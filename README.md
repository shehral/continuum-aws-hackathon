# Continuum

**AI-powered knowledge graph that captures engineering decisions from human-AI coding sessions using Amazon Bedrock, Strands Agents SDK, and Neo4j.**

AWS Hackathon 2025

---

## The Problem

Every day, engineering teams make hundreds of decisions during AI-assisted coding sessions — choosing libraries, designing architectures, evaluating trade-offs. These decisions vanish when the conversation ends. New team members re-debate settled choices. Rejected alternatives are forgotten. Architectural knowledge lives in people's heads, not in systems.

## The Solution

Continuum uses **Claude Sonnet 4.6 on Amazon Bedrock** to automatically extract structured decision traces from Claude Code conversations, builds a **Neo4j knowledge graph** connecting decisions to code entities, and provides intelligent search and analytics across your codebase.

---

## Demo

### Dashboard & Decision Traces
![Dashboard and Decision Trace](media/dashboard-trace.gif)

### Import from Claude Code Logs
![Import Claude Logs](media/import-logs.gif)

### AI-Guided Interview Capture
![Capture Session](media/capture-session.gif)

### Interactive Knowledge Graph
![Knowledge Graph](media/knowledge-graph.gif)

---

## How It Works

```
Claude Code Logs (.jsonl)
        │
        ▼
┌──────────────────────────────┐
│  Claude Sonnet 4.6           │  Decision extraction & entity
│  (Amazon Bedrock via         │  recognition with confidence
│   Strands Agents SDK)        │  scoring and calibration
└──────────┬───────────────────┘
           │
           ▼
┌──────────────────────────────┐
│  Entity Resolution Engine    │  7-stage deduplication:
│  NVIDIA NV-EmbedQA (2048d)  │  Levenshtein, token overlap,
│                              │  semantic similarity, canonical
│                              │  mappings from PyPI/npm/crates.io
└──────────┬───────────────────┘
           │
           ▼
┌──────────────────────────────┐
│  Neo4j Knowledge Graph       │  Decisions, entities, code files,
│  + PostgreSQL + Redis        │  relationships, evolution chains,
│                              │  git commit links
└──────────┬───────────────────┘
           │
           ▼
┌──────────────────────────────┐
│  Next.js 16 Frontend         │  Graph visualization, search,
│  + MCP Server for Agents     │  analytics, interview capture,
│                              │  chat Q&A, coverage maps
└──────────────────────────────┘
```

---

## Core AWS & AI Integration

### Amazon Bedrock + Claude Sonnet 4.6

Continuum uses **Claude Sonnet 4.6** via Amazon Bedrock as the primary LLM for:

- **Decision Extraction**: Analyzes conversation transcripts and extracts structured decision traces (trigger, context, options, decision, rationale) with confidence scoring
- **Entity Recognition**: Identifies technologies, concepts, patterns, and their relationships within conversations
- **Interview Agent**: Powers a multi-turn AI interviewer that guides users through structured knowledge capture
- **Chat Q&A**: Answers natural language questions about the codebase grounded in the knowledge graph

### Strands Agents SDK

The **Strands Agents SDK** provides the model abstraction layer:

- `BedrockModel` wraps Claude Sonnet 4.6 with the Bedrock ConverseStream API
- `StrandsLLMProviderAdapter` bridges Strands models to Continuum's `BaseLLMProvider` interface
- Handles message format conversion (OpenAI format → Strands content blocks), system prompt extraction, and streaming token delivery
- Same adapter pattern supports `OpenAIModel` for MiniMax integration

```python
# Single env var switches between providers
LLM_PROVIDER=bedrock   # Claude Sonnet 4.6 via Strands BedrockModel
LLM_PROVIDER=minimax   # MiniMax M2.5 via Strands OpenAIModel
LLM_PROVIDER=nvidia    # NVIDIA NIM direct client
```

### MiniMax M2.5

**MiniMax M2.5** serves as an alternative LLM provider via the Strands SDK's `OpenAIModel` with a custom base URL. It uses the same adapter pattern as Bedrock, demonstrating the pluggable provider architecture.

### Neo4j Knowledge Graph

Neo4j stores the core knowledge graph with:

- **Node types**: `DecisionTrace`, `Entity`, `CodeEntity`, `CandidateDecision`
- **Relationship types**: `INVOLVES`, `RELATED_TO`, `DEPENDS_ON`, `SUPERSEDES`, `ALTERNATIVE_TO`, `IMPLEMENTED_BY`, `TOUCHES`
- **Vector index**: `entity_embedding` (2048d, cosine similarity) for semantic search
- **Full-text indexes**: `decision_fulltext`, `entity_fulltext` for lexical search
- **Temporal edges**: `FOLLOWS`, `PRECEDES`, `SUPERSEDES` for decision evolution tracking

