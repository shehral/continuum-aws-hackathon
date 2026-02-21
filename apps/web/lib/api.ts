const API_URL = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000"

export interface Decision {
  id: string
  trigger: string
  context: string
  options: string[]
  agent_decision: string
  agent_rationale: string
  human_decision?: string | null
  human_rationale?: string | null
  confidence: number
  created_at: string
  entities: Entity[]
  source?: "claude_logs" | "interview" | "manual" | "unknown"
  project_name?: string
  // Verbatim grounding fields (CogCanvas-inspired, RQ1 enhancement)
  verbatim_quote?: string | null
  verbatim_start_char?: number | null
  verbatim_end_char?: number | null
  turn_index?: number | null
}

export interface Entity {
  id: string
  name: string
  type: "concept" | "system" | "person" | "technology" | "pattern"
}

export interface GraphNode {
  id: string
  type: "decision" | "entity"
  label: string
  data: Decision | Entity
  has_embedding?: boolean
}

export interface GraphEdge {
  id: string
  source: string
  target: string
  relationship: string
  weight?: number
}

export interface GraphData {
  nodes: GraphNode[]
  edges: GraphEdge[]
}

// Relationship types
export type RelationshipType =
  | "INVOLVES"
  | "SIMILAR_TO"
  | "SUPERSEDES"
  | "INFLUENCED_BY"
  | "CONTRADICTS"
  | "IS_A"
  | "PART_OF"
  | "RELATED_TO"
  | "DEPENDS_ON"

export interface SimilarDecision {
  id: string
  trigger: string
  agent_decision: string
  similarity: number
  shared_entities: string[]
}

// Search result from /api/search endpoint
export interface SearchResult {
  type: "decision" | "entity"
  id: string
  label: string
  score: number
  data: {
    // Decision fields
    trigger?: string
    decision?: string  // backward compat from search
    agent_decision?: string
    confidence?: number
    // Entity fields
    name?: string
    type?: string
  }
}

export interface GraphStats {
  decisions: { total: number; with_embeddings: number }
  entities: { total: number; with_embeddings: number }
  relationships: number
}

export interface ValidationIssue {
  type: string
  severity: "error" | "warning" | "info"
  message: string
  affected_nodes: string[]
  suggested_action?: string
  details?: Record<string, unknown>
}

export interface ValidationSummary {
  total_issues: number
  by_severity: Record<string, number>
  by_type: Record<string, number>
  issues: ValidationIssue[]
}

export interface CaptureSession {
  id: string
  status: "active" | "completed" | "abandoned"
  created_at: string
  updated_at: string
  messages: CaptureMessage[]
}

export interface CaptureMessage {
  id: string
  role: "user" | "assistant"
  content: string
  timestamp: string
  extracted_entities?: Entity[]
}

export interface DashboardStats {
  total_decisions: number
  total_entities: number
  total_sessions: number
  needs_review: number
  recent_decisions: Decision[]
}

class ApiClient {
  private baseUrl: string

  constructor(baseUrl: string = API_URL) {
    this.baseUrl = baseUrl
  }

  private async fetch<T>(
    endpoint: string,
    options: RequestInit = {}
  ): Promise<T> {
    const response = await fetch(`${this.baseUrl}${endpoint}`, {
      ...options,
      headers: {
        "Content-Type": "application/json",
        ...options.headers,
      },
    })

    if (!response.ok) {
      throw new Error(`API error: ${response.status} ${response.statusText}`)
    }

    return response.json()
  }

  // Dashboard
  async getDashboardStats(): Promise<DashboardStats> {
    return this.fetch<DashboardStats>("/api/dashboard/stats")
  }

  // Decisions
  async getDecisions(limit = 50, offset = 0): Promise<Decision[]> {
    return this.fetch<Decision[]>(
      `/api/decisions?limit=${limit}&offset=${offset}`
    )
  }

  async getDecision(id: string): Promise<Decision> {
    return this.fetch<Decision>(`/api/decisions/${id}`)
  }

  async deleteDecision(id: string): Promise<{ status: string; message: string }> {
    return this.fetch<{ status: string; message: string }>(
      `/api/decisions/${id}`,
      { method: "DELETE" }
    )
  }

  // Graph
  async getGraph(options?: {
    include_similarity?: boolean
    include_temporal?: boolean
    include_entity_relations?: boolean
    source_filter?: "claude_logs" | "interview" | "manual" | "unknown"
    project_filter?: string
  }): Promise<GraphData> {
    const params = new URLSearchParams()
    if (options?.include_similarity !== undefined)
      params.append("include_similarity", String(options.include_similarity))
    if (options?.include_temporal !== undefined)
      params.append("include_temporal", String(options.include_temporal))
    if (options?.include_entity_relations !== undefined)
      params.append("include_entity_relations", String(options.include_entity_relations))
    if (options?.source_filter)
      params.append("source_filter", options.source_filter)
    if (options?.project_filter)
      params.append("project_filter", options.project_filter)
    const query = params.toString()
    return this.fetch<GraphData>(`/api/graph${query ? `?${query}` : ""}`)
  }

