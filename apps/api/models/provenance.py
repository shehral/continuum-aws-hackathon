"""Provenance tracking models for knowledge graph data (KG-P2-4).

Tracks the origin and extraction metadata for each piece of information
in the knowledge graph, enabling:
- Data lineage tracking
- Confidence calibration based on source quality
- Audit trails for compliance
- Quality assessment and debugging
"""

from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import Enum
from typing import Optional


class ExtractionMethod(Enum):
    """Method used to extract information (KG-P2-4)."""

    LLM_EXTRACTION = "llm_extraction"  # Extracted via LLM prompt
    PATTERN_MATCHING = "pattern_matching"  # Extracted via regex/rules
    MANUAL_ENTRY = "manual_entry"  # User manually entered
    ENTITY_RESOLUTION = "entity_resolution"  # Created during resolution
    INFERENCE = "inference"  # Inferred from other data
    IMPORT = "import"  # Imported from external source


class SourceType(Enum):
    """Type of source the information came from (KG-P2-4)."""

    CLAUDE_LOG = "claude_log"  # Claude Code conversation log
    INTERVIEW = "interview"  # AI-guided interview session
    MANUAL = "manual"  # Manual user input
    API_IMPORT = "api_import"  # Imported via API
    FILE_UPLOAD = "file_upload"  # Uploaded document
    EXTERNAL = "external"  # External system integration


@dataclass
class SourceReference:
    """Reference to the original source of information (KG-P2-4).

    Provides detailed lineage information for audit and debugging.
    """

    # Source identification
    source_type: SourceType
    source_id: Optional[str] = None  # UUID of source (e.g., session_id, file_id)
    source_path: Optional[str] = None  # File path if applicable

    # Location within source
    line_start: Optional[int] = None  # Starting line number
    line_end: Optional[int] = None  # Ending line number
    message_index: Optional[int] = None  # Index within conversation

    # Timestamps
    source_timestamp: Optional[datetime] = None  # When source was created
    extraction_timestamp: datetime = field(default_factory=lambda: datetime.now(UTC))

    # Additional context
    snippet: Optional[str] = None  # Relevant text snippet (truncated)

    def to_dict(self) -> dict:
        """Convert to dictionary for storage."""
        return {
            "source_type": self.source_type.value,
            "source_id": self.source_id,
            "source_path": self.source_path,
            "line_start": self.line_start,
            "line_end": self.line_end,
            "message_index": self.message_index,
            "source_timestamp": self.source_timestamp.isoformat()
            if self.source_timestamp
            else None,
            "extraction_timestamp": self.extraction_timestamp.isoformat(),
            "snippet": self.snippet[:500]
            if self.snippet
            else None,  # Limit snippet size
        }

    @classmethod
    def from_dict(cls, data: dict) -> "SourceReference":
        """Create from dictionary."""
        return cls(
            source_type=SourceType(data.get("source_type", "manual")),
            source_id=data.get("source_id"),
            source_path=data.get("source_path"),
            line_start=data.get("line_start"),
            line_end=data.get("line_end"),
            message_index=data.get("message_index"),
            source_timestamp=datetime.fromisoformat(data["source_timestamp"])
            if data.get("source_timestamp")
            else None,
            extraction_timestamp=datetime.fromisoformat(data["extraction_timestamp"])
            if data.get("extraction_timestamp")
            else datetime.now(UTC),
            snippet=data.get("snippet"),
        )


