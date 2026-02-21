"use client"

import { useState, useCallback } from "react"
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query"

import { AppShell } from "@/components/layout/app-shell"
import { KnowledgeGraph } from "@/components/graph/knowledge-graph"
import { Button } from "@/components/ui/button"
import { ErrorState } from "@/components/ui/error-state"
import { GraphSkeleton } from "@/components/ui/skeleton"
import { api } from "@/lib/api"
import { RefreshCw, Trash2, AlertTriangle } from "lucide-react"
import { Tooltip, TooltipContent, TooltipProvider, TooltipTrigger } from "@/components/ui/tooltip"
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog"

export default function GraphPage() {
  const queryClient = useQueryClient()
  const [sourceFilter, setSourceFilter] = useState<string | null>(null)
  const [projectFilter, setProjectFilter] = useState<string | null>(null)
  const [showDeleteDialog, setShowDeleteDialog] = useState(false)

  const {
    data: graphData,
    isLoading,
    error,
    refetch,
    isFetching,
  } = useQuery({
    queryKey: ["graph", sourceFilter, projectFilter],
    queryFn: () =>
      api.getGraph({
        include_similarity: true,
        include_temporal: true,
        include_entity_relations: true,
        source_filter: sourceFilter as "claude_logs" | "interview" | "manual" | "unknown" | undefined,
        project_filter: projectFilter || undefined,
      }),
    staleTime: 5 * 60 * 1000, // 5 minutes for graph data (P1-5)
    gcTime: 10 * 60 * 1000, // 10 minutes garbage collection
  })

  const { data: sourceCounts } = useQuery({
    queryKey: ["graph-sources"],
    queryFn: () => api.getDecisionSources(),
    staleTime: 5 * 60 * 1000,
  })

  const { data: projectCounts } = useQuery({
    queryKey: ["project-counts"],
    queryFn: () => api.getProjectCounts(),
    staleTime: 5 * 60 * 1000,
  })

  const deleteMutation = useMutation({
    mutationFn: (id: string) => api.deleteDecision(id),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["graph"] })
      queryClient.invalidateQueries({ queryKey: ["graph-sources"] })
      queryClient.invalidateQueries({ queryKey: ["decisions"] })
      queryClient.invalidateQueries({ queryKey: ["dashboard-stats"] })
    },
  })

  const deleteProjectMutation = useMutation({
    mutationFn: async (projectName: string | null) => {
      if (!projectName) {
        // Reset entire graph
        const response = await fetch(
          `${process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000"}/api/graph/reset?confirm=true`,
          { method: "POST" }
        )
        if (!response.ok) {
          const error = await response.json()
          throw new Error(error.detail || "Failed to reset graph")
        }
        return response.json()
      } else {
        // Delete specific project
        const response = await fetch(
          `${process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000"}/api/projects/${encodeURIComponent(projectName)}?confirm=true`,
          { method: "DELETE" }
        )
        if (!response.ok) {
          const error = await response.json()
          throw new Error(error.detail || "Failed to delete project")
        }
        return response.json()
      }
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["graph"] })
      queryClient.invalidateQueries({ queryKey: ["graph-sources"] })
      queryClient.invalidateQueries({ queryKey: ["project-counts"] })
      queryClient.invalidateQueries({ queryKey: ["decisions"] })
      queryClient.invalidateQueries({ queryKey: ["dashboard-stats"] })
      setShowDeleteDialog(false)
      setProjectFilter(null) // Clear filter after deletion
    },
  })

  const handleSourceFilterChange = useCallback((source: string | null) => {
    setSourceFilter(source)
  }, [])

  const handleProjectFilterChange = useCallback((project: string | null) => {
    setProjectFilter(project)
  }, [])

  const handleDeleteDecision = useCallback(async (decisionId: string) => {
    await deleteMutation.mutateAsync(decisionId)
  }, [deleteMutation])

  return (
    <AppShell>
      <div className="h-full flex flex-col">
        {/* Header */}
        <div className="flex items-center justify-between px-6 py-4 border-b border-white/[0.06] bg-slate-900/80 backdrop-blur-xl animate-in fade-in slide-in-from-top-4 duration-500">
          <div>
            <h1 className="text-2xl font-bold tracking-tight text-slate-100">Knowledge Graph</h1>
            <p className="text-sm text-slate-400">
              Explore decisions and their relationships
              {sourceFilter && (
                <span className="ml-2 text-xs px-2 py-0.5 rounded-full bg-cyan-500/20 text-cyan-400 border border-cyan-500/30">
                  Filtered: {sourceFilter === "claude_logs" ? "AI Extracted" :
                            sourceFilter === "interview" ? "Human Captured" :
                            sourceFilter === "manual" ? "Manual Entry" : "Legacy"}
                </span>
              )}
              {projectFilter && (
                <span className="ml-2 text-xs px-2 py-0.5 rounded-full bg-purple-500/20 text-purple-400 border border-purple-500/30">
                  Project: {projectFilter}
                </span>
              )}
            </p>
          </div>
          <div className="flex gap-2">
            <TooltipProvider>
              <Tooltip>
                <TooltipTrigger asChild>
                  <Button
                    variant="outline"
                    size="sm"
                    onClick={() => refetch()}
                    disabled={isFetching}
                    className="border-white/10 text-slate-300 hover:bg-white/[0.08] hover:text-slate-100 hover:scale-105 transition-all"
                    aria-label="Refresh graph"
                  >
                    <RefreshCw
                      className={`h-4 w-4 mr-2 ${isFetching ? "animate-spin" : ""}`}
                      aria-hidden="true"
                    />
                    Refresh
                  </Button>
                </TooltipTrigger>
                <TooltipContent>Reload graph data</TooltipContent>
              </Tooltip>
            </TooltipProvider>

            <TooltipProvider>
              <Tooltip>
                <TooltipTrigger asChild>
                  <Button
                    variant="outline"
                    size="sm"
                    onClick={() => setShowDeleteDialog(true)}
                    className="border-red-500/30 text-red-400 hover:bg-red-500/20 hover:text-red-300 hover:border-red-500/50 hover:scale-105 transition-all"
                    aria-label={projectFilter ? "Delete project" : "Reset all graph data"}
                  >
                    <Trash2 className="h-4 w-4 mr-2" aria-hidden="true" />
                    {projectFilter ? "Delete Project" : "Reset Graph"}
                  </Button>
                </TooltipTrigger>
                <TooltipContent>
                  {projectFilter
                    ? `Delete all decisions in ${projectFilter}`
                    : "Delete ALL decisions and reset the graph"}
                </TooltipContent>
              </Tooltip>
            </TooltipProvider>
          </div>
        </div>

        {/* Graph */}
        <div className="flex-1" role="main" aria-label="Knowledge graph visualization area">
          {isLoading ? (
            <div aria-live="polite" aria-busy="true" className="h-full">
              <GraphSkeleton />
            </div>
          ) : error ? (
            <ErrorState
              title="Failed to load graph"
              message="We couldn't load your knowledge graph. Please try again."
              error={error instanceof Error ? error : null}
              retry={() => refetch()}
            />
          ) : (
            <KnowledgeGraph
              data={graphData}
              sourceFilter={sourceFilter}
              onSourceFilterChange={handleSourceFilterChange}
              sourceCounts={sourceCounts || {}}
              projectFilter={projectFilter}
              onProjectFilterChange={handleProjectFilterChange}
              projectCounts={projectCounts || {}}
              onDeleteDecision={handleDeleteDecision}
            />
          )}
        </div>
      </div>

      {/* Delete/Reset Confirmation Dialog */}
      <Dialog open={showDeleteDialog} onOpenChange={setShowDeleteDialog}>
        <DialogContent className="bg-slate-900 border-red-500/30">
          <DialogHeader>
            <DialogTitle className="flex items-center gap-2 text-red-400">
              <AlertTriangle className="h-5 w-5" />
              {projectFilter ? "Delete Project" : "Reset Graph"}
            </DialogTitle>
            <DialogDescription className="text-slate-300">
              {projectFilter ? (
                <>
                  Are you sure you want to delete the project{" "}
                  <span className="font-semibold text-purple-400">{projectFilter}</span>?
                  <br />
                  <br />
                  This will permanently delete all decisions in this project.
                </>
              ) : (
                <>
                  Are you sure you want to <span className="font-semibold text-red-400">reset the entire graph</span>?
                  <br />
                  <br />
                  This will permanently delete <span className="font-semibold">ALL decisions and entities</span> from the knowledge graph.
                </>
              )}
              <br />
              <br />
              Orphaned entities will be cleaned up automatically.
              <br />
              <br />
              <span className="text-red-400 font-semibold">This action cannot be undone.</span>
            </DialogDescription>
          </DialogHeader>
          <DialogFooter>
            <Button
              variant="outline"
              onClick={() => setShowDeleteDialog(false)}
              disabled={deleteProjectMutation.isPending}
              className="border-white/10"
            >
              Cancel
            </Button>
            <Button
              variant="destructive"
              onClick={() => deleteProjectMutation.mutate(projectFilter)}
              disabled={deleteProjectMutation.isPending}
              className="bg-red-600 hover:bg-red-700"
            >
              {deleteProjectMutation.isPending
                ? (projectFilter ? "Deleting Project..." : "Resetting Graph...")
                : (projectFilter ? "Delete Project" : "Reset Graph")}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </AppShell>
  )
}