  async getDecisionSources(): Promise<Record<string, number>> {
    return this.fetch<Record<string, number>>("/api/graph/sources")
  }

  async getProjectCounts(): Promise<Record<string, number>> {
    return this.fetch<Record<string, number>>("/api/graph/projects")
  }

  async getNodeDetails(nodeId: string): Promise<GraphNode> {
    return this.fetch<GraphNode>(`/api/graph/nodes/${nodeId}`)
  }

  async getSimilarDecisions(
    nodeId: string,
    topK = 5,
    threshold = 0.5
  ): Promise<SimilarDecision[]> {
    return this.fetch<SimilarDecision[]>(
      `/api/graph/nodes/${nodeId}/similar?top_k=${topK}&threshold=${threshold}`
    )
  }

  async semanticSearch(
    query: string,
    topK = 10,
    threshold = 0.5
  ): Promise<SimilarDecision[]> {
    return this.fetch<SimilarDecision[]>("/api/graph/search/semantic", {
      method: "POST",
      body: JSON.stringify({ query, top_k: topK, threshold }),
    })
  }

  async getGraphStats(): Promise<GraphStats> {
    return this.fetch<GraphStats>("/api/graph/stats")
  }

  async getRelationshipTypes(): Promise<Record<string, number>> {
    return this.fetch<Record<string, number>>("/api/graph/relationships/types")
  }

  async getGraphValidation(): Promise<ValidationSummary> {
    return this.fetch<ValidationSummary>("/api/graph/validate")
  }

  // Entities
  async deleteEntity(id: string): Promise<{ status: string; message: string }> {
    return this.fetch<{ status: string; message: string }>(
      `/api/entities/${id}`,
      { method: "DELETE" }
    )
  }


  // Capture Sessions
  async startCaptureSession(projectName?: string | null): Promise<CaptureSession> {
    return this.fetch<CaptureSession>("/api/capture/sessions", {
      method: "POST",
      ...(projectName && {
        body: JSON.stringify({ project_name: projectName }),
      }),
    })
  }

  async getCaptureSession(id: string): Promise<CaptureSession> {
    return this.fetch<CaptureSession>(`/api/capture/sessions/${id}`)
  }

  async sendCaptureMessage(
    sessionId: string,
    content: string
  ): Promise<CaptureMessage> {
    return this.fetch<CaptureMessage>(
      `/api/capture/sessions/${sessionId}/messages`,
      {
        method: "POST",
        body: JSON.stringify({ content }),
      }
    )
  }

  async completeCaptureSession(id: string): Promise<CaptureSession> {
    return this.fetch<CaptureSession>(`/api/capture/sessions/${id}/complete`, {
      method: "POST",
    })
  }

  // Ingestion
  async getAvailableProjects(): Promise<{
    dir: string
    name: string
    files: number
    path: string
  }[]> {
    return this.fetch("/api/ingest/projects")
  }

  async previewIngestion(options?: {
    project?: string
    exclude?: string[]
    limit?: number
  }): Promise<{
    total_conversations: number
    previews: { file: string; project: string; messages: number; preview: string }[]
    project_filter: string | null
    exclude_projects: string[]
  }> {
    const params = new URLSearchParams()
    if (options?.project) params.append("project", options.project)
    if (options?.exclude?.length) params.append("exclude", options.exclude.join(","))
    if (options?.limit) params.append("limit", String(options.limit))
    return this.fetch(`/api/ingest/preview?${params}`)
  }

  async triggerIngestion(options?: {
    project?: string
    exclude?: string[]
  }): Promise<{ status: string; job_id: string | null; total_files: number }> {
    const params = new URLSearchParams()
    if (options?.project) params.append("project", options.project)
    if (options?.exclude?.length) params.append("exclude", options.exclude.join(","))
    return this.fetch<{ status: string; job_id: string | null; total_files: number }>(
      `/api/ingest/trigger?${params}`,
      { method: "POST" }
    )
  }

  async getIngestionStatus(): Promise<{
    is_watching: boolean
    last_run: string | null
    files_processed: number
  }> {
    return this.fetch<{
      is_watching: boolean
      last_run: string | null
      files_processed: number
    }>("/api/ingest/status")
  }

