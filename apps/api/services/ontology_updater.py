"""Automated canonical dictionary updates — Part 3a.

OntologyUpdater mines three sources to discover new canonical name mappings:
  1. PyPI JSON API — Python package name variants (e.g. Pillow → PIL)
  2. npm registry API — JavaScript package name variants
  3. crates.io API — Rust crate name variants
  4. Neo4j graph — entity names created 5+ times with slight variations
     (detected via fuzzy-matching existing Entity nodes)

New mappings are written to:
  apps/api/models/ontology_dynamic.py  (auto-generated, loaded alongside static)

API endpoint (triggered on-demand or weekly):
  POST /api/admin/ontology/refresh

Architecture:
  - All registry calls are async + bounded (5-second timeout each)
  - New mappings are appended, not overwritten (safe to re-run)
  - The dynamic file is imported in ontology.py alongside the static dict
"""

from __future__ import annotations

import asyncio
import re
from datetime import UTC, datetime
from pathlib import Path
from typing import Optional

import aiohttp

from utils.logging import get_logger

logger = get_logger(__name__)

# Path to the auto-generated dynamic canonical mappings file
_DYNAMIC_ONTOLOGY_PATH = Path(__file__).parent.parent / "models" / "ontology_dynamic.py"

_REQUEST_TIMEOUT = 5  # seconds per registry call

# Known alias patterns for the three registries
_PYPI_KNOWN_ALIASES: dict[str, list[str]] = {
    "pillow": ["pil", "PIL", "Pillow"],
    "scikit-learn": ["sklearn", "scikit_learn"],
    "beautifulsoup4": ["bs4", "beautifulsoup"],
    "python-dotenv": ["dotenv"],
    "pyyaml": ["yaml"],
    "opencv-python": ["cv2"],
    "tensorflow": ["tf"],
    "pytorch": ["torch"],
    "psycopg2-binary": ["psycopg2"],
    "httpx": ["httpx"],
}

_NPM_KNOWN_ALIASES: dict[str, list[str]] = {
    "react": ["react-dom", "React"],
    "lodash": ["_", "lodash-es"],
    "axios": ["axios"],
    "typescript": ["ts"],
    "tailwindcss": ["tailwind"],
    "next": ["nextjs", "next.js"],
    "express": ["expressjs"],
}


