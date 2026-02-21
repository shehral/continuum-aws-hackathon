"""Code entity grounding — links natural-language file mentions to real codebase paths.

Part 3b/3c: File entity grounding + type-aware resolution thresholds
Part 3d:    Package registry lookups (PyPI, npm, crates.io)
Part 4.1:   CodeEntity Neo4j nodes + AFFECTS edges

Resolution cascade (fast → slow):
  1. Exact path match        ("apps/api/services/extractor.py")
  2. File stem match         ("extractor" → apps/api/services/extractor.py)
  3. Fuzzy stem match        (RapidFuzz, threshold 85%)
  4. Symbol match            (class/function name → file)
  5. Directory match         ("services layer" → apps/api/services/)

Tool-call file paths are resolved with confidence 1.0 (no fuzzy needed —
they are ground truth from the ToolCall.input dict).

Package registry lookup is an async Stage 3.5 for `technology` entities
not found in the local canonical dictionary.  Results are cached in Redis
for 7 days to avoid repeated network calls.
"""

import asyncio
import hashlib
import re
from pathlib import Path
from typing import Optional
from dataclasses import dataclass, field

import aiohttp

from config import get_settings
from db.redis import get_redis
from utils.logging import get_logger

logger = get_logger(__name__)


# ---------------------------------------------------------------------------
# Type-aware resolution thresholds (Part 3c)
# ---------------------------------------------------------------------------

TYPE_RESOLUTION_THRESHOLDS: dict[str, dict[str, float]] = {
    "file": {
        "fuzzy": 0.95,      # High precision — wrong file = wrong AFFECTS edge
        "embedding": 0.97,
    },
    "technology": {
        "fuzzy": 0.85,      # Current global default
        "embedding": 0.90,
    },
    "concept": {
        "fuzzy": 0.75,      # Higher recall — "eventual consistency" ≈ "eventual-consistency"
        "embedding": 0.82,
    },
    "pattern": {
        "fuzzy": 0.78,
        "embedding": 0.85,
    },
    "system": {
        "fuzzy": 0.88,
        "embedding": 0.92,
    },
    "person": {
        "fuzzy": 0.92,
        "embedding": 0.95,
    },
    "organization": {
        "fuzzy": 0.90,
        "embedding": 0.93,
    },
}


def get_type_threshold(entity_type: str, match_kind: str = "fuzzy") -> float:
    """Return the resolution threshold for a given entity type and match kind."""
    defaults = {"fuzzy": 0.85, "embedding": 0.90}
    type_entry = TYPE_RESOLUTION_THRESHOLDS.get(entity_type.lower(), defaults)
    return type_entry.get(match_kind, defaults[match_kind])


# ---------------------------------------------------------------------------
# Data classes
# ---------------------------------------------------------------------------

@dataclass
class CodeEntity:
    """A resolved codebase file or directory."""
    file_path: str              # Relative to repo root
    file_stem: str              # Filename without extension
    language: str               # python, typescript, javascript, rust, go, …
    entity_type: str = "file"
    line_count: int = 0
    size_bytes: int = 0
    confidence: float = 1.0     # 1.0 for tool-call ground truth, <1.0 for fuzzy
    resolution_method: str = "exact"  # exact, stem, fuzzy, symbol, directory


@dataclass
class CanonicalMapping:
    """A canonical package name from a registry."""
    name: str               # canonical name (e.g. "Pillow")
    aliases: list[str]      # known aliases (e.g. ["PIL", "pillow"])
    registry: str           # "pypi" | "npm" | "crates"
    description: str = ""


# ---------------------------------------------------------------------------
# Package registry client (Part 3d)
# ---------------------------------------------------------------------------

_REGISTRY_CACHE_PREFIX = "pkg_registry:"
_REGISTRY_CACHE_TTL = 60 * 60 * 24 * 7  # 7 days