  async getImportFiles(options?: {
    project?: string
  }): Promise<{
    file_path: string
    project_name: string
    project_dir: string
    conversation_count: number
    size_bytes: number
    last_modified: string
  }[]> {
    const params = new URLSearchParams()
    if (options?.project) params.append("project", options.project)
    return this.fetch(`/api/ingest/files?${params}`)
  }

  async importSelectedFiles(
    filePaths: string[],
    targetProject?: string | null
  ): Promise<{ status: string; job_id: string; total_files: number; validation_errors?: string[] }> {
    return this.fetch<{ status: string; job_id: string; total_files: number; validation_errors?: string[] }>(
      "/api/ingest/import-selected",
      {
        method: "POST",
        body: JSON.stringify({
          file_paths: filePaths,
          target_project: targetProject,
        }),
      }
    )
  }

  async getImportProgress(): Promise<{
    job_id: string | null
    status: string
    total_files: number
    processed_files: number
    current_file: string | null
    decisions_extracted: number
    errors: string[]
    started_at: string | null
    completed_at: string | null
  }> {
    return this.fetch("/api/ingest/import/progress")
  }

  async cancelImport(): Promise<{ status: string; job_id: string }> {
    return this.fetch("/api/ingest/import/cancel", { method: "POST" })
  }

  async resetGraph(): Promise<{ status: string; message: string }> {
    return this.fetch("/api/graph/reset?confirm=true", { method: "DELETE" })
  }

  // Search
  async search(
    query: string,
    type?: "decision" | "entity"
  ): Promise<SearchResult[]> {
    const params = new URLSearchParams({ query })
    if (type) params.append("type", type)
    return this.fetch<SearchResult[]>(`/api/search?${params}`)
  }

  // Create decision manually
  async createDecision(data: {
    trigger: string
    context: string
    options: string[]
    decision: string  // sent as alias, mapped to agent_decision on backend
    rationale: string  // sent as alias, mapped to agent_rationale on backend
    entities: string[]
    project_name?: string | null
  }): Promise<Decision> {
    return this.fetch<Decision>("/api/decisions", {
      method: "POST",
      body: JSON.stringify(data),
    })
  }

  // Entity linking
  async linkEntity(
    decisionId: string,
    entityId: string,
    relationship: string
  ): Promise<void> {
    await this.fetch(`/api/entities/link`, {
      method: "POST",
      body: JSON.stringify({
        decision_id: decisionId,
        entity_id: entityId,
        relationship,
      }),
    })
  }

  async updateDecision(
    id: string,
    data: Partial<Pick<Decision, "trigger" | "context" | "options" | "agent_decision" | "agent_rationale" | "human_decision" | "human_rationale">>
  ): Promise<Decision> {
    return this.fetch<Decision>(`/api/decisions/${id}`, {
      method: "PUT",
      body: JSON.stringify(data),
    })
  }

  async getDecisionsNeedingReview(
    limit = 20,
    offset = 0
  ): Promise<{ total_needs_review: number; decisions: Decision[] }> {
    return this.fetch(`/api/decisions/needs-review?limit=${limit}&offset=${offset}`)
  }

  // Analytics — Timeline (Part 4.4)
  async getTimeline(options?: {
    project?: string
    granularity?: "day" | "week" | "month"
    monthsBack?: number
  }): Promise<TimelineBucket[]> {
    const params = new URLSearchParams()
    if (options?.project) params.append("project", options.project)
    if (options?.granularity) params.append("granularity", options.granularity)
    if (options?.monthsBack) params.append("months_back", String(options.monthsBack))
    return this.fetch<TimelineBucket[]>(`/api/analytics/timeline?${params}`)
  }

  // Analytics — Dormant alternatives (Part 4.5)
  async getDormantAlternatives(options?: {
    project?: string
    minDaysDormant?: number
    limit?: number
  }): Promise<DormantAlternative[]> {
    const params = new URLSearchParams()
    if (options?.project) params.append("project", options.project)
    if (options?.minDaysDormant) params.append("min_days_dormant", String(options.minDaysDormant))
    if (options?.limit) params.append("limit", String(options.limit))
    return this.fetch<DormantAlternative[]>(`/api/analytics/dormant-alternatives?${params}`)
  }

  // Analytics — Coverage map (Part 4.6)
  async getCoverageMap(project?: string): Promise<CoverageStats> {
    const params = new URLSearchParams()
    if (project) params.append("project", project)
    return this.fetch<CoverageStats>(`/api/analytics/coverage?${params}`)
  }

  // Analytics — Stale decisions (Part 7)
  async getStaleDecisions(options?: {
    project?: string
    limit?: number
  }): Promise<StaleDecision[]> {
    const params = new URLSearchParams()
    if (options?.project) params.append("project", options.project)
    if (options?.limit) params.append("limit", String(options.limit))
    return this.fetch<StaleDecision[]>(`/api/analytics/stale?${params}`)
  }