@dataclass
class ExtractionMetadata:
    """Metadata about how information was extracted (KG-P2-4).

    Tracks extraction quality metrics for confidence calibration.
    """

    # Extraction method
    method: ExtractionMethod

    # Model/version info
    model_name: Optional[str] = None  # LLM model used
    model_version: Optional[str] = None  # Model version
    prompt_version: Optional[str] = None  # Prompt template version

    # Confidence scores (per-field where applicable)
    overall_confidence: float = 0.8
    field_confidences: dict[str, float] = field(default_factory=dict)

    # Quality indicators
    extraction_duration_ms: Optional[int] = None  # How long extraction took
    input_token_count: Optional[int] = None  # Tokens in input
    output_token_count: Optional[int] = None  # Tokens in output
    retry_count: int = 0  # Number of retries needed

    # Validation results
    validation_passed: bool = True
    validation_warnings: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        """Convert to dictionary for storage."""
        return {
            "method": self.method.value,
            "model_name": self.model_name,
            "model_version": self.model_version,
            "prompt_version": self.prompt_version,
            "overall_confidence": self.overall_confidence,
            "field_confidences": self.field_confidences,
            "extraction_duration_ms": self.extraction_duration_ms,
            "input_token_count": self.input_token_count,
            "output_token_count": self.output_token_count,
            "retry_count": self.retry_count,
            "validation_passed": self.validation_passed,
            "validation_warnings": self.validation_warnings,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "ExtractionMetadata":
        """Create from dictionary."""
        return cls(
            method=ExtractionMethod(data.get("method", "llm_extraction")),
            model_name=data.get("model_name"),
            model_version=data.get("model_version"),
            prompt_version=data.get("prompt_version"),
            overall_confidence=data.get("overall_confidence", 0.8),
            field_confidences=data.get("field_confidences", {}),
            extraction_duration_ms=data.get("extraction_duration_ms"),
            input_token_count=data.get("input_token_count"),
            output_token_count=data.get("output_token_count"),
            retry_count=data.get("retry_count", 0),
            validation_passed=data.get("validation_passed", True),
            validation_warnings=data.get("validation_warnings", []),
        )


@dataclass
class Provenance:
    """Complete provenance information for a piece of data (KG-P2-4).

    Combines source reference and extraction metadata for full lineage.
    """

    source: SourceReference
    extraction: ExtractionMetadata

    # Who created this
    created_by: Optional[str] = None  # User ID or system identifier

    # Modification tracking
    last_modified_by: Optional[str] = None
    last_modified_at: Optional[datetime] = None
    modification_count: int = 0

    def to_dict(self) -> dict:
        """Convert to dictionary for storage."""
        return {
            "source": self.source.to_dict(),
            "extraction": self.extraction.to_dict(),
            "created_by": self.created_by,
            "last_modified_by": self.last_modified_by,
            "last_modified_at": self.last_modified_at.isoformat()
            if self.last_modified_at
            else None,
            "modification_count": self.modification_count,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "Provenance":
        """Create from dictionary."""
        return cls(
            source=SourceReference.from_dict(data.get("source", {})),
            extraction=ExtractionMetadata.from_dict(data.get("extraction", {})),
            created_by=data.get("created_by"),
            last_modified_by=data.get("last_modified_by"),
            last_modified_at=datetime.fromisoformat(data["last_modified_at"])
            if data.get("last_modified_at")
            else None,
            modification_count=data.get("modification_count", 0),
        )


def create_llm_provenance(
    source_type: SourceType,
    source_id: Optional[str] = None,
    source_path: Optional[str] = None,
    model_name: Optional[str] = None,
    prompt_version: Optional[str] = None,
    confidence: float = 0.8,
    created_by: Optional[str] = None,
    snippet: Optional[str] = None,
    message_index: Optional[int] = None,
) -> Provenance:
    """Factory function to create provenance for LLM-extracted data (KG-P2-4).

    Args:
        source_type: Type of source (CLAUDE_LOG, INTERVIEW, etc.)
        source_id: Unique identifier for the source
        source_path: File path if applicable
        model_name: Name of the LLM model used
        prompt_version: Version of the prompt template
        confidence: Overall confidence score
        created_by: User or system that created this
        snippet: Relevant text snippet from source
        message_index: Index within conversation if applicable

    Returns:
        Provenance object with full lineage information
    """
    return Provenance(
        source=SourceReference(
            source_type=source_type,
            source_id=source_id,
            source_path=source_path,
            message_index=message_index,
            snippet=snippet,
        ),
        extraction=ExtractionMetadata(
            method=ExtractionMethod.LLM_EXTRACTION,
            model_name=model_name,
            prompt_version=prompt_version,
            overall_confidence=confidence,
        ),
        created_by=created_by,
    )


def create_manual_provenance(
    created_by: str,
    source_type: SourceType = SourceType.MANUAL,
) -> Provenance:
    """Factory function to create provenance for manually entered data (KG-P2-4).

    Args:
        created_by: User ID who entered the data
        source_type: Type of manual source

    Returns:
        Provenance object for manual entry
    """
    return Provenance(
        source=SourceReference(
            source_type=source_type,
        ),
        extraction=ExtractionMetadata(
            method=ExtractionMethod.MANUAL_ENTRY,
            overall_confidence=1.0,  # Manual entry assumed high confidence
        ),
        created_by=created_by,
    )