### NVIDIA NIM Embeddings

NVIDIA **NV-EmbedQA 1B** (2048 dimensions) provides the embedding backbone for:
- Semantic search across decisions and entities
- Entity resolution via embedding similarity
- BGE reranking of hybrid search results

Embeddings stay on NVIDIA regardless of LLM provider to avoid re-indexing the vector store.

---

## Features

### Knowledge Capture
- **Passive Log Import**: Batch and selective import from Claude Code JSONL logs with real-time progress tracking and file watching
- **AI Interview Agent**: Multi-turn guided capture powered by Sonnet 4.6 — extracts structured decision traces through conversation
- **Decision Traces**: Trigger, context, options, decision, rationale — with confidence scoring and LLM calibration
- **Human Review Queue**: Paginated workflow for reviewing AI-extracted decisions with agree/disagree + human rationale

### Knowledge Graph & Analytics
- **Interactive Graph**: Force-directed visualization with filtering, search, relationship exploration, and source tagging
- **Decision Timeline**: Time-series by day/week/month with scope and type distribution
- **Coverage Map**: File-level heatmap showing knowledge coverage and debt scoring per source file
- **Branch Explorer**: Surfaces rejected alternatives ranked by reconsider score and dormancy period
- **Stale Detection**: Scope-based auto-expiration (strategic: 2y, architectural: 6m, library: 3m, config: 1m) with review workflow
- **Assumption Monitoring**: Automatically flags when new decisions contradict assumptions in existing decisions

### Search & Intelligence
- **Ask Codebase**: Natural language Q&A grounded in the knowledge graph with source citations
- **Hybrid Search**: Full-text + semantic vector search with BGE reranking and score fusion
- **Entity Resolution**: 7-stage deduplication — Levenshtein, token overlap, semantic embeddings, canonical mappings (~530 from PyPI/npm/crates.io)
- **Graph Validation**: Circular dependency detection, orphan nodes, duplicates, relationship consistency

### Developer Tooling
- **Git Commit Linking**: Links commits to decisions via file overlap scoring (Jaccard similarity)
- **PR Context Injection**: Surfaces relevant decisions, contradictions, and stale decisions for PR file changes
- **MCP Server**: Five-tool Model Context Protocol server for AI agents (Claude Code, Cursor) — summary, search, entity lookup, prior art check, decision recording
- **Bulk Export**: JSON, CSV, and Markdown export of decisions and graph data

### Observability
- **Datadog Integration**: Bidirectional — pushes decision events and LLM metrics; reads alerts for assumption violation detection
- **Datadog RUM**: Browser-side Real User Monitoring with session replay
- **LLM Metrics**: Per-call logging of model, tokens, latency, cost to Datadog
- **Real-time Notifications**: REST + WebSocket for contradictions, stale alerts, and dormant alternative flags

### Resilience
- Per-user rate limiting via Redis token buckets
- Circuit breakers for external service calls
- Automatic model fallback (primary → fallback)
- Prompt injection detection and sanitization
- Saga pattern for distributed transactions across Neo4j + PostgreSQL + Redis

---

## Architecture

```
                    ┌───────────────────┐
                    │   Next.js 16 App  │  React 19, TailwindCSS 4
                    │   Port 3000       │  shadcn/ui, Framer Motion
                    └────────┬──────────┘
                             │
                    ┌────────▼──────────┐
                    │  FastAPI Backend   │  15 routers, 20+ services
                    │  Port 8000        │  Strands Agents SDK
                    └──┬─────┬─────┬──┬─┘
                       │     │     │  │
              ┌────────┘  ┌──┘  ┌──┘  └────────┐
              ▼           ▼     ▼              ▼
     ┌────────────┐ ┌─────────┐ ┌─────────┐ ┌─────────────────┐
     │ PostgreSQL │ │  Neo4j  │ │  Redis  │ │  LLM Providers  │
     │ Users,     │ │Knowledge│ │ Cache,  │ │                 │
     │ Sessions   │ │ Graph   │ │ Rate    │ │ Bedrock (Sonnet │
     │ Port 5433  │ │Port 7687│ │ Limits  │ │   4.6)          │
     └────────────┘ └─────────┘ │Port 6380│ │ NVIDIA NIM      │
                                └─────────┘ │ MiniMax M2.5    │
                                            └─────────────────┘
```

---

## Tech Stack

