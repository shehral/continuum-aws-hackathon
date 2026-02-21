/**
 * Mock data layer for the Chat Q&A interface.
 * Simulates backend responses for frontend-first development.
 * Replace with real API calls when backend is ready.
 */

import type {
  ChatSession,
  ChatMessage,
  ChatSessionListItem,
  SuggestedQuestion,
  SourceDecision,
  MentionedEntity,
} from "./api"

// ---------------------------------------------------------------------------
// Suggested questions
// ---------------------------------------------------------------------------

export const SUGGESTED_QUESTIONS: SuggestedQuestion[] = [
  {
    question: "What are the most important architectural decisions in this project?",
    category: "overview",
  },
  {
    question: "Why was Neo4j chosen over other graph databases?",
    category: "why",
  },
  {
    question: "How has the authentication system evolved over time?",
    category: "evolution",
  },
  {
    question: "What technologies does this project use and why?",
    category: "why",
  },
  {
    question: "Are there any unresolved technical debates or contradictions?",
    category: "comparison",
  },
  {
    question: "What decisions were made around the LLM provider choice?",
    category: "why",
  },
]

// ---------------------------------------------------------------------------
// Mock source decisions
// ---------------------------------------------------------------------------

const MOCK_DECISIONS: Record<string, SourceDecision[]> = {
  neo4j: [
    {
      id: "dec-001",
      trigger: "Need a database to store architectural decisions with rich relationships",
      decision: "Use Neo4j as the primary knowledge graph database",
      rationale:
        "Neo4j provides native graph traversal, Cypher query language for relationship queries, and built-in vector index support for semantic search. Relational databases would require complex JOIN operations for the highly connected decision-entity model.",
      confidence: 0.92,
      is_current: true,
      entities: ["Neo4j", "PostgreSQL", "Knowledge Graph"],
    },
    {
      id: "dec-002",
      trigger: "Need to support semantic similarity search over decisions",
      decision: "Use Neo4j vector indexes alongside NVIDIA NV-EmbedQA embeddings",
      rationale:
        "Neo4j 5.x added native vector index support, allowing us to colocate embeddings with graph data. This avoids the complexity of a separate vector DB (Pinecone, Weaviate) while leveraging NVIDIA's embedding model for 2048-dim vectors.",
      confidence: 0.88,
      is_current: true,
      entities: ["Neo4j", "NVIDIA", "Embeddings", "Vector Search"],
    },
  ],
  architecture: [
    {
      id: "dec-003",
      trigger: "Designing the system architecture for decision capture and retrieval",
      decision: "Use a three-database architecture: PostgreSQL (relational), Neo4j (graph), Redis (cache)",
      rationale:
        "Each database serves a distinct purpose: PostgreSQL for user data and session management with ACID guarantees, Neo4j for the knowledge graph with native relationship traversal, and Redis for caching (entity resolution, embeddings) and rate limiting. This separation of concerns allows each layer to be optimized independently.",
      confidence: 0.95,
      is_current: true,
      entities: ["PostgreSQL", "Neo4j", "Redis", "Microservices"],
    },
    {
      id: "dec-004",
      trigger: "Choosing between monolith and microservices for the initial build",
      decision: "Start with a modular monolith (FastAPI + Next.js) with clear service boundaries",
      rationale:
        "A modular monolith reduces operational complexity while maintaining clean separation via service classes. The codebase uses dependency injection and async patterns that make future extraction to microservices straightforward if needed.",
      confidence: 0.85,
      is_current: true,
      entities: ["FastAPI", "Next.js", "Monolith", "Microservices"],
    },
  ],
  auth: [
    {
      id: "dec-005",
      trigger: "Need user authentication for multi-tenant decision isolation",
      decision: "Use JWT tokens via python-jose with per-user scoping on all queries",
      rationale:
        "JWT provides stateless authentication suitable for API-first architecture. Every Neo4j query includes a user_id filter to ensure complete tenant isolation. Auth.js (next-auth) handles the frontend session management.",
      confidence: 0.9,
      is_current: true,
      entities: ["JWT", "Auth.js", "Multi-tenancy"],
    },
    {
      id: "dec-006",
      trigger: "Initial auth used simple API keys",
      decision: "Migrate from API key auth to JWT-based authentication",
      rationale:
        "API keys lacked user identity, session management, and token expiry. JWT with refresh tokens provides better security, enables per-user rate limiting (SEC-009), and supports the multi-tenant isolation model.",
      confidence: 0.82,
      is_current: false,
      entities: ["JWT", "API Keys", "Security"],
    },
  ],
  llm: [
    {
      id: "dec-007",
      trigger: "Need an LLM provider for decision extraction and interview agent",
      decision: "Use NVIDIA NIM API as primary LLM provider with Amazon Bedrock as fallback",
      rationale:
        "NVIDIA NIM provides access to Llama 3.3 Nemotron Super 49B with competitive pricing and low latency. Bedrock (Claude Sonnet) serves as a fallback with automatic failover (ML-QW-2). The provider abstraction layer allows swapping without code changes.",
      confidence: 0.87,
      is_current: true,
      entities: ["NVIDIA NIM", "Amazon Bedrock", "LLM", "Llama"],
    },
  ],
  technologies: [
    {
      id: "dec-003",
      trigger: "Designing the system architecture for decision capture and retrieval",
      decision: "Use a three-database architecture: PostgreSQL (relational), Neo4j (graph), Redis (cache)",
      rationale:
        "Each database serves a distinct purpose: PostgreSQL for user data and session management, Neo4j for the knowledge graph, and Redis for caching and rate limiting.",
      confidence: 0.95,
      is_current: true,
      entities: ["PostgreSQL", "Neo4j", "Redis"],
    },
    {
      id: "dec-008",
      trigger: "Choosing a frontend framework for the knowledge graph dashboard",
      decision: "Use Next.js 16 with React 19 and TailwindCSS 4",
      rationale:
        "Next.js provides SSR/SSG capabilities, file-based routing, and strong TypeScript support. React 19's concurrent features improve responsiveness for the graph visualization. TailwindCSS enables rapid UI development with consistent design tokens.",
      confidence: 0.91,
      is_current: true,
      entities: ["Next.js", "React", "TailwindCSS"],
    },
    {
      id: "dec-007",
      trigger: "Need an LLM provider for decision extraction and interview agent",
      decision: "Use NVIDIA NIM API as primary with Bedrock fallback",
      rationale:
        "NVIDIA NIM provides Llama 3.3 Nemotron with competitive pricing. Provider abstraction allows swapping without code changes.",
      confidence: 0.87,
      is_current: true,
      entities: ["NVIDIA NIM", "Amazon Bedrock", "LLM"],
    },
  ],
  contradictions: [
    {
      id: "dec-009",
      trigger: "Deciding on entity resolution strategy",
      decision: "Use a 7-stage pipeline with fuzzy matching at 85% threshold",
      rationale:
        "The pipeline balances precision and recall: exact match first, then progressively looser matching (canonical names, aliases, fuzzy, embedding similarity). The 85% fuzzy threshold was calibrated against training data to minimize false positives.",
      confidence: 0.88,
      is_current: true,
      entities: ["Entity Resolution", "RapidFuzz", "Embeddings"],
    },
    {
      id: "dec-010",
      trigger: "Debate about embedding similarity threshold for entity matching",
      decision: "Set embedding similarity threshold at 90% (stricter than fuzzy)",
      rationale:
        "Embedding similarity can produce false positives for semantically related but distinct concepts (e.g., 'PostgreSQL' vs 'MySQL'). The 90% threshold was chosen after testing showed 85% produced too many incorrect merges. This remains under review as the entity count grows.",
      confidence: 0.72,
      is_current: true,
      entities: ["Embeddings", "Entity Resolution", "Thresholds"],
    },
  ],
}

