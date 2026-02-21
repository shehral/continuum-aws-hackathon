"""Git integration service for Continuum.

Part 4.2: CommitNode creation, IMPLEMENTED_BY and TOUCHES edges
Part 4.6: Stale file detection (files not modified in N days)
Part 6:   POST /api/git/commit endpoint support

Provides:
- GitService.get_commits_in_window() — commits near a session timestamp
- GitService.link_session_to_commits() — score commits vs session files
- GitService.create_commit_node() — write CommitNode to Neo4j
- GitService.get_stale_files() — files not modified in threshold_days
- GitService.get_all_repo_files() — file tree for Coverage Map
"""

import asyncio
import json
import subprocess
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Optional

from config import get_settings
from utils.logging import get_logger

logger = get_logger(__name__)


# ---------------------------------------------------------------------------
# Data classes
# ---------------------------------------------------------------------------

@dataclass
class CommitInfo:
    """Metadata for a single git commit."""
    sha: str
    short_sha: str
    message: str
    author_name: str
    author_email: str
    committed_at: datetime
    files_changed: list[str] = field(default_factory=list)

    @property
    def summary(self) -> str:
        return self.message.split("\n")[0][:120]


@dataclass
class StaleFile:
    """A file that hasn't been modified recently."""
    file_path: str          # Relative to repo root
    last_modified: datetime
    days_since_modified: int
    has_decisions: bool = False
    decision_ids: list[str] = field(default_factory=list)


@dataclass
class RepoFile:
    """A file in the repository with metadata."""
    file_path: str          # Relative to repo root
    language: str
    size_bytes: int = 0
    last_modified: Optional[datetime] = None
    decision_count: int = 0


# ---------------------------------------------------------------------------
# GitService
# ---------------------------------------------------------------------------