class PackageRegistryClient:
    """Async package registry lookups for PyPI, npm, and crates.io.

    Results are cached in Redis for 7 days to minimise network overhead.
    All network calls have a 5-second timeout and fail silently so the
    entity resolution pipeline is never blocked by registry availability.
    """

    async def _get_cached(self, key: str) -> Optional[dict]:
        redis = await get_redis()
        if not redis:
            return None
        try:
            raw = await redis.get(key)
            if raw:
                import json
                return json.loads(raw)
        except Exception:
            pass
        return None

    async def _set_cached(self, key: str, value: dict) -> None:
        redis = await get_redis()
        if not redis:
            return
        try:
            import json
            await redis.setex(key, _REGISTRY_CACHE_TTL, json.dumps(value))
        except Exception:
            pass

    async def _check_pypi(self, name: str) -> Optional[CanonicalMapping]:
        cache_key = f"{_REGISTRY_CACHE_PREFIX}pypi:{name.lower()}"
        cached = await self._get_cached(cache_key)
        if cached:
            return CanonicalMapping(**cached)

        url = f"https://pypi.org/pypi/{name}/json"
        try:
            async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=5)) as session:
                async with session.get(url) as resp:
                    if resp.status == 200:
                        data = await resp.json()
                        info = data.get("info", {})
                        canonical = info.get("name", name)
                        aliases = list({name, name.lower(), canonical, canonical.lower()})
                        mapping = CanonicalMapping(
                            name=canonical,
                            aliases=aliases,
                            registry="pypi",
                            description=info.get("summary", ""),
                        )
                        await self._set_cached(cache_key, {
                            "name": mapping.name,
                            "aliases": mapping.aliases,
                            "registry": mapping.registry,
                            "description": mapping.description,
                        })
                        return mapping
        except Exception as e:
            logger.debug(f"PyPI lookup failed for {name}: {e}")
        return None

    async def _check_npm(self, name: str) -> Optional[CanonicalMapping]:
        cache_key = f"{_REGISTRY_CACHE_PREFIX}npm:{name.lower()}"
        cached = await self._get_cached(cache_key)
        if cached:
            return CanonicalMapping(**cached)

        url = f"https://registry.npmjs.org/{name}/latest"
        try:
            async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=5)) as session:
                async with session.get(url) as resp:
                    if resp.status == 200:
                        data = await resp.json()
                        canonical = data.get("name", name)
                        aliases = list({name, canonical})
                        mapping = CanonicalMapping(
                            name=canonical,
                            aliases=aliases,
                            registry="npm",
                            description=data.get("description", ""),
                        )
                        await self._set_cached(cache_key, {
                            "name": mapping.name,
                            "aliases": mapping.aliases,
                            "registry": mapping.registry,
                            "description": mapping.description,
                        })
                        return mapping
        except Exception as e:
            logger.debug(f"npm lookup failed for {name}: {e}")
        return None

    async def _check_crates(self, name: str) -> Optional[CanonicalMapping]:
        cache_key = f"{_REGISTRY_CACHE_PREFIX}crates:{name.lower()}"
        cached = await self._get_cached(cache_key)
        if cached:
            return CanonicalMapping(**cached)

        url = f"https://crates.io/api/v1/crates/{name}"
        headers = {"User-Agent": "Continuum/1.0 (knowledge graph tool)"}
        try:
            async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=5)) as session:
                async with session.get(url, headers=headers) as resp:
                    if resp.status == 200:
                        data = await resp.json()
                        crate = data.get("crate", {})
                        canonical = crate.get("name", name)
                        aliases = list({name, canonical})
                        mapping = CanonicalMapping(
                            name=canonical,
                            aliases=aliases,
                            registry="crates",
                            description=crate.get("description", ""),
                        )
                        await self._set_cached(cache_key, {
                            "name": mapping.name,
                            "aliases": mapping.aliases,
                            "registry": mapping.registry,
                            "description": mapping.description,
                        })
                        return mapping
        except Exception as e:
            logger.debug(f"crates.io lookup failed for {name}: {e}")
        return None

    async def resolve_technology(self, name: str) -> Optional[CanonicalMapping]:
        """Query all registries in parallel and return the first match."""
        results = await asyncio.gather(
            self._check_pypi(name),
            self._check_npm(name),
            self._check_crates(name),
            return_exceptions=True,
        )
        for r in results:
            if isinstance(r, CanonicalMapping):
                return r
        return None


