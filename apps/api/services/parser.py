"""Claude Code JSONL log parser.

Parses JSONL conversation logs produced by Claude Code into structured
Conversation / Message objects.  Preserves tool call details and thinking
blocks that the previous implementation silently dropped.

Key types
---------
ToolCall       – A single tool invocation (Bash, Edit, Read, Write, etc.)
                 with its full input parameters and the matching tool_result.
Message        – One turn in the conversation.  Carries the human-readable
                 `content` string (for backward compat) *plus* structured
                 `tool_calls` list and optional `thinking` text.
Conversation   – The full conversation.  `get_full_text()` is unchanged.
                 `get_structured_text()` is the richer form used by the
                 extraction pipeline.
"""

import hashlib
import json
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import AsyncIterator, Optional

from utils.logging import get_logger

logger = get_logger(__name__)


# ---------------------------------------------------------------------------
# Structured types
# ---------------------------------------------------------------------------

@dataclass
class ToolCall:
    """One tool invocation from an assistant turn.

    Attributes
    ----------
    name          Tool name (Bash, Edit, Read, Write, Glob, Grep, …)
    input         Full parameter dict as supplied to the tool.
    result        Raw text returned by the tool (from the matching
                  tool_result block in the *next* user turn), or None if
                  the result has not yet been matched.
    tool_use_id   Unique ID used to correlate tool_use ↔ tool_result blocks.
    """
    name: str
    input: dict
    tool_use_id: str
    result: Optional[str] = None

    def params_summary(self, max_len: int = 120) -> str:
        """One-line summary of the most important input parameter."""
        if not self.input:
            return ""
        # Prefer common path / command parameters
        for key in ("command", "file_path", "path", "pattern", "query"):
            if key in self.input:
                val = str(self.input[key])
                return val if len(val) <= max_len else val[:max_len] + "…"
        # Fall back to first value
        first_val = str(next(iter(self.input.values())))
        return first_val if len(first_val) <= max_len else first_val[:max_len] + "…"

    @property
    def file_paths(self) -> list[str]:
        """Extract any file path referenced in this tool call.

        Used downstream to create AFFECTS edges between decisions and
        CodeEntity nodes without fuzzy matching.
        """
        paths: list[str] = []
        for key in ("file_path", "path", "notebook_path"):
            val = self.input.get(key)
            if val and isinstance(val, str):
                paths.append(val)
        return paths


@dataclass
class Message:
    """One turn in a Claude Code conversation.

    Attributes
    ----------
    role        'user' | 'assistant' | 'unknown'
    content     Human-readable text representation (backward compatible with
                the old parser).  Tool calls appear as
                "[Tool: Name(param_summary)]" and thinking blocks are omitted
                (they're available via the `thinking` attribute).
    timestamp   ISO-8601 string from the JSONL entry, or None.
    tool_calls  Structured ToolCall objects for assistant turns.
    thinking    Raw text of the <thinking> block (Claude extended thinking),
                or None.  This is the AI's internal deliberation and is the
                highest-fidelity source for rationale extraction.
    raw_blocks  Original content blocks list from the JSONL, for auditing.
    turn_index  Zero-based sequential index within the conversation.
    """
    role: str
    content: str
    timestamp: Optional[str] = None
    tool_calls: list[ToolCall] = field(default_factory=list)
    thinking: Optional[str] = None
    raw_blocks: list[dict] = field(default_factory=list)
    turn_index: int = 0


# ---------------------------------------------------------------------------
# Conversation
# ---------------------------------------------------------------------------