class GitService:
    """Interact with a local git repository to link commits to decisions.

    All subprocess calls use a 10-second timeout and fail gracefully —
    if git is unavailable the calling code receives empty results.
    """

    def __init__(self, repo_path: str):
        self.repo_path = Path(repo_path).expanduser().resolve()
        self._git_available: Optional[bool] = None

    def _run_git(self, args: list[str], timeout: int = 10) -> Optional[str]:
        """Run a git command and return stdout, or None on failure."""
        try:
            result = subprocess.run(
                ["git"] + args,
                capture_output=True,
                text=True,
                cwd=str(self.repo_path),
                timeout=timeout,
            )
            if result.returncode == 0:
                return result.stdout
            logger.debug(f"git {' '.join(args)} failed: {result.stderr[:200]}")
        except subprocess.TimeoutExpired:
            logger.warning(f"git {' '.join(args)} timed out")
        except FileNotFoundError:
            logger.warning("git not found in PATH")
        except Exception as e:
            logger.debug(f"git error: {e}")
        return None

    def _is_git_repo(self) -> bool:
        if self._git_available is None:
            out = self._run_git(["rev-parse", "--git-dir"])
            self._git_available = out is not None
        return self._git_available

    def _parse_commit_line(self, line: str) -> Optional[CommitInfo]:
        """Parse a formatted git log line.

        Format: SHA|short_sha|author_name|author_email|iso_date|subject
        """
        parts = line.strip().split("|")
        if len(parts) < 6:
            return None
        sha, short_sha, author_name, author_email, iso_date, *subject_parts = parts
        subject = "|".join(subject_parts)
        try:
            committed_at = datetime.fromisoformat(iso_date.replace("Z", "+00:00"))
        except ValueError:
            return None
        return CommitInfo(
            sha=sha.strip(),
            short_sha=short_sha.strip(),
            message=subject.strip(),
            author_name=author_name.strip(),
            author_email=author_email.strip(),
            committed_at=committed_at,
        )

    def _get_commit_files(self, sha: str) -> list[str]:
        """Return files changed in a given commit."""
        out = self._run_git(
            ["diff-tree", "--no-commit-id", "-r", "--name-only", sha]
        )
        if not out:
            return []
        return [line.strip() for line in out.splitlines() if line.strip()]

    def get_commits_in_window(
        self,
        start: datetime,
        end: datetime,
    ) -> list[CommitInfo]:
        """Return commits made in [start, end] window.

        Args:
            start: Window start (UTC)
            end:   Window end (UTC)
        """
        if not self._is_git_repo():
            return []

        since = start.strftime("%Y-%m-%dT%H:%M:%S")
        until = end.strftime("%Y-%m-%dT%H:%M:%S")

        out = self._run_git([
            "log",
            f"--since={since}",
            f"--until={until}",
            "--format=%H|%h|%an|%ae|%aI|%s",
        ])
        if not out:
            return []

        commits: list[CommitInfo] = []
        for line in out.splitlines():
            commit = self._parse_commit_line(line)
            if commit:
                commit.files_changed = self._get_commit_files(commit.sha)
                commits.append(commit)

        return commits

    def _score_commit(self, commit: CommitInfo, session_files: list[str]) -> float:
        """File-overlap score between a commit and the session's affected files.

        Score = |intersection| / |union|  (Jaccard similarity)
        """
        if not session_files or not commit.files_changed:
            return 0.0
        a = set(session_files)
        b = set(commit.files_changed)
        intersection = len(a & b)
        union = len(a | b)
        return intersection / union if union > 0 else 0.0

    def link_session_to_commits(
        self,
        session_timestamp: datetime,
        affected_files: list[str],
        window_hours: Optional[int] = None,
        score_threshold: Optional[float] = None,
    ) -> list[tuple[CommitInfo, float]]:
        """Find commits that plausibly implement decisions from this session.

        Returns list of (CommitInfo, score) pairs sorted by score descending.
        Only includes commits whose file-overlap score >= score_threshold.

        Args:
            session_timestamp: When the Claude Code session started
            affected_files:    Files touched by tool calls in the session
            window_hours:      How many hours after session_start to search
            score_threshold:   Minimum Jaccard overlap score
        """
        settings = get_settings()
        window_hours = window_hours or settings.git_commit_link_window_hours
        score_threshold = score_threshold or settings.git_commit_link_score_threshold

        start = session_timestamp
        end = session_timestamp + timedelta(hours=window_hours)

        commits = self.get_commits_in_window(start, end)
        results: list[tuple[CommitInfo, float]] = []

        for commit in commits:
            score = self._score_commit(commit, affected_files)
            if score >= score_threshold:
                results.append((commit, score))

        results.sort(key=lambda x: x[1], reverse=True)
        return results

    def get_stale_files(
        self,
        threshold_days: Optional[int] = None,
    ) -> list[StaleFile]:
        """Return files not modified in the last threshold_days.

        Args:
            threshold_days: Days without modification to be considered stale.
                            Defaults to git_stale_file_threshold_days from config.
        """
        if not self._is_git_repo():
            return []

        settings = get_settings()
        threshold = threshold_days or settings.git_stale_file_threshold_days
        cutoff = datetime.now(UTC) - timedelta(days=threshold)

        # Get all tracked files with their last commit date
        out = self._run_git([
            "log",
            "--format=%aI %f",
            "--name-only",
            "--diff-filter=A",  # files that were added
        ])

        # Simpler approach: get last commit date per file
        out = self._run_git([
            "ls-files",
        ])
        if not out:
            return []

        all_files = [f.strip() for f in out.splitlines() if f.strip()]
        stale: list[StaleFile] = []

        for file_path in all_files:
            log_out = self._run_git([
                "log",
                "-1",
                "--format=%aI",
                "--",
                file_path,
            ])
            if not log_out or not log_out.strip():
                continue

            try:
                last_modified = datetime.fromisoformat(log_out.strip().replace("Z", "+00:00"))
            except ValueError:
                continue

            if last_modified < cutoff:
                days_since = (datetime.now(UTC) - last_modified).days
                stale.append(StaleFile(
                    file_path=file_path,
                    last_modified=last_modified,
                    days_since_modified=days_since,
                ))

        return stale

    def get_all_repo_files(self) -> list[RepoFile]:
        """Return all tracked files with basic metadata for Coverage Map.

        Used by GET /api/git/files to populate the file tree view.
        """
        if not self._is_git_repo():
            return []

        out = self._run_git(["ls-files", "-z"])
        if not out:
            return []

        files: list[RepoFile] = []
        from services.code_resolver import _detect_language

        for file_path in out.split("\x00"):
            file_path = file_path.strip()
            if not file_path:
                continue

            full = self.repo_path / file_path
            size = full.stat().st_size if full.exists() else 0

            # Get last modified date from git
            log_out = self._run_git(["log", "-1", "--format=%aI", "--", file_path])
            last_modified: Optional[datetime] = None
            if log_out and log_out.strip():
                try:
                    last_modified = datetime.fromisoformat(log_out.strip().replace("Z", "+00:00"))
                except ValueError:
                    pass

            files.append(RepoFile(
                file_path=file_path,
                language=_detect_language(file_path),
                size_bytes=size,
                last_modified=last_modified,
            ))

        return files


