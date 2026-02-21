"""Application configuration with secure handling of sensitive values (SEC-007)."""

from functools import lru_cache

from pydantic import SecretStr, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Application settings with secure secret handling.

    SEC-007: Sensitive fields use SecretStr to prevent accidental exposure
    in logs, error messages, or repr() output.
    """

    # Database - all credentials must be set via environment variables
    database_url: str = ""  # e.g., postgresql+asyncpg://user:pass@localhost:5432/dbname

    @field_validator("database_url", mode="after")
    @classmethod
    def ensure_asyncpg_driver(cls, v: str) -> str:
        """Convert postgresql:// to postgresql+asyncpg:// for async support."""
        if v.startswith("postgresql://"):
            return v.replace("postgresql://", "postgresql+asyncpg://", 1)
        return v

    neo4j_uri: str = (
        ""  # e.g., bolt://localhost:7687 or neo4j+s://xxx.databases.neo4j.io
    )
    neo4j_user: str = ""
    neo4j_password: SecretStr = SecretStr("")  # SEC-007: Use SecretStr for passwords
    redis_url: str = ""  # e.g., redis://localhost:6379

    # Provider selection
    llm_provider: str = "nvidia"  # "nvidia", "bedrock", or "minimax"
    embedding_provider: str = "nvidia"  # "nvidia" or "bedrock" (keep nvidia to avoid re-indexing)

    # AI Provider (NVIDIA NIM) - SEC-007: Use SecretStr for API keys
    nvidia_api_key: SecretStr = SecretStr("")
    nvidia_model: str = "nvidia/llama-3.3-nemotron-super-49b-v1.5"
    
    # Model comparison settings (for RQ1.3 cross-model evaluation)
    # Available NVIDIA models for comparison:
    # - nvidia/llama-3.3-nemotron-super-49b-v1.5 (default)
    # - qwen/qwen3-next-80b-a3b-instruct
    # - qwen/qwen3-coder-480b-a35b-instruct
    # - deepseek-ai/deepseek-v3.1
    nvidia_models_for_comparison: list[str] = [
        "nvidia/llama-3.3-nemotron-super-49b-v1.5",
        "qwen/qwen3-next-80b-a3b-instruct",
        "qwen/qwen3-coder-480b-a35b-instruct",
        "deepseek-ai/deepseek-v3.1",
    ]
    # Enable model comparison mode (runs extraction on all models)
    model_comparison_enabled: bool = False

    # Amazon Bedrock settings (used when llm_provider="bedrock")
    bedrock_model_id: str = "anthropic.claude-sonnet-4-20250514"
    bedrock_embedding_model_id: str = "amazon.titan-embed-text-v2:0"
    aws_region: str = "us-west-2"

    # MiniMax settings (used when llm_provider="minimax")
    minimax_api_key: SecretStr = SecretStr("")
    minimax_model_id: str = "MiniMax-M2.5"
    minimax_base_url: str = "https://api.minimax.io/v1"

    # Datadog observability
    dd_trace_enabled: bool = False
    datadog_api_key: SecretStr = SecretStr("")  # SEC-007: Use SecretStr for API keys
    datadog_app_key: SecretStr = SecretStr("")  # Optional, for some Datadog APIs
    datadog_site: str = "datadoghq.com"  # or "dtraining.datadoghq.com" for training
    datadog_integration_enabled: bool = False  # Enable/disable Datadog log shipping

    # Embedding Model (NVIDIA NV-EmbedQA) - SEC-007: Use SecretStr for API keys
    nvidia_embedding_api_key: SecretStr = SecretStr("")
    nvidia_embedding_model: str = "nvidia/llama-3.2-nv-embedqa-1b-v2"

    # Embedding cache settings (ML-P1-2)
    embedding_cache_ttl: int = 86400 * 30  # 30 days in seconds
    embedding_cache_min_text_length: int = 10  # Minimum text length to cache
    # SD-QW-002: Embedding batch size for bulk operations
    # Tradeoff: Larger batches = fewer API calls but more memory per request
    # NVIDIA NIM embedding API supports up to ~256 texts per batch
    # Default 32 balances throughput with memory usage and rate limit (30 req/min)
    embedding_batch_size: int = 32

    # Rate limiting
    rate_limit_requests: int = 30  # requests per minute
    rate_limit_window: int = 60  # seconds

    # LLM retry settings (ML-P0-1)
    llm_max_retries: int = 3  # Maximum retry attempts for LLM calls
    llm_retry_base_delay: float = 1.0  # Base delay in seconds for exponential backoff

    # LLM prompt size limits (ML-P1-3) — model-aware (Part 13)
    # Context limits per model (85% of actual limit to leave room for response)
    _MODEL_CONTEXT_LIMITS: dict = {
        "nvidia/llama-3.3-nemotron-super-49b-v1.5": 128000,
        "nvidia/llama-3.1-nemotron-70b-instruct": 131072,
        "qwen/qwen3-next-80b-a3b-instruct": 131072,
        "qwen/qwen3-coder-480b-a35b-instruct": 131072,
        "deepseek-ai/deepseek-v3.1": 131072,
    }
    max_prompt_tokens: int = 70000  # Default fallback; overridden by model-aware logic at runtime

    @property
    def effective_max_prompt_tokens(self) -> int:
        """Model-aware max_prompt_tokens — 85% of actual model context limit."""
        limit = self._MODEL_CONTEXT_LIMITS.get(self.nvidia_model, 82000)
        return int(limit * 0.85)
    prompt_warning_threshold: float = 0.8  # Warn when prompt exceeds this % of max

    # LLM response cache settings (KG-P0-2)
    llm_cache_enabled: bool = True  # Enable/disable LLM response caching
    llm_cache_ttl: int = 86400  # 24 hours in seconds (default)
    llm_extraction_prompt_version: str = (
        "v1"  # Bump when prompts change to invalidate cache
    )
    # LLM model fallback settings (ML-QW-2)
    # If primary model fails, fall back to a secondary model
    llm_fallback_model: str = "nvidia/llama-3.1-nemotron-70b-instruct"  # Fallback model
    llm_fallback_enabled: bool = True  # Enable/disable fallback behavior
    
    # Confidence calibration settings (RQ1.2 + Part 2e)
    # Method: "composite" (data-driven, no ground truth), "temperature" (Temperature Scaling), "heuristic"
    confidence_calibration_method: str = "composite"  # Default to composite (Part 2e)
    confidence_calibration_temperature: float = 1.5  # Temperature parameter for temperature method
    
    # Verbatim grounding settings (CogCanvas-inspired)
    verbatim_grounding_enabled: bool = True  # Store exact text quotes with offsets
    verbatim_store_offsets: bool = True  # Store character offsets and turn indices
    
    # Temporal reasoning settings
    temporal_reasoning_enabled: bool = True  # Track turn indices and temporal relationships
    temporal_edge_types: list[str] = ["FOLLOWS", "PRECEDES", "SUPERSEDES"]  # Temporal relationship types
    
    # BGE reranking settings (CogCanvas)
    bge_reranking_enabled: bool = True  # Enable BGE reranking for search results
    bge_reranker_model: str = "BAAI/bge-reranker-v2-m3"  # BGE reranker model
    bge_reranking_top_k: int = 20  # Rerank top-K candidates before returning
    
    # Evaluation settings (RQ1)
    evaluation_metrics_enabled: bool = True  # Enable evaluation metrics collection
    evaluation_ground_truth_path: str = ""  # Path to ground truth dataset (optional)

    # Entity cache settings (SD-011)
    entity_cache_ttl: int = 300  # 5 minutes in seconds
    entity_cache_enabled: bool = True

    # Message batch settings (SD-010)
    message_batch_size: int = 10  # Flush after N messages
    message_batch_timeout: float = 2.0  # Flush after N seconds

    # Similarity thresholds (KG-P2-2: Configurable thresholds)
    # Decision similarity (ML-P1-4)
    similarity_threshold: float = 0.85  # Minimum similarity for SIMILAR_TO edges
    high_confidence_similarity_threshold: float = 0.90  # For high-confidence matches
    # Entity resolution thresholds
    fuzzy_match_threshold: float = (
        0.85  # Fuzzy string matching threshold (0-1 scale, 85%)
    )
    embedding_similarity_threshold: float = (
        0.90  # Embedding cosine similarity threshold
    )

    # Decision embedding field weights (KG-P1-5)
    # Higher weights increase importance in semantic search
    decision_embedding_weight_title: float = 1.5  # Title gets 1.5x weight
    decision_embedding_weight_decision: float = 1.2  # Decision field gets 1.2x weight
    decision_embedding_weight_rationale: float = 1.0  # Rationale gets base weight
    decision_embedding_weight_context: float = 0.8  # Context gets 0.8x weight
    decision_embedding_weight_trigger: float = 0.8  # Trigger gets 0.8x weight

    # Paths
    claude_logs_path: str = "~/.claude/projects"

    # Repository path for codebase connectivity (Part 3b / 4.1 / 4.6)
    # Set this to the root of the project being tracked.
    # If empty, file entity grounding and git integration are gracefully skipped.
    repo_path: str = ""

    # Git integration settings (Part 4.2 / 4.6)
    git_commit_link_window_hours: int = 2       # Look N hours after session for commits
    git_commit_link_score_threshold: float = 0.3  # Min file-overlap score to create IMPLEMENTED_BY
    git_stale_file_threshold_days: int = 90     # Files not modified in N days are "stale"
    episode_gap_minutes: float = 10.0           # Minutes between messages to split episodes

    # Datadog integration (Part 12) — opt-in, disabled by default
    datadog_api_key: SecretStr = SecretStr("")
    datadog_app_key: SecretStr = SecretStr("")
    datadog_site: str = "datadoghq.com"
    datadog_integration_enabled: bool = False

    # Auth - SEC-007: Use SecretStr for secret key
    secret_key: SecretStr = SecretStr("")
    algorithm: str = "HS256"
    access_token_expire_minutes: int = 30

    # App
    debug: bool = False
    cors_origins: list[str] = ["http://localhost:3000"]

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    def __repr__(self) -> str:
        """Custom repr that masks sensitive values (SEC-007)."""
        # Only show non-sensitive fields in repr
        safe_fields = {
            "database_url": self._mask_url(self.database_url),
            "neo4j_uri": self.neo4j_uri,
            "neo4j_user": self.neo4j_user,
            "redis_url": self._mask_url(self.redis_url),
            "nvidia_model": self.nvidia_model,
            "nvidia_embedding_model": self.nvidia_embedding_model,
            "rate_limit_requests": self.rate_limit_requests,
            "max_prompt_tokens": self.max_prompt_tokens,
            "claude_logs_path": self.claude_logs_path,
            "algorithm": self.algorithm,
            "debug": self.debug,
            "cors_origins": self.cors_origins,
        }
        fields_str = ", ".join(f"{k}={v!r}" for k, v in safe_fields.items())
        return f"Settings({fields_str})"

    @staticmethod
    def _mask_url(url: str) -> str:
        """Mask password in database URLs."""
        if not url:
            return url
        # Simple masking for URLs with passwords
        import re

        return re.sub(r":([^:@]+)@", ":***@", url)

    def get_nvidia_api_key(self) -> str:
        """Safely get NVIDIA API key value."""
        return self.nvidia_api_key.get_secret_value()

    def get_nvidia_embedding_api_key(self) -> str:
        """Safely get NVIDIA embedding API key value."""
        return self.nvidia_embedding_api_key.get_secret_value()

    def get_minimax_api_key(self) -> str:
        """Safely get MiniMax API key value."""
        return self.minimax_api_key.get_secret_value()

    def get_secret_key(self) -> str:
        """Safely get JWT secret key value."""
        return self.secret_key.get_secret_value()

    def get_neo4j_password(self) -> str:
        """Safely get Neo4j password value."""
        return self.neo4j_password.get_secret_value()

    def get_datadog_api_key(self) -> str:
        """Safely get Datadog API key value."""
        return self.datadog_api_key.get_secret_value()

    def get_datadog_app_key(self) -> str:
        """Safely get Datadog application key value."""
        return self.datadog_app_key.get_secret_value()


@lru_cache
def get_settings() -> Settings:
    return Settings()