class Conversation:
    """Represents a Claude Code conversation.

    Backward-compatible with the old interface:
    - `self.messages` is a list[dict] with 'role', 'content', 'timestamp'
    - `get_full_text()` unchanged
    - `get_preview()` unchanged

    New additions:
    - `self.raw_messages` is a list[Message] with full structure
    - `get_structured_text()` richer representation for the extractor
    """

    def __init__(
        self,
        messages: list[dict],
        file_path: str,
        project_name: str = "",
        timestamp: datetime | None = None,
        raw_messages: Optional[list[Message]] = None,
    ):
        # Legacy: flat dicts used everywhere in the existing codebase
        self.messages = messages
        self.file_path = file_path
        self.project_name = project_name
        self.timestamp = timestamp or datetime.now(UTC)
        # New: structured Message objects
        self.raw_messages: list[Message] = raw_messages or []

    def get_full_text(self) -> str:
        """Get the full conversation as text (backward compatible)."""
        return "\n\n".join(
            f"{m.get('role', 'unknown')}: {m.get('content', '')}" for m in self.messages
        )

    def get_structured_text(self) -> str:
        """Richer text representation for the LLM extraction pipeline.

        Each turn includes:
        - The thinking block (highest-fidelity rationale signal)
        - Full tool invocations with parameters and results
        - The regular text content

        This replaces the flat `get_full_text()` as the extractor input so
        that the LLM sees the AI's actual deliberation process and the exact
        tool calls made — not just the sanitised summary.
        """
        parts: list[str] = []
        for msg in self.raw_messages:
            header = f"[Turn {msg.turn_index} | {msg.role}]"
            sections: list[str] = [header]

            # 1. Thinking block (Claude extended thinking / chain-of-thought)
            if msg.thinking:
                sections.append(f"<thinking>\n{msg.thinking}\n</thinking>")

            # 2. Tool calls with results
            for tc in msg.tool_calls:
                params = tc.params_summary()
                tc_line = f"Tool: {tc.name}({params})" if params else f"Tool: {tc.name}()"
                if tc.result is not None:
                    result_preview = tc.result[:500] + "…" if len(tc.result) > 500 else tc.result
                    sections.append(f"{tc_line}\nResult: {result_preview}")
                else:
                    sections.append(tc_line)

            # 3. Regular text content
            if msg.content:
                sections.append(f"Response: {msg.content}")

            parts.append("\n".join(sections))

        return "\n\n".join(parts)

    def get_preview(self, max_chars: int = 500) -> str:
        """Get a preview of the conversation."""
        full_text = self.get_full_text()
        if len(full_text) <= max_chars:
            return full_text
        return full_text[:max_chars] + "..."


# ---------------------------------------------------------------------------
# Parser
# ---------------------------------------------------------------------------

