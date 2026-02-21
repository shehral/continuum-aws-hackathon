# Continuum

**A knowledge graph for capturing engineering decisions from human-AI coding sessions**

> 🔬 Research project in development
> ⚠️ **This project is not yet ready for public use. Please do not fork or redistribute.**

---

## Overview

Continuum automatically extracts decision traces from AI-assisted coding conversations and visualizes them as an interactive knowledge graph. It transforms ephemeral human-AI collaboration into structured, searchable knowledge.

### Research Context

This project explores human-AI collaboration patterns in software engineering—specifically how decisions are made, communicated, and can be preserved during AI-assisted development.

**Project Lead**: Ali Shehral (shehral.m@northeastern.edu)

**Affiliation**: HCAI Lab, Northeastern University

**Status**: Active Development

---

## Demo

### Dashboard & Decision Traces
View recent decisions, analytics, and explore individual decision traces with full context.

![Dashboard and Decision Trace](media/dashboard-trace.gif)

### Knowledge Graph (Sample Data)
Explore the graph structure with sample decisions before importing your own data.

![Graph Before Import](media/graph-before-import.gif)

### Import from Claude Code Logs
Automatically extract decisions from your Claude Code conversation history with progress tracking.

![Import Claude Logs](media/import-logs.gif)

### AI-Guided Interview Capture
Document decisions through a guided conversation with an AI interviewer that extracts structured decision traces.

![Capture Session](media/capture-session.gif)

### Interactive Knowledge Graph
Explore decisions and entities as an interactive graph with filtering, search, and relationship visualization.

![Knowledge Graph](media/knowledge-graph.gif)

---

## Features

- **Passive Knowledge Capture**: Automatically extract decisions from Claude Code conversation logs
- **AI-Guided Interviews**: NVIDIA Llama-powered interview agent guides knowledge capture
- **Knowledge Graph**: Interactive visualization of decisions and their relationships
- **Decision Traces**: Structured capture of trigger, context, options, decision, and rationale
- **Entity Resolution**: 7-stage deduplication pipeline with configurable similarity thresholds
- **Hybrid Search**: Combined lexical and semantic search with score fusion
- **Graph Validation**: Detect circular dependencies, orphans, duplicates, and relationship issues

---

## Tech Stack

| Layer | Technologies |
|-------|--------------|
| **Frontend** | Next.js 16, React 19, TailwindCSS 4, shadcn/ui |
| **Backend** | FastAPI, SQLAlchemy (async), Pydantic, Python 3.14 |
| **Databases** | PostgreSQL 18, Neo4j 2025.01, Redis 7.4 |
| **AI** | NVIDIA NIM API (Llama 3.3 Nemotron, NV-EmbedQA) |
| **Auth** | Auth.js v5 (next-auth) |
| **Infrastructure** | Docker, Kubernetes, GitHub Actions, Node.js 24 LTS |

---

## Project Status

This project has achieved production-ready status (8.4/10) with:

- ✅ JWT authentication with multi-tenant isolation
- ✅ Kubernetes-ready with CI/CD pipelines
- ✅ Prometheus metrics + Grafana dashboards
- ✅ 838 tests including E2E workflows
- ✅ Circuit breakers, retry logic, and saga transactions
- ✅ 7-stage entity resolution with ~530 canonical mappings

---

## Installation

> **Note**: Public installation instructions are not available at this time.
> This project requires NVIDIA NIM API access and specific infrastructure setup.

For authorized collaborators, please refer to the internal documentation.

---

## License

All rights reserved. See [LICENSE](./LICENSE) for details.

This software is provided for academic review and research collaboration purposes only.

---

## Third-Party Services

This project uses:
- [NVIDIA NIM API](https://developer.nvidia.com/) - Subject to NVIDIA Terms of Service
- [Claude Code](https://claude.ai/) conversation format from Anthropic

---

## Acknowledgments

Built as part of ongoing research in human-AI collaboration for software engineering.

---

*For collaboration inquiries, please contact Ali Shehral at shehral.m@northeastern.edu*