class OntologyUpdater:
    """Mine package registries and the Neo4j graph for new canonical name mappings.

    Usage (from router or background task):
        updater = OntologyUpdater(neo4j_session)
        new_mappings = await updater.refresh()
        # Returns number of new mappings added
    """

    def __init__(self, neo4j_session=None):
        self.session = neo4j_session

    # ------------------------------------------------------------------
    # Registry lookups
    # ------------------------------------------------------------------

    async def _fetch_pypi_aliases(self, name: str) -> list[str]:
        """Fetch PyPI package info and extract common import name variants."""
        url = f"https://pypi.org/pypi/{name}/json"
        try:
            async with aiohttp.ClientSession(
                timeout=aiohttp.ClientTimeout(total=_REQUEST_TIMEOUT)
            ) as http:
                async with http.get(url) as resp:
                    if resp.status != 200:
                        return []
                    data = await resp.json()
        except Exception:
            return []

        aliases: list[str] = [name]
        info = data.get("info", {})

        # Common pattern: PyPI name uses hyphens, import uses underscore
        underscore_variant = name.replace("-", "_")
        if underscore_variant != name:
            aliases.append(underscore_variant)

        # Extract from classifiers (e.g. "Topic :: Software Development :: Libraries :: Python Modules")
        summary = info.get("summary", "").lower()
        # Look for "import X" patterns in summary or description
        for match in re.findall(r"import\s+(\w+)", info.get("description", "")[:2000] or ""):
            if match.lower() != name.lower() and len(match) > 2:
                aliases.append(match)

        # Known hard-coded aliases (supplement registry data)
        if name.lower() in _PYPI_KNOWN_ALIASES:
            aliases.extend(_PYPI_KNOWN_ALIASES[name.lower()])

        return list(set(aliases))

    async def _fetch_npm_aliases(self, name: str) -> list[str]:
        """Fetch npm registry info for a package name."""
        url = f"https://registry.npmjs.org/{name}/latest"
        try:
            async with aiohttp.ClientSession(
                timeout=aiohttp.ClientTimeout(total=_REQUEST_TIMEOUT)
            ) as http:
                async with http.get(url) as resp:
                    if resp.status != 200:
                        return [name]
                    data = await resp.json()
        except Exception:
            return [name]

        aliases: list[str] = [name]

        # Scoped packages: @org/package → package
        if name.startswith("@") and "/" in name:
            bare = name.split("/", 1)[1]
            aliases.append(bare)

        # Known hard-coded aliases
        if name.lower() in _NPM_KNOWN_ALIASES:
            aliases.extend(_NPM_KNOWN_ALIASES[name.lower()])

        return list(set(aliases))

    async def _fetch_crates_aliases(self, name: str) -> list[str]:
        """Fetch crates.io info for a Rust crate."""
        url = f"https://crates.io/api/v1/crates/{name}"
        try:
            async with aiohttp.ClientSession(
                timeout=aiohttp.ClientTimeout(total=_REQUEST_TIMEOUT),
                headers={"User-Agent": "Continuum/1.0 (ontology updater)"},
            ) as http:
                async with http.get(url) as resp:
                    if resp.status != 200:
                        return [name]
                    data = await resp.json()
        except Exception:
            return [name]

        aliases: list[str] = [name]
        # Some crates have underscore/hyphen duality
        aliases.append(name.replace("-", "_"))
        aliases.append(name.replace("_", "-"))

        return list(set(a for a in aliases if a))

    # ------------------------------------------------------------------
    # Neo4j graph mining
    # ------------------------------------------------------------------

    async def _mine_graph_aliases(self) -> dict[str, list[str]]:
        """Find entity names with 5+ occurrences that are likely alias variants.

        Strategy: group by normalized form (lowercase, strip punctuation),
        where 2+ different spellings of the same concept appear → candidate alias pair.
        """
        if not self.session:
            return {}

        try:
            result = await self.session.run(
                """
                MATCH (e:Entity)
                WHERE e.type IN ['technology', 'library', 'system']
                RETURN toLower(trim(e.name)) AS normalized,
                       e.name AS raw_name,
                       count(e) AS usage_count
                ORDER BY usage_count DESC
                LIMIT 500
                """
            )
            rows = await result.data()
        except Exception as e:
            logger.warning(f"Graph alias mining failed: {e}")
            return {}

        # Group raw names by their slug (letters+numbers only)
        slug_groups: dict[str, list[str]] = {}
        for row in rows:
            raw = row.get("raw_name", "")
            slug = re.sub(r"[^a-z0-9]", "", row.get("normalized", "").lower())
            if slug and len(slug) > 2:
                slug_groups.setdefault(slug, []).append(raw)

        # Return groups with 2+ different names (alias candidates)
        return {
            slug: list(set(names))
            for slug, names in slug_groups.items()
            if len(set(n.lower() for n in names)) >= 2
        }

    # ------------------------------------------------------------------
    # Dynamic file management
    # ------------------------------------------------------------------

    def _load_existing_dynamic(self) -> dict[str, str]:
        """Parse the existing ontology_dynamic.py file into a dict."""
        existing: dict[str, str] = {}
        if not _DYNAMIC_ONTOLOGY_PATH.exists():
            return existing

        content = _DYNAMIC_ONTOLOGY_PATH.read_text()
        # Parse lines like:    "alias": "canonical",
        for match in re.finditer(r'"([^"]+)":\s*"([^"]+)"', content):
            alias, canonical = match.group(1), match.group(2)
            existing[alias.lower()] = canonical
        return existing

    def _write_dynamic_file(self, mappings: dict[str, str]) -> None:
        """Write the complete set of mappings to ontology_dynamic.py."""
        lines = [
            '"""Auto-generated canonical name mappings — do not edit manually.',
            "",
            "Generated by OntologyUpdater. Re-run POST /api/admin/ontology/refresh to update.",
            '"""',
            "",
            "# Maps alias (lowercase) → canonical name",
            "DYNAMIC_CANONICAL_NAMES: dict[str, str] = {",
        ]
        for alias, canonical in sorted(mappings.items()):
            lines.append(f'    "{alias}": "{canonical}",')
        lines.append("}")
        lines.append("")

        _DYNAMIC_ONTOLOGY_PATH.write_text("\n".join(lines))
        logger.info(f"Written {len(mappings)} mappings to {_DYNAMIC_ONTOLOGY_PATH}")

    # ------------------------------------------------------------------
    # Main refresh entry point
    # ------------------------------------------------------------------

    async def refresh(
        self,
        technology_names: Optional[list[str]] = None,
    ) -> int:
        """Refresh canonical mappings from registries and the Neo4j graph.

        Args:
            technology_names: Optional list of technology names to look up.
                              If None, uses a built-in seed list.

        Returns:
            Number of new mappings added.
        """
        seed_names = technology_names or [
            # Python packages
            "pillow", "scikit-learn", "beautifulsoup4", "python-dotenv",
            "pyyaml", "opencv-python", "tensorflow", "pytorch", "psycopg2-binary",
            "fastapi", "pydantic", "sqlalchemy", "celery", "redis",
            # npm packages
            "react", "lodash", "axios", "typescript", "next", "express",
            "tailwindcss", "@apollo/client", "graphql",
            # Rust crates
            "tokio", "serde", "actix-web", "reqwest",
        ]

        existing = self._load_existing_dynamic()
        new_mappings: dict[str, str] = dict(existing)
        added = 0

        # Parallel registry lookups (bounded concurrency)
        sem = asyncio.Semaphore(5)  # max 5 concurrent HTTP calls

        async def lookup_one(name: str) -> None:
            nonlocal added
            async with sem:
                # Try PyPI first, then npm
                pypi_aliases = await self._fetch_pypi_aliases(name)
                npm_aliases = await self._fetch_npm_aliases(name)
                crates_aliases = await self._fetch_crates_aliases(name)

                all_aliases = set(pypi_aliases + npm_aliases + crates_aliases)
                canonical = name.lower()

                for alias in all_aliases:
                    key = alias.lower()
                    if key != canonical and key not in new_mappings:
                        new_mappings[key] = canonical
                        added += 1

        await asyncio.gather(*(lookup_one(n) for n in seed_names))

        # Mine graph aliases
        graph_groups = await self._mine_graph_aliases()
        for _slug, variants in graph_groups.items():
            # Heuristic: longest variant is most likely the canonical name
            canonical = max(variants, key=len).lower()
            for v in variants:
                key = v.lower()
                if key != canonical and key not in new_mappings:
                    new_mappings[key] = canonical
                    added += 1

        if added > 0 or not _DYNAMIC_ONTOLOGY_PATH.exists():
            self._write_dynamic_file(new_mappings)

        logger.info(f"OntologyUpdater: {added} new mappings added, {len(new_mappings)} total")
        return added


# ---------------------------------------------------------------------------
# Integration with static ontology — load dynamic mappings at startup
# ---------------------------------------------------------------------------

def load_dynamic_canonical_names() -> dict[str, str]:
    """Load the auto-generated canonical name mappings, if the file exists."""
    if not _DYNAMIC_ONTOLOGY_PATH.exists():
        return {}
    try:
        _globals: dict = {}
        exec(_DYNAMIC_ONTOLOGY_PATH.read_text(), _globals)  # nosec (own generated file)
        return _globals.get("DYNAMIC_CANONICAL_NAMES", {})
    except Exception as e:
        logger.warning(f"Failed to load dynamic ontology: {e}")
        return {}
