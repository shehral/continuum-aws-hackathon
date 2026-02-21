"""Markdown exporter for conversations and decisions (SpecStory-inspired, Phase 4).

Exports conversations and decision traces as versioned markdown files,
enabling git-friendly knowledge capture.
"""

from datetime import datetime
from pathlib import Path
from typing import Any

from config import get_settings
from services.parser import Conversation
from utils.logging import get_logger

logger = get_logger(__name__)


class MarkdownExporter:
    """Export conversations and decisions as markdown (SpecStory pattern)."""

    def __init__(self, output_dir: str | None = None):
        """Initialize markdown exporter.
        
        Args:
            output_dir: Output directory for markdown files (default: .continuum/specs/)
        """
        settings = get_settings()
        if output_dir is None:
            output_dir = ".continuum/specs"
        
        self.output_dir = Path(output_dir).expanduser()
        self.output_dir.mkdir(parents=True, exist_ok=True)

    def export_conversation(
        self,
        conversation: Conversation,
        include_decisions: bool = True,
        decisions: list[dict[str, Any]] | None = None,
    ) -> Path:
        """Export conversation as markdown file.
        
        Args:
            conversation: Conversation to export
            include_decisions: Whether to include extracted decisions inline
            decisions: Optional list of decision dicts to include
            
        Returns:
            Path to exported markdown file
        """
        # Create project directory
        project_dir = self.output_dir / conversation.project_name
        project_dir.mkdir(parents=True, exist_ok=True)
        
        # Generate filename with timestamp
        timestamp = conversation.timestamp.strftime("%Y%m%d-%H%M%S")
        filename = f"{timestamp}.md"
        filepath = project_dir / filename
        
        # Build markdown content
        lines = [
            f"# Conversation: {conversation.project_name}",
            "",
            f"**Date**: {conversation.timestamp.strftime('%Y-%m-%d %H:%M:%S')}",
            f"**Source**: {conversation.file_path}",
            "",
            "---",
            "",
            "## Conversation",
            "",
        ]
        
        # Add conversation turns
        for i, msg in enumerate(conversation.messages):
            role = msg.get("role", "unknown")
            content = msg.get("content", "")
            
            lines.append(f"### Turn {i}: {role.title()}")
            lines.append("")
            
            # Format code blocks if present
            if "```" in content:
                lines.append(content)
            else:
                # Regular text
                lines.append(content)
            
            lines.append("")
        
        # Add extracted decisions if available
        if include_decisions and decisions:
            lines.extend([
                "---",
                "",
                "## Extracted Decisions",
                "",
            ])
            
            for i, decision in enumerate(decisions, 1):
                lines.extend([
                    f"### Decision {i}",
                    "",
                    f"**Trigger**: {decision.get('trigger', 'N/A')}",
                    "",
                    f"**Context**: {decision.get('context', 'N/A')}",
                    "",
                    f"**Options Considered**:",
                ])
                
                for opt in decision.get("options", []):
                    lines.append(f"- {opt}")
                
                lines.extend([
                    "",
                    f"**Decision**: {decision.get('decision', 'N/A')}",
                    "",
                    f"**Rationale**: {decision.get('rationale', 'N/A')}",
                    "",
                    f"**Confidence**: {decision.get('confidence', 0.0):.2f}",
                    "",
                ])
                
                # Add verbatim quotes if available
                verbatim_decision = decision.get("verbatim_decision")
                if verbatim_decision:
                    lines.extend([
                        f"**Verbatim Quote**:",
                        "",
                        f"> {verbatim_decision}",
                        "",
                    ])
                
                lines.append("---")
                lines.append("")
        
        # Write to file
        content = "\n".join(lines)
        filepath.write_text(content, encoding="utf-8")
        
        logger.info(f"Exported conversation to {filepath}")
        return filepath

    def export_decisions_log(
        self,
        project_name: str,
        decisions: list[dict[str, Any]],
    ) -> Path:
        """Export decision traces as structured markdown log.
        
        Creates a DECISIONS.md file in the project directory.
        
        Args:
            project_name: Project name
            decisions: List of decision dicts
            
        Returns:
            Path to DECISIONS.md file
        """
        project_dir = self.output_dir / project_name
        project_dir.mkdir(parents=True, exist_ok=True)
        
        filepath = project_dir / "DECISIONS.md"
        
        lines = [
            f"# Decisions: {project_name}",
            "",
            f"*Last updated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}*",
            "",
            "---",
            "",
        ]
        
        for i, decision in enumerate(decisions, 1):
            lines.extend([
                f"## Decision {i}",
                "",
                f"### {decision.get('decision', 'N/A')}",
                "",
                f"**Trigger**: {decision.get('trigger', 'N/A')}",
                "",
                f"**Context**: {decision.get('context', 'N/A')}",
                "",
                "**Options Considered**:",
            ])
            
            for opt in decision.get("options", []):
                lines.append(f"- {opt}")
            
            lines.extend([
                "",
                f"**Rationale**: {decision.get('rationale', 'N/A')}",
                "",
                f"**Confidence**: {decision.get('confidence', 0.0):.2f}",
                "",
            ])
            
            # Add temporal information if available
            turn_index = decision.get("turn_index")
            if turn_index is not None:
                lines.append(f"**Turn Index**: {turn_index}")
                lines.append("")
            
            # Add verbatim quotes
            verbatim_decision = decision.get("verbatim_decision")
            if verbatim_decision:
                lines.extend([
                    "**Verbatim Quote**:",
                    "",
                    f"> {verbatim_decision}",
                    "",
                ])
            
            lines.append("---")
            lines.append("")
        
        content = "\n".join(lines)
        filepath.write_text(content, encoding="utf-8")
        
        logger.info(f"Exported decisions log to {filepath}")
        return filepath