// ---------------------------------------------------------------------------
// Mock entities
// ---------------------------------------------------------------------------

const MOCK_ENTITIES: Record<string, MentionedEntity[]> = {
  neo4j: [
    { name: "Neo4j", type: "technology", decision_count: 8 },
    { name: "PostgreSQL", type: "technology", decision_count: 5 },
    { name: "Knowledge Graph", type: "concept", decision_count: 12 },
    { name: "Vector Search", type: "concept", decision_count: 3 },
  ],
  architecture: [
    { name: "PostgreSQL", type: "technology", decision_count: 5 },
    { name: "Neo4j", type: "technology", decision_count: 8 },
    { name: "Redis", type: "technology", decision_count: 4 },
    { name: "FastAPI", type: "technology", decision_count: 6 },
    { name: "Next.js", type: "technology", decision_count: 4 },
  ],
  auth: [
    { name: "JWT", type: "technology", decision_count: 3 },
    { name: "Auth.js", type: "technology", decision_count: 2 },
    { name: "Multi-tenancy", type: "concept", decision_count: 4 },
  ],
  llm: [
    { name: "NVIDIA NIM", type: "technology", decision_count: 3 },
    { name: "Amazon Bedrock", type: "technology", decision_count: 2 },
    { name: "LLM", type: "concept", decision_count: 7 },
    { name: "Llama", type: "technology", decision_count: 2 },
  ],
  technologies: [
    { name: "PostgreSQL", type: "technology", decision_count: 5 },
    { name: "Neo4j", type: "technology", decision_count: 8 },
    { name: "Redis", type: "technology", decision_count: 4 },
    { name: "Next.js", type: "technology", decision_count: 4 },
    { name: "React", type: "technology", decision_count: 3 },
    { name: "TailwindCSS", type: "technology", decision_count: 2 },
  ],
  contradictions: [
    { name: "Entity Resolution", type: "concept", decision_count: 4 },
    { name: "RapidFuzz", type: "technology", decision_count: 2 },
    { name: "Embeddings", type: "concept", decision_count: 5 },
    { name: "Thresholds", type: "concept", decision_count: 2 },
  ],
}