# ---------------------------------------------------------------------------
# File extension → language mapping
# ---------------------------------------------------------------------------

_EXT_LANGUAGE: dict[str, str] = {
    ".py": "python",
    ".ts": "typescript",
    ".tsx": "typescript",
    ".js": "javascript",
    ".jsx": "javascript",
    ".mjs": "javascript",
    ".rs": "rust",
    ".go": "go",
    ".java": "java",
    ".kt": "kotlin",
    ".cs": "csharp",
    ".cpp": "cpp",
    ".c": "c",
    ".rb": "ruby",
    ".php": "php",
    ".swift": "swift",
    ".scala": "scala",
    ".sh": "shell",
    ".bash": "shell",
    ".zsh": "shell",
    ".sql": "sql",
    ".toml": "toml",
    ".yaml": "yaml",
    ".yml": "yaml",
    ".json": "json",
    ".md": "markdown",
    ".mdx": "markdown",
}


def _detect_language(path: str) -> str:
    suffix = Path(path).suffix.lower()
    return _EXT_LANGUAGE.get(suffix, "unknown")


def _count_lines(full_path: Path) -> int:
    try:
        return sum(1 for _ in full_path.open("rb"))
    except Exception:
        return 0


# ---------------------------------------------------------------------------
# CodeResolver
# ---------------------------------------------------------------------------