class ClaudeLogParser:
    """Parser for Claude Code JSONL log files."""

    def __init__(self, logs_path: str):
        self.logs_path = Path(logs_path).expanduser()
        self.processed_hashes: set[str] = set()

    def _compute_file_hash(self, file_path: Path) -> str:
        """Compute a hash of the file contents."""
        with open(file_path, "rb") as f:
            return hashlib.sha256(f.read()).hexdigest()

    def _extract_project_name(self, file_path: Path) -> str:
        """Extract project name from file path."""
        # Path structure: ~/.claude/projects/-Users-username-projectname/xxx.jsonl
        try:
            relative = file_path.relative_to(self.logs_path)
            project_dir = str(relative).split("/")[0]
            # Convert -Users-username-projectname to just projectname
            parts = project_dir.split("-")
            if len(parts) > 2:
                # Skip -Users-username- prefix, get the rest
                return "-".join(parts[3:]) if len(parts) > 3 else parts[-1]
            return project_dir
        except Exception:
            return "unknown"

    def get_available_projects(self) -> list[dict]:
        """List all available projects with their conversation counts."""
        if not self.logs_path.exists():
            return []

        projects = {}
        for file_path in self.logs_path.glob("**/*.jsonl"):
            if "subagents" in str(file_path):
                continue

            project_name = self._extract_project_name(file_path)
            project_dir = file_path.parent.name

            if project_dir not in projects:
                projects[project_dir] = {
                    "dir": project_dir,
                    "name": project_name,
                    "files": 0,
                    "path": str(file_path.parent),
                }
            projects[project_dir]["files"] += 1

        return list(projects.values())

    # ------------------------------------------------------------------
    # Core block-level parsers
    # ------------------------------------------------------------------

    @staticmethod
    def _extract_text_from_blocks(blocks: list) -> str:
        """Extract human-readable text from a content blocks list.

        Converts tool_use blocks to a short "[Tool: Name(params)]" marker
        (backward compatible) and ignores thinking / tool_result blocks at
        this layer (they are captured in _parse_structured_message).
        """
        parts: list[str] = []
        for block in blocks:
            if not isinstance(block, dict):
                if isinstance(block, str):
                    parts.append(block)
                continue

            btype = block.get("type", "")
            if btype == "text":
                text = block.get("text", "")
                if text:
                    parts.append(text)
            elif btype == "tool_use":
                name = block.get("name", "unknown")
                inp = block.get("input", {})
                # Build a minimal param summary without importing ToolCall
                for key in ("command", "file_path", "path", "pattern", "query"):
                    if key in inp:
                        val = str(inp[key])[:80]
                        parts.append(f"[Tool: {name}({val})]")
                        break
                else:
                    parts.append(f"[Tool: {name}]")
            # thinking / tool_result / other block types → handled elsewhere

        return "".join(parts)

    @staticmethod
    def _parse_structured_message(
        role: str,
        raw_content: object,
        timestamp: Optional[str],
        turn_index: int,
        pending_tool_results: dict[str, str],
    ) -> Message:
        """Build a structured Message from a raw JSONL message dict.

        Parameters
        ----------
        role                 'user' | 'assistant' | …
        raw_content          The msg['content'] value (str or list of blocks)
        timestamp            ISO-8601 string or None
        turn_index           Sequential position in the conversation
        pending_tool_results Mapping of tool_use_id → result text, collected
                             from tool_result blocks in *this* message (user
                             turns carry results for previous assistant calls).
        """
        tool_calls: list[ToolCall] = []
        thinking_parts: list[str] = []
        raw_blocks: list[dict] = []
        content_text = ""

        if isinstance(raw_content, str):
            content_text = raw_content

        elif isinstance(raw_content, list):
            raw_blocks = [b for b in raw_content if isinstance(b, dict)]
            content_text = ClaudeLogParser._extract_text_from_blocks(raw_content)

            for block in raw_content:
                if not isinstance(block, dict):
                    continue
                btype = block.get("type", "")

                if btype == "thinking":
                    # Claude extended thinking block — highest-fidelity rationale
                    text = block.get("thinking", block.get("text", ""))
                    if text:
                        thinking_parts.append(text)

                elif btype == "tool_use":
                    tc = ToolCall(
                        name=block.get("name", "unknown"),
                        input=block.get("input", {}),
                        tool_use_id=block.get("id", ""),
                    )
                    # Attach result if already collected (same-turn result)
                    if tc.tool_use_id and tc.tool_use_id in pending_tool_results:
                        tc.result = pending_tool_results.pop(tc.tool_use_id)
                    tool_calls.append(tc)

                elif btype == "tool_result":
                    # Store result so it can be matched to the ToolCall
                    tid = block.get("tool_use_id", "")
                    result_content = block.get("content", "")
                    if isinstance(result_content, list):
                        result_text = "".join(
                            b.get("text", "") for b in result_content
                            if isinstance(b, dict) and b.get("type") == "text"
                        )
                    else:
                        result_text = str(result_content) if result_content else ""
                    if tid:
                        pending_tool_results[tid] = result_text

        thinking_text = "\n\n".join(thinking_parts) if thinking_parts else None

        return Message(
            role=role,
            content=content_text,
            timestamp=timestamp,
            tool_calls=tool_calls,
            thinking=thinking_text,
            raw_blocks=raw_blocks,
            turn_index=turn_index,
        )

    def _parse_jsonl_file(self, file_path: Path) -> list[Conversation]:
        """Parse a single JSONL file into conversations."""
        conversations: list[Conversation] = []
        current_messages: list[dict] = []        # Legacy flat dicts
        current_raw: list[Message] = []          # Structured messages
        project_name = self._extract_project_name(file_path)

        # tool_use_id → result text: populated by tool_result blocks so the
        # matching tool_use ToolCall can receive its result.
        pending_tool_results: dict[str, str] = {}
        turn_index = 0

        try:
            with open(file_path, "r", encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if not line:
                        continue

                    try:
                        entry = json.loads(line)
                    except json.JSONDecodeError:
                        continue

                    # --------------------------------------------------
                    # Normal message entry
                    # --------------------------------------------------
                    if "message" in entry:
                        msg = entry["message"]
                        role = msg.get("role", "unknown")
                        raw_content = msg.get("content", "")
                        ts = entry.get("timestamp")

                        # Build structured message
                        structured = self._parse_structured_message(
                            role=role,
                            raw_content=raw_content,
                            timestamp=ts,
                            turn_index=turn_index,
                            pending_tool_results=pending_tool_results,
                        )

                        # After parsing a user message, try to attach pending
                        # tool results to the *previous* assistant's ToolCalls
                        # (tool_result blocks live in user turns that follow
                        # the assistant turn that issued tool_use blocks).
                        if role == "user" and pending_tool_results and current_raw:
                            last_assistant = next(
                                (m for m in reversed(current_raw) if m.role == "assistant"),
                                None,
                            )
                            if last_assistant:
                                for tc in last_assistant.tool_calls:
                                    if tc.tool_use_id in pending_tool_results:
                                        tc.result = pending_tool_results.pop(tc.tool_use_id)

                        if structured.content or structured.tool_calls or structured.thinking:
                            current_raw.append(structured)
                            # Legacy dict for backward compat
                            current_messages.append({
                                "role": role,
                                "content": structured.content,
                                "timestamp": ts,
                            })
                            turn_index += 1

                    # --------------------------------------------------
                    # Conversation boundary
                    # --------------------------------------------------
                    if entry.get("type") == "conversation_end" and current_messages:
                        conversations.append(
                            Conversation(
                                messages=current_messages.copy(),
                                file_path=str(file_path),
                                project_name=project_name,
                                raw_messages=current_raw.copy(),
                            )
                        )
                        current_messages = []
                        current_raw = []
                        pending_tool_results = {}
                        turn_index = 0

            # Flush remaining messages as the last conversation
            if current_messages:
                conversations.append(
                    Conversation(
                        messages=current_messages,
                        file_path=str(file_path),
                        project_name=project_name,
                        raw_messages=current_raw,
                    )
                )

        except Exception as e:
            logger.error(f"Error parsing {file_path}: {e}")

        return conversations

    async def parse_file(self, file_path: str) -> list[Conversation]:
        """Parse a single JSONL file into conversations (public async wrapper)."""
        return self._parse_jsonl_file(Path(file_path))

    async def parse_all_logs(
        self,
        project_filter: Optional[str] = None,
        exclude_projects: Optional[list[str]] = None,
    ) -> AsyncIterator[tuple[Path, list[Conversation]]]:
        """Parse JSONL files with optional filtering.

        Args:
            project_filter: Only include this project (partial match on dir name)
            exclude_projects: Exclude these projects (partial match on dir names)
        """
        if not self.logs_path.exists():
            logger.warning(f"Logs path does not exist: {self.logs_path}")
            return

        exclude_projects = exclude_projects or []

        pattern = "**/*.jsonl"
        files_found = list(self.logs_path.glob(pattern))
        logger.info(f"Found {len(files_found)} JSONL files in {self.logs_path}")

        for file_path in files_found:
            # Skip subagent files (they're fragments)
            if "subagents" in str(file_path):
                continue

            project_dir = file_path.parent.name

            if project_filter:
                if project_filter.lower() not in project_dir.lower():
                    continue

            should_exclude = any(
                excl.lower() in project_dir.lower() for excl in exclude_projects
            )
            if should_exclude:
                continue

            file_hash = self._compute_file_hash(file_path)
            if file_hash in self.processed_hashes:
                continue

            conversations = self._parse_jsonl_file(file_path)

            if conversations:
                self.processed_hashes.add(file_hash)
                yield file_path, conversations

    async def preview_logs(
        self,
        project_filter: Optional[str] = None,
        exclude_projects: Optional[list[str]] = None,
        max_conversations: int = 10,
    ) -> list[dict]:
        """Preview what would be imported without actually importing."""
        previews = []
        count = 0

        async for file_path, conversations in self.parse_all_logs(
            project_filter=project_filter,
            exclude_projects=exclude_projects,
        ):
            for conv in conversations:
                if count >= max_conversations:
                    return previews

                previews.append(
                    {
                        "file": str(file_path),
                        "project": conv.project_name,
                        "messages": len(conv.messages),
                        "preview": conv.get_preview(300),
                    }
                )
                count += 1

        return previews

    async def watch_for_changes(self) -> AsyncIterator[tuple[Path, list[Conversation]]]:
        """Watch for new or modified log files."""
        async for result in self.parse_all_logs():
            yield result