// ---------------------------------------------------------------------------
// Mock responses keyed by question topic
// ---------------------------------------------------------------------------

interface MockResponse {
  content: string
  decisionKey: string
}

const MOCK_RESPONSES: { pattern: RegExp; response: MockResponse }[] = [
  {
    pattern: /neo4j|graph\s*database/i,
    response: {
      content: `The team chose **Neo4j** as the primary knowledge graph database for several compelling reasons [DEC-dec-001].

**Why Neo4j over alternatives:**

1. **Native graph traversal** — The decision-entity model is highly connected. Decisions link to entities, entities relate to each other (DEPENDS_ON, ALTERNATIVE_TO), and decisions form evolution chains (SUPERSEDES, CONTRADICTS). Neo4j handles these multi-hop queries natively via Cypher, whereas a relational DB would require complex recursive JOINs.

2. **Vector index support** — Neo4j 5.x added native vector indexes, which enabled the team to colocate embeddings directly alongside graph data [DEC-dec-002]. This eliminated the need for a separate vector database like Pinecone or Weaviate, simplifying the architecture.

3. **Hybrid search** — The combination of Neo4j's fulltext indexes (lexical search) and vector indexes (semantic search) enables the hybrid search strategy (30% lexical + 70% semantic weighting) that powers the context retrieval.

**Trade-offs acknowledged:**
- Neo4j adds operational complexity compared to using PostgreSQL alone
- The team accepted this because the relationship-heavy query patterns made a graph database significantly more natural and performant

The decision has a **92% confidence score** and remains the current approach.`,
      decisionKey: "neo4j",
    },
  },
  {
    pattern: /important|architectural|overview|key\s*decisions/i,
    response: {
      content: `Here are the most significant architectural decisions that shape this project:

**1. Three-Database Architecture** [DEC-dec-003]
The system uses PostgreSQL (relational data), Neo4j (knowledge graph), and Redis (caching). Each serves a distinct purpose — this separation of concerns is the backbone of the architecture. Confidence: **95%**.

**2. Modular Monolith** [DEC-dec-004]
Rather than starting with microservices, the team chose a modular monolith (FastAPI backend + Next.js frontend) with clean service boundaries. This reduces operational complexity while keeping future extraction paths open.

**3. NVIDIA NIM as Primary LLM** [DEC-dec-007]
The LLM provider abstraction supports NVIDIA NIM (primary) and Amazon Bedrock (fallback). Automatic failover ensures reliability without vendor lock-in.

**4. JWT-Based Multi-Tenancy** [DEC-dec-005]
Every query is scoped by user_id via JWT tokens, ensuring complete tenant isolation across the knowledge graph.

**5. 7-Stage Entity Resolution** [DEC-dec-009]
Entity deduplication uses a progressive pipeline: exact match → canonical names → aliases → fuzzy matching → embedding similarity, with ~530 canonical mappings.

These decisions have an average confidence of **89%**, indicating they are well-established and unlikely to change.`,
      decisionKey: "architecture",
    },
  },
  {
    pattern: /auth|authentication|login|jwt/i,
    response: {
      content: `The authentication system has gone through a notable evolution:

**Phase 1: API Key Authentication** (Early)
The system initially used simple API keys for authentication. This was quick to implement but lacked user identity, session management, and token expiry [DEC-dec-006].

**Phase 2: JWT-Based Authentication** (Current) [DEC-dec-005]
The team migrated to JWT tokens via python-jose (HS256 algorithm) with the following design:
- **Backend**: FastAPI dependency injection with \`get_current_user_id()\` — every endpoint gets the authenticated user
- **Frontend**: Auth.js (next-auth) manages sessions, token refresh, and login/logout flows
- **Multi-tenant isolation**: Every Neo4j query includes \`WHERE d.user_id = $user_id\` to ensure users only see their own decisions
- **Rate limiting**: Per-user rate limiting (SEC-009) uses Redis sliding window — 30 req/min for authenticated, 10 for anonymous

**Why the migration happened:**
API keys couldn't support the multi-tenant model. When the team added user isolation (every decision scoped by user_id), they needed proper user identity. JWT provided stateless auth, token expiry, and session management.

The current JWT system has **90% confidence** and is considered stable.`,
      decisionKey: "auth",
    },
  },
  {
    pattern: /technolog|stack|use|framework|tools/i,
    response: {
      content: `The project uses a carefully chosen technology stack, with each component selected for specific reasons:

**Backend:**
- **FastAPI** (Python 3.14) — Chosen for async-first design, automatic OpenAPI docs, and Pydantic integration. The entire backend is async, using SQLAlchemy 2.0 async and asyncpg [DEC-dec-004].
- **PostgreSQL 18** — User data, capture sessions, audit logs. Selected for ACID guarantees and mature ecosystem.
- **Neo4j 2025.01** — Knowledge graph. Native graph traversal and vector indexes [DEC-dec-001].
- **Redis 7.4** — Caching (entity resolution, embeddings) and rate limiting.

**Frontend:**
- **Next.js 16 + React 19** — SSR/SSG, file-based routing, strong TypeScript support [DEC-dec-008].
- **TailwindCSS 4** — Rapid styling with design tokens.
- **shadcn/ui** — Accessible component primitives (Button, Card, Dialog, etc.).
- **XyFlow** — Interactive graph visualization.
- **TanStack React Query** — Server state management with caching.

**AI/ML:**
- **NVIDIA NIM** (primary LLM) — Llama 3.3 Nemotron Super 49B [DEC-dec-007].
- **Amazon Bedrock** (fallback) — Claude Sonnet 4 with automatic failover.
- **NVIDIA NV-EmbedQA** — 2048-dim embeddings for semantic search [DEC-dec-002].

**Why these specific choices:**
The pattern is consistent — the team favors proven, well-documented tools with strong async support and clear upgrade paths. The provider abstraction layer for LLMs specifically guards against vendor lock-in.`,
      decisionKey: "technologies",
    },
  },
  {
    pattern: /contradict|debate|unresolved|conflict/i,
    response: {
      content: `There are a few areas where the team has ongoing technical debates:

**1. Entity Resolution Thresholds** [DEC-dec-009] vs [DEC-dec-010]
The fuzzy matching threshold is set at **85%** while the embedding similarity threshold is at **90%**. There's tension here:
- The fuzzy threshold catches variations like "postgres" → "PostgreSQL" effectively
- But the embedding threshold needed to be stricter (90% vs 85%) because embedding similarity can produce false positives for related-but-distinct concepts (e.g., "PostgreSQL" vs "MySQL" score ~87% similarity)
- The 90% threshold has only **72% confidence**, indicating the team isn't fully settled on this value

**2. Embedding Provider Lock-in**
While the LLM provider can be swapped between NVIDIA and Bedrock, the embedding provider is effectively locked to NVIDIA NV-EmbedQA because changing it would require re-indexing all existing vectors. This is an accepted trade-off but documented as a future risk.

**3. WebSocket Authentication**
The WebSocket endpoint for capture sessions currently uses anonymous user IDs (marked as TODO in the codebase). This needs to be resolved before production deployment with either query parameter tokens, first-message auth, or cookie-based auth.

These are tracked as open items. The CONTRADICTS relationship type in the knowledge graph can surface these automatically when new related decisions are added.`,
      decisionKey: "contradictions",
    },
  },
  {
    pattern: /llm|provider|nvidia|bedrock|model/i,
    response: {
      content: `The LLM provider architecture was designed with resilience and flexibility in mind [DEC-dec-007]:

**Primary Provider: NVIDIA NIM**
- Model: Llama 3.3 Nemotron Super 49B v1.5
- Used for: decision extraction, interview agent responses, entity analysis
- Why: Competitive pricing, low latency, good performance on structured extraction tasks

**Fallback Provider: Amazon Bedrock**
- Model: Claude Sonnet 4
- Activated automatically when NVIDIA NIM fails (ML-QW-2 pattern)
- Uses the Bedrock Converse API

**Provider Abstraction Layer:**
The system uses a \`BaseLLMProvider\` abstract class with \`NvidiaLLMProvider\` and \`BedrockLLMProvider\` implementations. This means swapping providers requires only a config change (\`llm_provider: "nvidia" | "bedrock"\`), no code changes.

**Resilience Features:**
- **Retry logic**: Exponential backoff with jitter for 429/5xx errors
- **Model fallback**: If primary model fails, automatically falls back to secondary
- **Rate limiting**: Per-user Redis-based sliding window (30 req/min authenticated)
- **Prompt sanitization**: Detects injection attempts before sending to LLM

**Embedding Provider:**
NVIDIA NV-EmbedQA (2048-dim vectors) with Redis caching (30-day TTL). Note: unlike the LLM provider, the embedding provider can't be easily swapped because it would require re-indexing all existing vectors.`,
      decisionKey: "llm",
    },
  },
]