| Layer | Technologies |
|-------|-------------|
| **Frontend** | Next.js 16, React 19, TailwindCSS 4, shadcn/ui, Framer Motion, React Flow |
| **Backend** | FastAPI, SQLAlchemy (async), Pydantic, Strands Agents SDK |
| **Knowledge Graph** | Neo4j 2025.01 (vector + full-text indexes, temporal edges) |
| **Databases** | PostgreSQL 18, Redis 7.4 |
| **Primary LLM** | Amazon Bedrock — Claude Sonnet 4.6 (via Strands BedrockModel) |
| **Alternative LLMs** | MiniMax M2.5 (via Strands OpenAIModel), NVIDIA NIM (Llama 3.3 Nemotron) |
| **Embeddings** | NVIDIA NV-EmbedQA 1B (2048d) + BGE Reranker v2-m3 |
| **Observability** | Datadog (RUM + Logs + LLM Metrics) |
| **Auth** | Auth.js v5 (next-auth), JWT with multi-tenant isolation |
| **Infrastructure** | Docker Compose, Kubernetes manifests, GitHub Actions CI/CD |

---

## Quick Start

### Prerequisites

- Docker & Docker Compose
- Node.js 24+ / pnpm
- Python 3.12+
- AWS credentials with Bedrock access (Claude Sonnet 4.6)

### 1. Clone and configure

```bash
git clone https://github.com/shehral/continuum-aws-hackathon.git
cd continuum-aws-hackathon

cp apps/api/.env.example apps/api/.env
cp apps/web/.env.example apps/web/.env.local
```

Edit `apps/api/.env`:

```bash
LLM_PROVIDER=bedrock
BEDROCK_MODEL_ID=us.anthropic.claude-sonnet-4-6
AWS_REGION=us-west-2
```

### 2. Start databases

```bash
docker compose up -d
# Starts PostgreSQL (5433), Neo4j (7687), Redis (6380)
```

### 3. Start the API

```bash
cd apps/api
python3 -m venv .venv && .venv/bin/pip install -r requirements.txt
pip install strands-agents strands-agents-tools

# Export AWS credentials
export AWS_ACCESS_KEY_ID="..."
export AWS_SECRET_ACCESS_KEY="..."
export AWS_SESSION_TOKEN="..."  # if using temporary credentials

.venv/bin/uvicorn main:app --reload --port 8000
```

### 4. Start the web app

```bash
cd apps/web
pnpm install && pnpm dev
```

### 5. Open

- **App**: http://localhost:3000
- **API Docs**: http://localhost:8000/docs
- **Neo4j Browser**: http://localhost:7474

---

## Project Structure

```
continuum-aws-hackathon/
├── apps/
│   ├── api/                    # FastAPI backend
│   │   ├── agents/             # Interview agent (Sonnet 4.6)
│   │   ├── routers/            # 15 API routers
│   │   ├── services/           # 20+ services
│   │   │   ├── llm_providers/  # Bedrock, NVIDIA, MiniMax, Strands adapter
│   │   │   ├── extractor.py    # Decision extraction via LLM
│   │   │   ├── entity_resolver.py  # 7-stage entity resolution
│   │   │   ├── parser.py       # Claude Code JSONL parser
│   │   │   └── datadog_*.py    # Datadog integration
│   │   ├── evaluation/         # Model comparison & benchmarks
│   │   └── tests/              # 838+ tests
│   ├── web/                    # Next.js 16 frontend
│   │   ├── app/                # 15 pages
│   │   ├── components/
│   │   │   ├── landing/        # Hero animations
│   │   │   ├── graph/          # Knowledge graph (React Flow)
│   │   │   ├── capture/        # Interview chat
│   │   │   └── chat/           # Ask Codebase Q&A
│   │   └── lib/                # API client, Datadog RUM
│   └── mcp/                    # MCP server for AI agents
├── k8s/                        # Kubernetes manifests
├── docker-compose.yml          # Local dev stack
└── media/                      # Demo GIFs
```

---

## Third-Party Services

- [Amazon Bedrock](https://aws.amazon.com/bedrock/) — Claude Sonnet 4.6 LLM inference
- [Strands Agents SDK](https://strandsagents.com/) — Model provider abstraction
- [MiniMax](https://www.minimax.io/) — MiniMax M2.5 alternative LLM
- [NVIDIA NIM](https://developer.nvidia.com/) — Embeddings (NV-EmbedQA) and alternative LLM (Llama 3.3 Nemotron)
- [Datadog](https://www.datadoghq.com/) — Observability, RUM, LLM metrics
- [Neo4j](https://neo4j.com/) — Knowledge graph database
- [Claude Code](https://claude.ai/) — Source conversation format

---

## License

All rights reserved. See [LICENSE](./LICENSE) for details.

---

*Built by Ali Shehral (shehral.m@northeastern.edu) — Northeastern University, HCAI Lab*