class CodeResolver:
    """Resolve natural-language file mentions to real codebase paths.

    Usage
    -----
    resolver = CodeResolver("/path/to/repo")
    await resolver.build_index()
    entity = await resolver.resolve_file_entity("extractor.py")
    """

    def __init__(self, repo_path: str):
        self.repo_path = Path(repo_path).expanduser().resolve()
        self._file_index: dict[str, str] = {}         # stem_lower → relative_path
        self._multi_stem: dict[str, list[str]] = {}   # stem_lower → [paths] (ambiguous)
        self._all_paths: list[str] = []               # all relative paths
        self._indexed = False
        self._registry_client = PackageRegistryClient()

    async def build_index(self) -> int:
        """Index all tracked files in the repo.

        Uses ``git ls-files`` when available (fastest, respects .gitignore).
        Falls back to a recursive glob if git is not available.

        Returns the number of files indexed.
        """
        files: list[str] = []

        # Try git ls-files first
        try:
            import subprocess
            result = subprocess.run(
                ["git", "ls-files"],
                capture_output=True,
                text=True,
                cwd=str(self.repo_path),
                timeout=10,
            )
            if result.returncode == 0:
                files = [line.strip() for line in result.stdout.splitlines() if line.strip()]
        except Exception:
            pass

        # Fallback: walk the directory
        if not files:
            ignored_dirs = {".git", "node_modules", "__pycache__", ".venv", "dist", "build"}
            for p in self.repo_path.rglob("*"):
                if p.is_file() and not any(part in ignored_dirs for part in p.parts):
                    try:
                        files.append(str(p.relative_to(self.repo_path)))
                    except ValueError:
                        pass

        # Build stem index
        stem_counts: dict[str, int] = {}
        for rel_path in files:
            stem = Path(rel_path).stem.lower()
            stem_counts[stem] = stem_counts.get(stem, 0) + 1

        self._file_index = {}
        self._multi_stem = {}
        self._all_paths = files

        for rel_path in files:
            stem = Path(rel_path).stem.lower()
            if stem_counts[stem] == 1:
                self._file_index[stem] = rel_path
            else:
                self._multi_stem.setdefault(stem, []).append(rel_path)

        self._indexed = True
        logger.info(
            f"CodeResolver indexed {len(files)} files from {self.repo_path}",
            extra={"unique_stems": len(self._file_index), "ambiguous_stems": len(self._multi_stem)},
        )
        return len(files)

    def _make_entity(self, rel_path: str, confidence: float, method: str) -> CodeEntity:
        full = self.repo_path / rel_path
        return CodeEntity(
            file_path=rel_path,
            file_stem=Path(rel_path).stem,
            language=_detect_language(rel_path),
            line_count=_count_lines(full),
            size_bytes=full.stat().st_size if full.exists() else 0,
            confidence=confidence,
            resolution_method=method,
        )

    async def resolve_file_entity(self, mention: str) -> Optional[CodeEntity]:
        """Resolve a natural-language file mention to a CodeEntity.

        Resolution cascade:
        1. Exact path match
        2. Stem match (fast O(1))
        3. Fuzzy stem match via RapidFuzz (threshold from TYPE_RESOLUTION_THRESHOLDS["file"])
        4. Directory match (partial path)
        """
        if not self._indexed:
            await self.build_index()

        mention = mention.strip()
        if not mention:
            return None

        # 1. Exact relative path match
        for p in self._all_paths:
            if p == mention or p.endswith("/" + mention):
                return self._make_entity(p, 1.0, "exact")

        # 2. Stem match (fast)
        stem = Path(mention).stem.lower()
        if stem in self._file_index:
            return self._make_entity(self._file_index[stem], 0.95, "stem")
        if stem in self._multi_stem:
            # Ambiguous — return highest-confidence match by path proximity
            # For now, pick the shortest relative path (most likely the "main" file)
            best = min(self._multi_stem[stem], key=lambda p: len(p))
            return self._make_entity(best, 0.80, "stem_ambiguous")

        # 3. Fuzzy stem match
        try:
            from rapidfuzz import fuzz, process
            threshold = get_type_threshold("file", "fuzzy") * 100  # rapidfuzz uses 0-100
            all_stems = list(self._file_index.keys())
            if all_stems:
                match_result = process.extractOne(
                    stem,
                    all_stems,
                    scorer=fuzz.ratio,
                    score_cutoff=threshold,
                )
                if match_result:
                    matched_stem, score, _ = match_result
                    rel_path = self._file_index[matched_stem]
                    return self._make_entity(rel_path, score / 100, "fuzzy")
        except ImportError:
            pass  # rapidfuzz not available — skip fuzzy

        # 4. Directory match
        mention_lower = mention.lower()
        candidates = [p for p in self._all_paths if mention_lower in p.lower()]
        if candidates:
            best = min(candidates, key=lambda p: len(p))
            return self._make_entity(best, 0.60, "directory")

        return None

    async def resolve_tool_call_paths(self, file_paths: list[str]) -> list[CodeEntity]:
        """Resolve a list of file paths extracted directly from tool call inputs.

        These are ground-truth references (confidence 1.0) — no fuzzy matching needed.
        """
        if not self._indexed:
            await self.build_index()

        entities: list[CodeEntity] = []
        for raw_path in file_paths:
            # Normalise: strip leading ./ and repo prefix
            path = raw_path.strip()
            for prefix in (str(self.repo_path) + "/", "./"):
                if path.startswith(prefix):
                    path = path[len(prefix):]

            if not path:
                continue

            # Check if the path exists in index
            if path in self._all_paths:
                entities.append(self._make_entity(path, 1.0, "tool_call"))
            else:
                # Try as absolute → relative conversion
                for p in self._all_paths:
                    if path.endswith(p) or p.endswith(path):
                        entities.append(self._make_entity(p, 1.0, "tool_call"))
                        break

        return entities


# ---------------------------------------------------------------------------
# Singleton cache per repo_path
# ---------------------------------------------------------------------------

_resolver_cache: dict[str, CodeResolver] = {}


async def get_code_resolver() -> Optional[CodeResolver]:
    """Get the CodeResolver for the configured repo_path.

    Returns None if repo_path is not configured or doesn't exist.
    """
    settings = get_settings()
    repo_path = settings.repo_path
    if not repo_path:
        return None

    full = Path(repo_path).expanduser().resolve()
    if not full.exists():
        logger.warning(f"repo_path does not exist: {full}")
        return None

    path_str = str(full)
    if path_str not in _resolver_cache:
        resolver = CodeResolver(path_str)
        await resolver.build_index()
        _resolver_cache[path_str] = resolver

    return _resolver_cache[path_str]


async def invalidate_resolver_cache() -> None:
    """Force rebuild of the resolver index on next call."""
    global _resolver_cache
    _resolver_cache = {}