// Default fallback response
const DEFAULT_RESPONSE: MockResponse = {
  content: `That's an interesting question! Based on the knowledge graph, I can share what I've found.

The project follows several key architectural principles:
- **Async-first**: The entire backend uses async Python (FastAPI, SQLAlchemy async, asyncpg)
- **Separation of concerns**: Three databases for three purposes (PostgreSQL, Neo4j, Redis)
- **Resilience patterns**: Circuit breakers, retry logic, and model fallback throughout
- **Multi-tenant isolation**: Every query scoped by user_id

I'd be happy to dive deeper into any specific area. Try asking about:
- A specific technology choice (e.g., "Why Neo4j?")
- How a system evolved (e.g., "How has auth changed?")
- Current debates or contradictions in the architecture`,
  decisionKey: "architecture",
}

// ---------------------------------------------------------------------------
// Mock session history
// ---------------------------------------------------------------------------

export const MOCK_SESSION_LIST: ChatSessionListItem[] = [
  {
    id: "session-001",
    title: "Understanding the database architecture",
    status: "active",
    created_at: new Date(Date.now() - 2 * 60 * 60 * 1000).toISOString(),
    updated_at: new Date(Date.now() - 1 * 60 * 60 * 1000).toISOString(),
    message_count: 6,
    last_message_preview: "The three-database architecture was chosen for separation of concerns...",
  },
  {
    id: "session-002",
    title: "Auth system evolution",
    status: "active",
    created_at: new Date(Date.now() - 24 * 60 * 60 * 1000).toISOString(),
    updated_at: new Date(Date.now() - 23 * 60 * 60 * 1000).toISOString(),
    message_count: 4,
    last_message_preview: "JWT-based authentication replaced the earlier API key approach...",
  },
  {
    id: "session-003",
    title: "LLM provider decisions",
    status: "active",
    created_at: new Date(Date.now() - 3 * 24 * 60 * 60 * 1000).toISOString(),
    updated_at: new Date(Date.now() - 3 * 24 * 60 * 60 * 1000).toISOString(),
    message_count: 8,
    last_message_preview: "NVIDIA NIM was selected as the primary LLM provider with Bedrock fallback...",
  },
]

