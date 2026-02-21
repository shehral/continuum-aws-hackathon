import { datadogRum } from '@datadog/browser-rum';

/**
 * Track when a user views a decision in the knowledge graph
 */
export const trackDecisionViewed = (decisionId: string, trigger: string, scope?: string) => {
  datadogRum.addAction('decision_viewed', {
    decision_id: decisionId,
    trigger: trigger.substring(0, 100), // Limit length
    scope: scope || 'unknown',
  });
};

/**
 * Track graph interactions (node clicks, zoom, pan, etc.)
 */
export const trackGraphInteraction = (action: string, nodeType: string, nodeId?: string) => {
  datadogRum.addAction('graph_interaction', {
    action,
    node_type: nodeType,
    node_id: nodeId,
  });
};

/**
 * Track search queries and their effectiveness
 */
export const trackSearchQuery = (query: string, resultCount: number, searchType: 'semantic' | 'fulltext' = 'semantic') => {
  datadogRum.addAction('search_performed', {
    query: query.substring(0, 100),
    result_count: resultCount,
    search_type: searchType,
    has_results: resultCount > 0,
  });
};

/**
 * Track when a user starts importing Claude Code logs
 */
export const trackImportStarted = (fileCount: number, totalSizeBytes?: number) => {
  datadogRum.addAction('import_started', {
    file_count: fileCount,
    total_size_bytes: totalSizeBytes,
  });
};

/**
 * Track import completion with metrics
 */
export const trackImportCompleted = (
  fileCount: number,
  decisionsExtracted: number,
  entitiesFound: number,
  durationMs: number
) => {
  datadogRum.addAction('import_completed', {
    file_count: fileCount,
    decisions_extracted: decisionsExtracted,
    entities_found: entitiesFound,
    duration_ms: durationMs,
    decisions_per_file: fileCount > 0 ? decisionsExtracted / fileCount : 0,
  });
};

/**
 * Track errors during import
 */
export const trackImportError = (errorMessage: string, fileName?: string) => {
  datadogRum.addError(new Error(`Import failed: ${errorMessage}`), {
    file_name: fileName,
    error_type: 'import_error',
  });
};

/**
 * Track when users explore dormant alternatives
 */
export const trackDormantAlternativeViewed = (alternativeText: string, daysSinceRejection: number) => {
  datadogRum.addAction('dormant_alternative_viewed', {
    alternative: alternativeText.substring(0, 100),
    days_since_rejection: daysSinceRejection,
  });
};

/**
 * Track timeline chart interactions
 */
export const trackTimelineInteraction = (action: string, period?: string, scope?: string) => {
  datadogRum.addAction('timeline_interaction', {
    action,
    period,
    scope,
  });
};

/**
 * Track MCP tool usage (when developers query via Claude Code)
 */
export const trackMCPToolUsage = (toolName: string, success: boolean) => {
  datadogRum.addAction('mcp_tool_used', {
    tool_name: toolName,
    success,
  });
};

/**
 * Track page navigation
 */
export const trackPageView = (pageName: string, metadata?: Record<string, any>) => {
  datadogRum.addAction('page_viewed', {
    page_name: pageName,
    ...metadata,
  });
};