  async markDecisionReviewed(
    decisionId: string,
    notes?: string
  ): Promise<{ status: string; decision_id: string; reviewed_at: string }> {
    return this.fetch(`/api/analytics/decisions/${decisionId}/review`, {
      method: "POST",
      body: JSON.stringify({ notes: notes || null }),
    })
  }

  // Analytics — Assumption violations (Part 11)
  async getAssumptionViolations(options?: {
    project?: string
    limit?: number
  }): Promise<AssumptionViolation[]> {
    const params = new URLSearchParams()
    if (options?.project) params.append("project", options.project)
    if (options?.limit) params.append("limit", String(options.limit))
    return this.fetch<AssumptionViolation[]>(`/api/analytics/assumption-violations?${params}`)
  }

  async getSuggestedEntities(text: string): Promise<Entity[]> {
    return this.fetch<Entity[]>("/api/entities/suggest", {
      method: "POST",
      body: JSON.stringify({ text }),
    })
  }

  // Hybrid search combining lexical and semantic search
  async hybridSearch(
    query: string,
    options?: {
      topK?: number
      threshold?: number
      alpha?: number
      searchDecisions?: boolean
      searchEntities?: boolean
    }
  ): Promise<HybridSearchResult[]> {
    const body = {
      query,
      top_k: options?.topK ?? 10,
      threshold: options?.threshold ?? 0.3,
      alpha: options?.alpha ?? 0.3,
      search_decisions: options?.searchDecisions ?? true,
      search_entities: options?.searchEntities ?? true,
    }
    return this.fetch<HybridSearchResult[]>("/api/graph/search/hybrid", {
      method: "POST",
      body: JSON.stringify(body),
    })
  }
}

export const api = new ApiClient()

// Hybrid search types and methods
export interface HybridSearchResult {
  id: string
  type: "decision" | "entity"
  label: string
  lexical_score: number
  semantic_score: number
  combined_score: number
  data: {
    trigger?: string
    decision?: string  // backward compat
    agent_decision?: string
    context?: string
    rationale?: string  // backward compat
    agent_rationale?: string
    created_at?: string
    source?: string
    name?: string
    type?: string
    aliases?: string[]
  }
  matched_fields: string[]
}

export type SearchMode = "hybrid" | "lexical" | "semantic"

// Analytics types (Parts 4.4, 4.5, 4.6, 7, 11)

export interface TimelineBucket {
  period: string          // e.g. "2025-W03" or "2025-01"
  count: number
  by_scope: Record<string, number>   // scope → count
  by_type: Record<string, number>    // decision_type → count
  avg_confidence: number
}

export interface DormantAlternative {
  candidate_id: string
  text: string
  rejected_at: string | null
  rejected_by_decision_id: string
  rejected_by_trigger: string
  original_decision: string
  days_dormant: number
  reconsider_score: number
}

export interface CoverageFile {
  file_path: string
  language: string
  decision_count: number
  last_decision_at: string | null
  days_since_decision: number | null
  is_stale: boolean
  staleness_days: number
}

export interface CoverageStats {
  total_files: number
  covered_files: number
  stale_files: number
  uncovered_files: number
  knowledge_debt_score: number  // 0–1
  files: CoverageFile[]
}

export interface StaleDecision {
  id: string
  trigger: string
  decision: string
  scope: string | null
  confidence: number
  created_at: string
  last_reviewed_at: string | null
  days_since_review: number
  staleness_threshold_days: number
  is_overdue: boolean
}

export interface AssumptionViolation {
  decision_id: string
  decision_trigger: string
  assumption: string
  invalidating_decision_id: string
  invalidating_trigger: string
  confidence: number
}

// ---------------------------------------------------------------------------
// Chat Q&A types
// ---------------------------------------------------------------------------

export interface SourceDecision {
  id: string
  trigger: string
  decision: string
  rationale: string
  confidence: number
  is_current: boolean
  entities: string[]
}

export interface MentionedEntity {
  name: string
  type: string
  decision_count: number
}

export interface ChatMessage {
  id: string
  role: "user" | "assistant"
  content: string
  timestamp: string
  source_decisions?: SourceDecision[]
  mentioned_entities?: MentionedEntity[]
}

export interface ChatSession {
  id: string
  title: string | null
  status: "active" | "archived"
  project_filter: string | null
  created_at: string
  updated_at: string
  messages: ChatMessage[]
}

export interface ChatSessionListItem {
  id: string
  title: string | null
  status: string
  created_at: string
  updated_at: string
  message_count: number
  last_message_preview: string | null
}

export interface SuggestedQuestion {
  question: string
  category: "why" | "evolution" | "overview" | "comparison"
}
