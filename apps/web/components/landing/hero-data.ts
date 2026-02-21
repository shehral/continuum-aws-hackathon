// ── Chat messages (human ↔ AI conversation on the left monitor) ──────

export const CHAT_MESSAGES = [
  { role: "human" as const, text: "Build a Strands agent with persistent memory" },
  { role: "ai" as const, text: "I'll use Bedrock with Neo4j as the knowledge graph and add Datadog LLM Observability." },
  { role: "human" as const, text: "Can the agent check prior decisions before acting?" },
  { role: "ai" as const, text: "Yes — continuum_check queries Neo4j, every call traced in Datadog." },
];

// ── Graph nodes that the conversation transforms into ────────────────

export interface GraphNode {
  id: number;
  kind: "decision" | "entity";
  label: string;
  entityType?: "technology" | "pattern";
  x: number;
  y: number;
}

export const GRAPH_NODES: GraphNode[] = [
  // Decisions (violet)
  { id: 0, kind: "decision", label: "Use Bedrock", x: -200, y: -100 },
  { id: 1, kind: "decision", label: "Add LLM Observability", x: 200, y: -100 },
  // Technologies (orange)
  { id: 2, kind: "entity", entityType: "technology", label: "Neo4j", x: -440, y: 60 },
  { id: 3, kind: "entity", entityType: "technology", label: "Datadog", x: 440, y: 60 },
  { id: 4, kind: "entity", entityType: "technology", label: "Strands SDK", x: -40, y: 60 },
  { id: 6, kind: "entity", entityType: "technology", label: "Claude Sonnet", x: -380, y: -200 },
  { id: 10, kind: "entity", entityType: "technology", label: "FastAPI", x: 280, y: 220 },
  // Patterns (pink)
  { id: 5, kind: "entity", entityType: "pattern", label: "Agent Memory", x: 0, y: -270 },
  { id: 7, kind: "entity", entityType: "pattern", label: "Entity Resolution", x: -240, y: 220 },
  { id: 8, kind: "entity", entityType: "pattern", label: "Knowledge Graph", x: 40, y: 260 },
  { id: 9, kind: "entity", entityType: "pattern", label: "LLM Tracing", x: 380, y: -200 },
];

export interface GraphEdge {
  source: number;
  target: number;
  label: string;
  dashed?: boolean;
}

export const GRAPH_EDGES: GraphEdge[] = [
  // Original connections
  { source: 0, target: 2, label: "STORES_IN" },
  { source: 0, target: 4, label: "POWERED_BY" },
  { source: 1, target: 3, label: "TRACES_WITH" },
  { source: 1, target: 5, label: "ENABLES" },
  { source: 1, target: 0, label: "OBSERVES", dashed: true },
  // New connections
  { source: 0, target: 6, label: "RUNS_ON" },
  { source: 2, target: 7, label: "RESOLVES_VIA" },
  { source: 2, target: 8, label: "BUILDS" },
  { source: 3, target: 9, label: "POWERS" },
  { source: 4, target: 10, label: "SERVES_VIA" },
  { source: 5, target: 8, label: "PERSISTS_AS", dashed: true },
  { source: 7, target: 8, label: "FEEDS" },
];

// ── Colour helpers ───────────────────────────────────────────────────

export function nodeColor(node: GraphNode): string {
  if (node.kind === "decision") return "rgba(139,92,246,0.9)";
  return node.entityType === "technology"
    ? "rgba(251,146,60,0.9)"
    : "rgba(236,72,153,0.9)";
}

export function nodeBg(node: GraphNode): string {
  if (node.kind === "decision") return "rgba(139,92,246,0.08)";
  return node.entityType === "technology"
    ? "rgba(251,146,60,0.08)"
    : "rgba(236,72,153,0.08)";
}

export function nodeBorder(node: GraphNode): string {
  if (node.kind === "decision") return "rgba(139,92,246,0.4)";
  return node.entityType === "technology"
    ? "rgba(251,146,60,0.3)"
    : "rgba(236,72,153,0.3)";
}

// ── Code editor content (right monitor) ──────────────────────────────

export type TokenColor =
  | "keyword"
  | "string"
  | "function"
  | "comment"
  | "type"
  | "default"
  | "operator";

export interface CodeToken {
  text: string;
  color: TokenColor;
}

export interface CodeLine {
  lineNo: number;
  tokens: CodeToken[];
}

export const TOKEN_COLORS: Record<TokenColor, string> = {
  keyword: "#c4b5fd",   // violet-300
  string: "#fdba74",    // orange-300
  function: "#67e8f9",  // cyan-300
  comment: "#64748b",   // slate-500
  type: "#6ee7b7",      // emerald-400
  default: "#cbd5e1",   // slate-300
  operator: "#f9a8d4",  // pink-300
};

export const CODE_LINES: CodeLine[] = [
  { lineNo: 1,  tokens: [{ text: "from", color: "keyword" }, { text: " strands ", color: "default" }, { text: "import", color: "keyword" }, { text: " Agent", color: "type" }] },
  { lineNo: 2,  tokens: [{ text: "from", color: "keyword" }, { text: " strands.models.bedrock ", color: "default" }, { text: "import", color: "keyword" }, { text: " BedrockModel", color: "type" }] },
  { lineNo: 3,  tokens: [{ text: "from", color: "keyword" }, { text: " ddtrace ", color: "default" }, { text: "import", color: "keyword" }, { text: " tracer", color: "function" }] },
  { lineNo: 4,  tokens: [] },
  { lineNo: 5,  tokens: [{ text: "model", color: "default" }, { text: " = ", color: "operator" }, { text: "BedrockModel", color: "type" }, { text: "(", color: "default" }] },
  { lineNo: 6,  tokens: [{ text: "    model_id", color: "default" }, { text: "=", color: "operator" }, { text: '"us.anthropic.claude-sonnet"', color: "string" }, { text: ",", color: "default" }] },
  { lineNo: 7,  tokens: [{ text: ")", color: "default" }] },
  { lineNo: 8,  tokens: [] },
  { lineNo: 9,  tokens: [{ text: "@tracer.wrap", color: "function" }, { text: "(", color: "default" }, { text: '"agent.decide"', color: "string" }, { text: ")", color: "default" }] },
  { lineNo: 10, tokens: [{ text: "def", color: "keyword" }, { text: " ", color: "default" }, { text: "decide", color: "function" }, { text: "(query: ", color: "default" }, { text: "str", color: "type" }, { text: "):", color: "default" }] },
  { lineNo: 11, tokens: [{ text: "    agent ", color: "default" }, { text: "=", color: "operator" }, { text: " ", color: "default" }, { text: "Agent", color: "type" }, { text: "(", color: "default" }] },
  { lineNo: 12, tokens: [{ text: "        model", color: "default" }, { text: "=", color: "operator" }, { text: "model", color: "default" }, { text: ",", color: "default" }] },
  { lineNo: 13, tokens: [{ text: "        tools", color: "default" }, { text: "=", color: "operator" }, { text: "[check, remember]", color: "default" }, { text: ",", color: "default" }] },
  { lineNo: 14, tokens: [{ text: "    )", color: "default" }] },
  { lineNo: 15, tokens: [{ text: "    ", color: "default" }, { text: "return", color: "keyword" }, { text: " agent", color: "default" }, { text: "(", color: "default" }, { text: "query", color: "default" }, { text: ")", color: "default" }] },
];
