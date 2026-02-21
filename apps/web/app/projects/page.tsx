"use client"

import { useState } from "react"
import { useRouter } from "next/navigation"
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query"
import {
  Folder,
  Trash2,
  RefreshCw,
  Eye,
  Loader2,
  AlertTriangle,
  CheckCircle2,
  FileText,
  Network,
} from "lucide-react"

import { AppShell } from "@/components/layout/app-shell"
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from "@/components/ui/card"
import { Button } from "@/components/ui/button"
import { Badge } from "@/components/ui/badge"
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
  DialogDescription,
  DialogFooter,
} from "@/components/ui/dialog"
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table"
import { api } from "@/lib/api"

interface ProjectListItem {
  name: string
  decision_count: number
  created_at: string | null
}

type ActionType = "delete" | "reset"

export default function ProjectsPage() {
  const router = useRouter()
  const queryClient = useQueryClient()
  const [selectedProject, setSelectedProject] = useState<string | null>(null)
  const [actionType, setActionType] = useState<ActionType>("delete")
  const [showConfirmDialog, setShowConfirmDialog] = useState(false)

  // Fetch projects list
  const { data: projects, isLoading } = useQuery<ProjectListItem[]>({
    queryKey: ["projects-list"],
    queryFn: async () => {
      const response = await fetch(`${process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000"}/api/projects`)
      if (!response.ok) throw new Error("Failed to fetch projects")
      return response.json()
    },
  })

  // Delete/Reset project mutation
  const projectActionMutation = useMutation({
    mutationFn: async ({ name, action }: { name: string; action: ActionType }) => {
      const endpoint = action === "delete"
        ? `/api/projects/${encodeURIComponent(name)}?confirm=true`
        : `/api/projects/${encodeURIComponent(name)}/reset?confirm=true`

      const response = await fetch(
        `${process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000"}${endpoint}`,
        { method: action === "delete" ? "DELETE" : "POST" }
      )

      if (!response.ok) {
        const error = await response.json()
        throw new Error(error.detail || `Failed to ${action} project`)
      }

      return response.json()
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["projects-list"] })
      queryClient.invalidateQueries({ queryKey: ["project-counts"] })
      queryClient.invalidateQueries({ queryKey: ["decisions"] })
      queryClient.invalidateQueries({ queryKey: ["dashboard-stats"] })
      queryClient.invalidateQueries({ queryKey: ["graph"] })
      setShowConfirmDialog(false)
      setSelectedProject(null)
    },
  })

  const handleAction = (project: string, action: ActionType) => {
    setSelectedProject(project)
    setActionType(action)
    setShowConfirmDialog(true)
  }

  const confirmAction = () => {
    if (selectedProject) {
      projectActionMutation.mutate({ name: selectedProject, action: actionType })
    }
  }

  const formatDate = (isoDate: string | null) => {
    if (!isoDate) return "Unknown"
    const date = new Date(isoDate)
    return date.toLocaleDateString("en-US", { year: "numeric", month: "short", day: "numeric" })
  }

  return (
    <AppShell>
      <div className="p-6 space-y-6">
        {/* Header */}
        <div className="flex items-center justify-between">
          <div>
            <h1 className="text-3xl font-bold tracking-tight text-slate-100">Projects</h1>
            <p className="text-slate-400">
              Manage your knowledge graph projects
            </p>
          </div>
        </div>

        {/* Projects Table */}
        <Card className="bg-white/[0.03] backdrop-blur-xl border-white/[0.06]">
          <CardHeader>
            <div className="flex items-center gap-3">
              <div className="h-10 w-10 rounded-xl bg-cyan-500/10 flex items-center justify-center">
                <Folder className="h-5 w-5 text-cyan-400" />
              </div>
              <div>
                <CardTitle className="text-slate-100">All Projects</CardTitle>
                <CardDescription className="text-slate-400">
                  {projects?.length || 0} project{projects?.length !== 1 ? "s" : ""}
                </CardDescription>
              </div>
            </div>
          </CardHeader>
          <CardContent>
            {isLoading ? (
              <div className="flex items-center justify-center py-12">
                <Loader2 className="h-8 w-8 animate-spin text-cyan-400" />
              </div>
            ) : projects?.length === 0 ? (
              <div className="text-center py-12">
                <Folder className="h-12 w-12 text-slate-600 mx-auto mb-4" />
                <p className="text-slate-400 mb-2">No projects yet</p>
                <p className="text-sm text-slate-500">
                  Projects are created automatically when you tag decisions with a project name
                </p>
              </div>
            ) : (
              <div className="rounded-lg border border-white/10 overflow-hidden">
                <Table>
                  <TableHeader>
                    <TableRow className="hover:bg-transparent border-b border-white/10">
                      <TableHead className="text-slate-300">Project Name</TableHead>
                      <TableHead className="text-slate-300">Decisions</TableHead>
                      <TableHead className="text-slate-300">Created</TableHead>
                      <TableHead className="text-slate-300 text-right">Actions</TableHead>
                    </TableRow>
                  </TableHeader>
                  <TableBody>
                    {projects?.map((project) => (
                      <TableRow
                        key={project.name}
                        className="border-b border-white/5 hover:bg-white/[0.02] transition-colors"
                      >
                        <TableCell className="font-medium text-slate-100">
                          <div className="flex items-center gap-2">
                            <Folder className="h-4 w-4 text-cyan-400" />
                            <button
                              onClick={() => router.push(`/graph?project=${encodeURIComponent(project.name)}`)}
                              className="hover:underline hover:text-cyan-400 transition-colors"
                            >
                              {project.name}
                            </button>
                          </div>
                        </TableCell>
                        <TableCell>
                          <div className="flex items-center gap-2">
                            <FileText className="h-4 w-4 text-slate-400" />
                            <span className="text-slate-300">{project.decision_count}</span>
                          </div>
                        </TableCell>
                        <TableCell className="text-slate-400">
                          {formatDate(project.created_at)}
                        </TableCell>
                        <TableCell>
                          <div className="flex items-center justify-end gap-2">
                            <Button
                              variant="ghost"
                              size="sm"
                              onClick={() => router.push(`/graph?project=${encodeURIComponent(project.name)}`)}
                              className="hover:bg-cyan-500/10 hover:text-cyan-400"
                            >
                              <Eye className="h-4 w-4 mr-1" />
                              View Graph
                            </Button>
                            <Button
                              variant="ghost"
                              size="sm"
                              onClick={() => handleAction(project.name, "reset")}
                              className="hover:bg-yellow-500/10 hover:text-yellow-400"
                            >
                              <RefreshCw className="h-4 w-4 mr-1" />
                              Reset
                            </Button>
                            <Button
                              variant="ghost"
                              size="sm"
                              onClick={() => handleAction(project.name, "delete")}
                              className="hover:bg-red-500/10 hover:text-red-400"
                            >
                              <Trash2 className="h-4 w-4 mr-1" />
                              Delete
                            </Button>
                          </div>
                        </TableCell>
                      </TableRow>
                    ))}
                  </TableBody>
                </Table>
              </div>
            )}
          </CardContent>
        </Card>

        {/* Info Card */}
        <Card className="bg-white/[0.03] backdrop-blur-xl border-white/[0.06]">
          <CardContent className="pt-6">
            <div className="flex items-start gap-4">
              <div className="h-10 w-10 rounded-xl bg-blue-500/10 flex items-center justify-center shrink-0">
                <Network className="h-5 w-5 text-blue-400" />
              </div>
              <div>
                <h3 className="font-medium mb-1 text-slate-100">About Projects</h3>
                <p className="text-sm text-slate-400 mb-2">
                  Projects are organizational units for grouping related decisions in your knowledge graph.
                  Each decision can be tagged with a project name during creation (interview, manual entry, or import).
                </p>
                <ul className="text-sm text-slate-400 space-y-1">
                  <li>• <strong className="text-slate-300">View Graph</strong>: Navigate to the graph page filtered by this project</li>
                  <li>• <strong className="text-slate-300">Reset</strong>: Delete all decisions in the project (useful for re-importing)</li>
                  <li>• <strong className="text-slate-300">Delete</strong>: Permanently remove the project and all its decisions</li>
                </ul>
              </div>
            </div>
          </CardContent>
        </Card>
      </div>

      {/* Confirmation Dialog */}
      <Dialog open={showConfirmDialog} onOpenChange={setShowConfirmDialog}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle className="flex items-center gap-2">
              <AlertTriangle className={actionType === "delete" ? "h-5 w-5 text-red-400" : "h-5 w-5 text-yellow-400"} />
              {actionType === "delete" ? "Delete" : "Reset"} Project
            </DialogTitle>
            <DialogDescription>
              {actionType === "delete" ? (
                <>
                  This will permanently delete all <strong>{projects?.find(p => p.name === selectedProject)?.decision_count || 0} decisions</strong> in the project <strong>&ldquo;{selectedProject}&rdquo;</strong>.
                  Orphaned entities will also be removed. This action cannot be undone.
                </>
              ) : (
                <>
                  This will delete all <strong>{projects?.find(p => p.name === selectedProject)?.decision_count || 0} decisions</strong> in <strong>&ldquo;{selectedProject}&rdquo;</strong> to prepare for re-import.
                  You can re-import the project&apos;s data after reset.
                </>
              )}
            </DialogDescription>
          </DialogHeader>
          <DialogFooter>
            <Button
              variant="outline"
              onClick={() => setShowConfirmDialog(false)}
              disabled={projectActionMutation.isPending}
            >
              Cancel
            </Button>
            <Button
              variant={actionType === "delete" ? "destructive" : "default"}
              onClick={confirmAction}
              disabled={projectActionMutation.isPending}
              className={actionType === "reset" ? "bg-yellow-500 hover:bg-yellow-600 text-slate-900" : ""}
            >
              {projectActionMutation.isPending ? (
                <>
                  <Loader2 className="h-4 w-4 mr-2 animate-spin" />
                  {actionType === "delete" ? "Deleting..." : "Resetting..."}
                </>
              ) : (
                <>
                  {actionType === "delete" ? (
                    <>
                      <Trash2 className="h-4 w-4 mr-2" />
                      Delete Project
                    </>
                  ) : (
                    <>
                      <RefreshCw className="h-4 w-4 mr-2" />
                      Reset Project
                    </>
                  )}
                </>
              )}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </AppShell>
  )
}
