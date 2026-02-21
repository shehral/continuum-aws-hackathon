# Continuum API

FastAPI backend for the Continuum knowledge management platform.

## Setup

```bash
# Create virtual environment
python3 -m venv .venv

# Activate virtual environment
source .venv/bin/activate  # On macOS/Linux
# or
.venv\Scripts\activate     # On Windows

# Install dependencies
pip install -e ".[dev]"
```

## Running

```bash
# From project root (uses venv automatically)
pnpm dev:api

# Or manually
cd apps/api
.venv/bin/uvicorn main:app --reload --port 8000
```

## API Documentation

Visit http://localhost:8000/docs for interactive Swagger documentation.

## Endpoints

### Dashboard
- `GET /api/dashboard/stats` - Get dashboard statistics

### Decisions
- `GET /api/decisions` - List all decisions
- `GET /api/decisions/{id}` - Get single decision
- `DELETE /api/decisions/{id}` - Delete a decision

### Entities
- `GET /api/entities` - List all entities
- `GET /api/entities/{id}` - Get single entity
- `DELETE /api/entities/{id}` - Delete an entity
  - Query param: `force=true` to delete entities with relationships

### Graph
- `GET /api/graph` - Get full knowledge graph
  - Query params: `include_similarity`, `include_temporal`, `include_entity_relations`
- `GET /api/graph/stats` - Get graph statistics
- `GET /api/graph/sources` - Get list of source files
- `GET /api/graph/validate` - Run validation checks

### Search
- `GET /api/search?query={term}` - Search decisions and entities (case-insensitive)

### Capture
- `POST /api/capture/sessions` - Start a new capture session
- `GET /api/capture/sessions/{id}` - Get session details
- `WebSocket /api/capture/sessions/{id}/ws` - Real-time capture streaming

### Ingest
- `POST /api/ingest/trigger` - Trigger Claude Code log ingestion

## Project Structure

```
apps/api/
├── main.py                 # FastAPI app entry point
├── config.py               # Settings (NVIDIA API keys, database URLs)
├── routers/               # API route handlers
│   ├── decisions.py       # Decision CRUD
│   ├── entities.py        # Entity CRUD
│   ├── graph.py           # Graph queries
│   ├── search.py          # Search functionality
│   ├── capture.py         # Capture sessions
│   └── ingest.py          # Log ingestion
├── services/              # Business logic
│   ├── llm.py             # NVIDIA NIM LLM client
│   ├── embeddings.py      # NVIDIA NV-EmbedQA client
│   ├── extractor.py       # Decision extraction (CoT prompts)
│   ├── entity_resolver.py # Entity deduplication (7-stage)
│   ├── validator.py       # Graph validation
│   └── decision_analyzer.py # Relationship detection
├── models/                # Data models
│   ├── database.py        # SQLAlchemy models
│   └── ontology.py        # Entity/Relationship types
├── db/                    # Database connections
│   ├── postgres.py        # PostgreSQL (SQLAlchemy async)
│   └── neo4j.py           # Neo4j driver
├── agents/                # AI agents
│   └── interview.py       # Interview agent (NVIDIA Llama)
└── tests/                 # Test suite
    └── test_e2e.py        # E2E tests (31 tests)
```

## Testing

```bash
# Run all tests
.venv/bin/pytest tests/ -v

# Run with coverage
.venv/bin/pytest tests/ -v --cov=.

# Run specific test file
.venv/bin/pytest tests/test_e2e.py -v
```

## AI Services

### LLM Client (`services/llm.py`)

NVIDIA NIM API client for text generation:

- **Model**: `nvidia/llama-3.3-nemotron-super-49b-v1.5`
- **Base URL**: `https://integrate.api.nvidia.com/v1`
- **Rate Limiting**: Redis token bucket (30 req/min)
- **Thinking Tags**: Automatically strips `<think>...</think>` from output
- **Streaming**: Supports async streaming for WebSocket

```python
from services.llm import get_llm_client

llm = get_llm_client()
response = await llm.generate("Your prompt here")
```

### Embedding Service (`services/embeddings.py`)

NVIDIA NV-EmbedQA for semantic embeddings:

- **Model**: `nvidia/llama-3.2-nv-embedqa-1b-v2`
- **Dimensions**: 2048
- **Input Types**: "query" for searches, "passage" for documents

```python
from services.embeddings import get_embedding_service

embeddings = get_embedding_service()
vector = await embeddings.embed_text("Your text here")
```

### Entity Resolution (`services/entity_resolver.py`)

7-stage pipeline for entity deduplication:

1. **Exact match** - Case-insensitive name lookup
2. **Canonical lookup** - Map aliases (postgres → PostgreSQL)
3. **Alias search** - Check entity aliases field
4. **Fuzzy match** - rapidfuzz with 85% threshold
5. **Embedding similarity** - Cosine similarity > 0.9

### Extractor (`services/extractor.py`)

Decision extraction using NVIDIA LLM with few-shot Chain-of-Thought prompts:

- Entity extraction with reasoning
- Relationship extraction between entities
- Decision-decision relationship detection (SUPERSEDES, CONTRADICTS)

### Validator (`services/validator.py`)

Graph validation checks:

- Circular dependency detection
- Orphan entity detection
- Low confidence relationship flagging
- Duplicate entity detection

## Configuration

Environment variables (in `.env` or `config.py` defaults):

```bash
# NVIDIA AI
NVIDIA_API_KEY=nvapi-...                    # LLM API key
NVIDIA_EMBEDDING_API_KEY=nvapi-...          # Embedding API key
NVIDIA_MODEL=nvidia/llama-3.3-nemotron-super-49b-v1.5
NVIDIA_EMBEDDING_MODEL=nvidia/llama-3.2-nv-embedqa-1b-v2

# Rate limiting
RATE_LIMIT_REQUESTS=30                      # requests per minute
RATE_LIMIT_WINDOW=60                        # seconds

# Databases
DATABASE_URL=postgresql+asyncpg://...
NEO4J_URI=bolt://localhost:7687
REDIS_URL=redis://localhost:6379
```

## Dependencies

Key Python packages:
- `fastapi` - Web framework
- `uvicorn` - ASGI server
- `sqlalchemy[asyncio]` - Async ORM
- `neo4j` - Graph database driver
- `openai` - AsyncOpenAI client (for NVIDIA NIM API)
- `redis` - Rate limiting and caching
- `rapidfuzz` - Fuzzy string matching
- `httpx` - HTTP client
- `pytest` - Testing framework