// ---------------------------------------------------------------------------
// Mock response matching
// ---------------------------------------------------------------------------

function findMockResponse(question: string): MockResponse {
  for (const { pattern, response } of MOCK_RESPONSES) {
    if (pattern.test(question)) {
      return response
    }
  }
  return DEFAULT_RESPONSE
}

// ---------------------------------------------------------------------------
// Simulated streaming
// ---------------------------------------------------------------------------

export async function simulateStream(
  text: string,
  onChunk: (chunk: string) => void,
  options?: { wordDelay?: number; initialDelay?: number }
): Promise<void> {
  const { wordDelay = 30, initialDelay = 500 } = options ?? {}

  // Initial "thinking" delay
  await new Promise((r) => setTimeout(r, initialDelay))

  // Stream word by word
  const words = text.split(/(\s+)/)
  for (const word of words) {
    onChunk(word)
    if (word.trim()) {
      await new Promise((r) => setTimeout(r, wordDelay + Math.random() * 20))
    }
  }
}

// ---------------------------------------------------------------------------
// Public API (mirrors what the backend will provide)
// ---------------------------------------------------------------------------

let sessionCounter = 100

export function createMockSession(projectFilter?: string): ChatSession {
  sessionCounter++
  return {
    id: `session-${sessionCounter}`,
    title: null,
    status: "active",
    project_filter: projectFilter ?? null,
    created_at: new Date().toISOString(),
    updated_at: new Date().toISOString(),
    messages: [],
  }
}

export function getMockResponse(question: string): {
  content: string
  sourceDecisions: SourceDecision[]
  mentionedEntities: MentionedEntity[]
} {
  const response = findMockResponse(question)
  return {
    content: response.content,
    sourceDecisions: MOCK_DECISIONS[response.decisionKey] ?? [],
    mentionedEntities: MOCK_ENTITIES[response.decisionKey] ?? [],
  }
}

export function generateMockTitle(firstMessage: string): string {
  const lower = firstMessage.toLowerCase()
  if (lower.includes("neo4j") || lower.includes("graph database")) return "Neo4j architecture decisions"
  if (lower.includes("auth")) return "Authentication system evolution"
  if (lower.includes("llm") || lower.includes("provider")) return "LLM provider strategy"
  if (lower.includes("technolog") || lower.includes("stack")) return "Technology stack overview"
  if (lower.includes("contradict") || lower.includes("debate")) return "Open technical debates"
  if (lower.includes("important") || lower.includes("architectural")) return "Key architectural decisions"
  // Truncate to first ~40 chars
  return firstMessage.length > 40 ? firstMessage.slice(0, 40) + "..." : firstMessage
}