# ---------------------------------------------------------------------------
# Neo4j operations
# ---------------------------------------------------------------------------

async def create_commit_node(session, commit: CommitInfo, user_id: str) -> str:
    """Create or merge a CommitNode in Neo4j.

    Returns the commit SHA (used as node ID).
    """
    await session.run(
        """
        MERGE (c:CommitNode {sha: $sha})
        SET c.short_sha = $short_sha,
            c.message   = $message,
            c.author    = $author,
            c.committed_at = $committed_at,
            c.files_changed = $files,
            c.user_id   = $user_id
        """,
        sha=commit.sha,
        short_sha=commit.short_sha,
        message=commit.summary,
        author=commit.author_email,
        committed_at=commit.committed_at.isoformat(),
        files=commit.files_changed,
        user_id=user_id,
    )
    return commit.sha


async def create_implemented_by_edge(
    session,
    decision_id: str,
    commit_sha: str,
    score: float,
) -> None:
    """Create IMPLEMENTED_BY edge: Decision → CommitNode."""
    await session.run(
        """
        MATCH (d:DecisionTrace {id: $decision_id})
        MATCH (c:CommitNode {sha: $sha})
        MERGE (d)-[r:IMPLEMENTED_BY]->(c)
        SET r.score = $score,
            r.linked_at = $now
        """,
        decision_id=decision_id,
        sha=commit_sha,
        score=score,
        now=datetime.now(UTC).isoformat(),
    )


async def create_touches_edges(
    session,
    commit_sha: str,
    code_entity_paths: list[str],
    user_id: str,
) -> None:
    """Create TOUCHES edges: CommitNode → CodeEntity for each changed file."""
    for file_path in code_entity_paths:
        await session.run(
            """
            MATCH (c:CommitNode {sha: $sha})
            MERGE (e:CodeEntity {file_path: $path, user_id: $user_id})
            ON CREATE SET e.file_stem = $stem, e.user_id = $user_id
            MERGE (c)-[:TOUCHES]->(e)
            """,
            sha=commit_sha,
            path=file_path,
            stem=Path(file_path).stem,
            user_id=user_id,
        )


async def create_code_entity_node(
    session,
    file_path: str,
    user_id: str,
    language: str = "unknown",
    line_count: int = 0,
    size_bytes: int = 0,
) -> None:
    """Create or update a CodeEntity node in Neo4j."""
    await session.run(
        """
        MERGE (e:CodeEntity {file_path: $path, user_id: $user_id})
        SET e.file_stem   = $stem,
            e.language    = $language,
            e.line_count  = $line_count,
            e.size_bytes  = $size_bytes,
            e.indexed_at  = $now
        """,
        path=file_path,
        user_id=user_id,
        stem=Path(file_path).stem,
        language=language,
        line_count=line_count,
        size_bytes=size_bytes,
        now=datetime.now(UTC).isoformat(),
    )


async def create_affects_edge(
    session,
    decision_id: str,
    file_path: str,
    user_id: str,
    confidence: float = 1.0,
    source: str = "tool_call",
) -> None:
    """Create AFFECTS edge: Decision → CodeEntity.

    ``source`` is "tool_call" for ground-truth references or "inferred"
    for fuzzy-matched mentions.
    """
    await session.run(
        """
        MATCH (d:DecisionTrace {id: $decision_id})
        MERGE (e:CodeEntity {file_path: $path, user_id: $user_id})
        ON CREATE SET e.file_stem = $stem, e.user_id = $user_id
        MERGE (d)-[r:AFFECTS]->(e)
        SET r.confidence = $confidence,
            r.source     = $source
        """,
        decision_id=decision_id,
        path=file_path,
        user_id=user_id,
        stem=Path(file_path).stem,
        confidence=confidence,
        source=source,
    )


# ---------------------------------------------------------------------------
# Singleton per repo_path
# ---------------------------------------------------------------------------

_git_service_cache: dict[str, GitService] = {}


def get_git_service() -> Optional[GitService]:
    """Get the GitService for the configured repo_path.

    Returns None if repo_path is not configured or doesn't exist.
    """
    settings = get_settings()
    repo_path = settings.repo_path
    if not repo_path:
        return None

    full = Path(repo_path).expanduser().resolve()
    if not full.exists():
        return None

    path_str = str(full)
    if path_str not in _git_service_cache:
        _git_service_cache[path_str] = GitService(path_str)

    return _git_service_cache[path_str]
