"use client"

import { useState, useEffect } from "react"
import { useRouter } from "next/navigation"
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query"
import {
  FolderOpen,
  MessageSquarePlus,
  PenLine,
  Play,
  Loader2,
  CheckCircle2,
  AlertCircle,
  FileJson,
  Filter,
  Eye,
  Trash2,
  RefreshCw,
  FileStack,
  XCircle,
  StopCircle,
} from "lucide-react"

import { AppShell } from "@/components/layout/app-shell"
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from "@/components/ui/card"
import { Button } from "@/components/ui/button"
import { Badge } from "@/components/ui/badge"
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select"
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
  DialogDescription,
  DialogFooter,
} from "@/components/ui/dialog"
import { ScrollArea } from "@/components/ui/scroll-area"
import { Tooltip, TooltipContent, TooltipProvider, TooltipTrigger } from "@/components/ui/tooltip"
import { Progress } from "@/components/ui/progress"
import { FileBrowser } from "@/components/import/file-browser"
import { ProjectSelector } from "@/components/projects/project-selector"
import { api } from "@/lib/api"

type IngestionStatus = "idle" | "running" | "success" | "error" | "cancelled"

export default function AddKnowledgePage() {
  const router = useRouter()
  const queryClient = useQueryClient()
  const [ingestionStatus, setIngestionStatus] = useState<IngestionStatus>("idle")
  const [ingestionResult, setIngestionResult] = useState<{ processed: number; decisions: number } | null>(null)
  const [selectedProject, setSelectedProject] = useState<string>("all")
  const [showPreview, setShowPreview] = useState(false)
  const [showResetConfirm, setShowResetConfirm] = useState(false)
  const [currentJobId, setCurrentJobId] = useState<string | null>(null)

  // Selective import state
  const [selectedFiles, setSelectedFiles] = useState<string[]>([])
  const [targetProject, setTargetProject] = useState<string | null>(null)
  const [showFileBrowser, setShowFileBrowser] = useState(false)

  // Import progress tracking
  const { data: importProgress, refetch: refetchProgress } = useQuery({
    queryKey: ["import-progress"],
    queryFn: () => api.getImportProgress(),
    refetchInterval: ingestionStatus === "running" ? 1000 : false,
    enabled: ingestionStatus === "running",
  })

  // Update local state based on progress
  useEffect(() => {
    if (importProgress) {
      if (importProgress.status === "running" || importProgress.status === "starting") {
        setIngestionStatus("running")
      } else if (importProgress.status === "completed" || importProgress.status.startsWith("completed")) {
        setIngestionStatus("success")
        setIngestionResult({
          processed: importProgress.processed_files,
          decisions: importProgress.decisions_extracted,
        })
        queryClient.invalidateQueries({ queryKey: ["decisions"] })
        queryClient.invalidateQueries({ queryKey: ["dashboard-stats"] })
        queryClient.invalidateQueries({ queryKey: ["graph"] })
      } else if (importProgress.status === "cancelled") {
        setIngestionStatus("cancelled")
        setIngestionResult({
          processed: importProgress.processed_files,
          decisions: importProgress.decisions_extracted,
        })
      } else if (importProgress.status.startsWith("error")) {
        setIngestionStatus("error")
      }
    }
  }, [importProgress, queryClient])

  // Check for existing running import on mount
  useEffect(() => {
    api.getImportProgress().then((progress) => {
      if (progress.status === "running" || progress.status === "starting") {
        setIngestionStatus("running")
        setCurrentJobId(progress.job_id)
      }
    })
  }, [])

  // Fetch available projects
  const { data: projects, isLoading: projectsLoading } = useQuery({
    queryKey: ["ingest-projects"],
    queryFn: () => api.getAvailableProjects(),
  })

  // Fetch project counts for target project selector
  const { data: projectCounts } = useQuery({
    queryKey: ["project-counts"],
    queryFn: () => api.getProjectCounts(),
    staleTime: 5 * 60 * 1000,
  })

  const availableProjects = Object.keys(projectCounts || {}).filter((p) => p !== "unassigned")

  // Fetch import files
  const { data: importFiles, isLoading: filesLoading } = useQuery({
    queryKey: ["import-files"],
    queryFn: () => api.getImportFiles(),
    enabled: showFileBrowser,
  })

  // Preview query
  const { data: preview, isLoading: previewLoading, refetch: refetchPreview } = useQuery({
    queryKey: ["ingest-preview", selectedProject],
    queryFn: () => api.previewIngestion({
      project: selectedProject === "all" ? undefined : selectedProject,
      limit: 20,
    }),
    enabled: showPreview,
  })

  const ingestionMutation = useMutation({
    mutationFn: () => api.triggerIngestion({
      project: selectedProject === "all" ? undefined : selectedProject,
    }),
    onMutate: () => {
      setIngestionStatus("running")
      setIngestionResult(null)
    },
    onSuccess: (data) => {
      if (data.status === "started") {
        setCurrentJobId(data.job_id)
        // Progress polling will handle the rest
      } else if (data.status === "no_files") {
        setIngestionStatus("idle")
        setIngestionResult({ processed: 0, decisions: 0 })
      }
    },
    onError: () => {
      setIngestionStatus("error")
    },
  })

  const selectiveImportMutation = useMutation({
    mutationFn: () => api.importSelectedFiles(selectedFiles, targetProject),
    onMutate: () => {
      setIngestionStatus("running")
      setIngestionResult(null)
    },
    onSuccess: (data) => {
      if (data.status === "started") {
        setCurrentJobId(data.job_id)
        setSelectedFiles([])
        setShowFileBrowser(false)
        // Progress polling will handle the rest
      } else if (data.status === "no_valid_files") {
        setIngestionStatus("error")
      }
    },
    onError: () => {
      setIngestionStatus("error")
    },
  })

  const cancelMutation = useMutation({
    mutationFn: () => api.cancelImport(),
    onSuccess: () => {
      // Status will update via progress polling
    },
  })

  const resetMutation = useMutation({
    mutationFn: () => api.resetGraph(),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["decisions"] })
      queryClient.invalidateQueries({ queryKey: ["dashboard-stats"] })
      queryClient.invalidateQueries({ queryKey: ["graph"] })
      setShowResetConfirm(false)
    },
  })

  return (
    <AppShell>
      <div className="p-6 space-y-6">
        {/* Header */}
        <div className="flex items-center justify-between">
          <div>
            <h1 className="text-3xl font-bold tracking-tight text-slate-100">Add Knowledge</h1>
            <p className="text-slate-400">
              Choose how you want to add decisions to your knowledge graph
            </p>
          </div>
          <Button
            variant="outline"
            size="sm"
            className="text-red-400 border-red-400/30 hover:bg-red-400/10"
            onClick={() => setShowResetConfirm(true)}
          >
            <Trash2 className="h-4 w-4 mr-2" />
            Reset Graph
          </Button>
        </div>

        {/* Import Section - Enhanced */}
        <Card className="bg-white/[0.03] backdrop-blur-xl border-white/[0.06]">
          <CardHeader>
            <div className="flex items-start justify-between">
              <div className="flex items-center gap-3">
                <div className="h-10 w-10 rounded-xl bg-cyan-500/10 flex items-center justify-center">
                  <FolderOpen className="h-5 w-5 text-cyan-400" />
                </div>
                <div>
                  <CardTitle className="text-slate-100">Import from Claude Code</CardTitle>
                  <CardDescription className="text-slate-400">
                    Parse conversation logs and extract decisions using AI
                  </CardDescription>
                </div>
              </div>
              <Badge className="bg-cyan-500/20 text-cyan-400 border-cyan-500/30">
                Automatic
              </Badge>
            </div>
          </CardHeader>
          <CardContent className="space-y-4">
            {/* Project Filter */}
            <div className="flex items-center gap-4">
              <div className="flex items-center gap-2">
                <Filter className="h-4 w-4 text-slate-400" />
                <span className="text-sm text-slate-400">Project:</span>
              </div>
              <Select value={selectedProject} onValueChange={setSelectedProject}>
                <SelectTrigger className="w-[280px] bg-white/[0.05] border-white/10">
                  <SelectValue placeholder="Select a project" />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value="all">All Projects</SelectItem>
                  {projects?.map((p) => (
                    <SelectItem key={p.dir} value={p.name}>
                      {p.name} ({p.files} files)
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
              <Button
                variant="outline"
                size="sm"
                onClick={() => {
                  setShowPreview(true)
                  refetchPreview()
                }}
                className="bg-white/[0.05] border-white/10"
              >
                <Eye className="h-4 w-4 mr-2" />
                Preview
              </Button>
            </div>

            {/* Action Buttons */}
            <div className="flex gap-3">
              <Button
                onClick={() => ingestionMutation.mutate()}
                disabled={ingestionStatus === "running"}
                className="bg-gradient-to-r from-cyan-500 to-teal-400 text-slate-900 font-semibold shadow-[0_4px_16px_rgba(34,211,238,0.3)] hover:shadow-[0_6px_20px_rgba(34,211,238,0.4)]"
              >
                {ingestionStatus === "running" ? (
                  <>
                    <Loader2 className="h-4 w-4 mr-2 animate-spin" />
                    Extracting decisions...
                  </>
                ) : (
                  <>
                    <Play className="h-4 w-4 mr-2" />
                    Import {selectedProject === "all" ? "All" : selectedProject}
                  </>
                )}
              </Button>
            </div>

            {/* Progress Bar */}
            {ingestionStatus === "running" && importProgress && (
              <div className="space-y-3 p-4 bg-white/[0.03] rounded-lg border border-white/[0.06]">
                <div className="flex items-center justify-between">
                  <div className="flex items-center gap-2">
                    <Loader2 className="h-4 w-4 animate-spin text-cyan-400" />
                    <span className="text-sm font-medium text-slate-200">
                      Importing... {importProgress.processed_files}/{importProgress.total_files} files
                    </span>
                  </div>
                  <Button
                    size="sm"
                    variant="outline"
                    onClick={() => cancelMutation.mutate()}
                    disabled={cancelMutation.isPending}
                    className="text-red-400 border-red-400/30 hover:bg-red-400/10"
                  >
                    {cancelMutation.isPending ? (
                      <Loader2 className="h-3 w-3 animate-spin" />
                    ) : (
                      <StopCircle className="h-3 w-3 mr-1" />
                    )}
                    Cancel
                  </Button>
                </div>
                <Progress
                  value={importProgress.total_files > 0
                    ? (importProgress.processed_files / importProgress.total_files) * 100
                    : 0}
                  className="h-2"
                />
                <div className="flex justify-between text-xs text-slate-400">
                  <span>
                    {importProgress.current_file
                      ? `Processing: ${importProgress.current_file}`
                      : "Starting..."}
                  </span>
                  <span>{importProgress.decisions_extracted} decisions extracted</span>
                </div>
              </div>
            )}

            {/* Status Messages */}
            {ingestionStatus === "success" && ingestionResult && (
              <div className="flex items-center gap-2 text-sm text-green-400 bg-green-400/10 px-3 py-2 rounded-lg">
                <CheckCircle2 className="h-4 w-4" />
                Processed {ingestionResult.processed} files, extracted {ingestionResult.decisions} decisions
              </div>
            )}
            {ingestionStatus === "cancelled" && ingestionResult && (
              <div className="flex items-center gap-2 text-sm text-amber-400 bg-amber-400/10 px-3 py-2 rounded-lg">
                <XCircle className="h-4 w-4" />
                Import cancelled. Processed {ingestionResult.processed} files, extracted {ingestionResult.decisions} decisions
              </div>
            )}
            {ingestionStatus === "error" && (
              <div className="flex items-center gap-2 text-sm text-red-400 bg-red-400/10 px-3 py-2 rounded-lg">
                <AlertCircle className="h-4 w-4" />
                Import failed. Check API keys and try again.
              </div>
            )}
          </CardContent>
        </Card>

        {/* Selective Import Section */}
        <Card className="bg-white/[0.03] backdrop-blur-xl border-white/[0.06]">
          <CardHeader>
            <div className="flex items-start justify-between">
              <div className="flex items-center gap-3">
                <div className="h-10 w-10 rounded-xl bg-blue-500/10 flex items-center justify-center">
                  <FileStack className="h-5 w-5 text-blue-400" />
                </div>
                <div>
                  <CardTitle className="text-slate-100">Selective File Import</CardTitle>
                  <CardDescription className="text-slate-400">
                    Choose specific files and assign them to a target project
                  </CardDescription>
                </div>
              </div>
              <Badge className="bg-blue-500/20 text-blue-400 border-blue-500/30">
                Advanced
              </Badge>
            </div>
          </CardHeader>
          <CardContent className="space-y-4">
            {!showFileBrowser ? (
              <Button
                onClick={() => setShowFileBrowser(true)}
                variant="outline"
                className="w-full bg-white/[0.05] border-white/10 text-slate-300 hover:bg-white/[0.08]"
              >
                <FileStack className="h-4 w-4 mr-2" />
                Browse Files
              </Button>
            ) : (
              <>
                {filesLoading ? (
                  <div className="flex items-center justify-center py-8">
                    <Loader2 className="h-6 w-6 animate-spin text-blue-400" />
                  </div>
                ) : (
                  <>
                    <FileBrowser
                      files={importFiles || []}
                      selectedFiles={selectedFiles}
                      onSelectionChange={setSelectedFiles}
                    />

                    {/* Target Project Selection */}
                    {selectedFiles.length > 0 && (
                      <div className="space-y-3 pt-2 border-t border-white/10">
                        <div>
                          <label className="text-sm font-medium text-slate-300 mb-2 block">
                            Target Project <span className="text-slate-500">(optional)</span>
                          </label>
                          <p className="text-xs text-slate-500 mb-2">
                            Assign selected files to a specific project, or leave empty to use their original project names
                          </p>
                          <ProjectSelector
                            value={targetProject}
                            onChange={setTargetProject}
                            projects={availableProjects}
                            placeholder="Use original project names..."
                          />
                        </div>

                        <div className="flex gap-2">
                          <Button
                            onClick={() => selectiveImportMutation.mutate()}
                            disabled={ingestionStatus === "running"}
                            className="flex-1 bg-gradient-to-r from-blue-500 to-indigo-400 text-slate-900 font-semibold shadow-[0_4px_16px_rgba(59,130,246,0.3)] hover:shadow-[0_6px_20px_rgba(59,130,246,0.4)]"
                          >
                            {ingestionStatus === "running" ? (
                              <>
                                <Loader2 className="h-4 w-4 mr-2 animate-spin" />
                                Importing {selectedFiles.length} files...
                              </>
                            ) : (
                              <>
                                <Play className="h-4 w-4 mr-2" />
                                Import {selectedFiles.length} Selected
                              </>
                            )}
                          </Button>
                          <Button
                            variant="outline"
                            onClick={() => {
                              setShowFileBrowser(false)
                              setSelectedFiles([])
                              setTargetProject(null)
                            }}
                            className="bg-white/[0.05] border-white/10"
                          >
                            Cancel
                          </Button>
                        </div>
                      </div>
                    )}
                  </>
                )}
              </>
            )}
          </CardContent>
        </Card>

        {/* Other Methods */}
        <div className="grid gap-6 md:grid-cols-2 items-stretch">
          {/* AI Interview */}
          <Card className="bg-white/[0.03] backdrop-blur-xl border-white/[0.06] flex flex-col">
            <CardHeader>
              <div className="flex items-start justify-between">
                <div className="h-10 w-10 rounded-xl bg-purple-500/10 flex items-center justify-center">
                  <MessageSquarePlus className="h-5 w-5 text-purple-400" />
                </div>
                <Badge className="bg-purple-500/20 text-purple-400 border-purple-500/30">
                  Interactive
                </Badge>
              </div>
              <CardTitle className="mt-4 text-slate-100">AI Interview</CardTitle>
              <CardDescription className="text-slate-400">
                Guided conversation to document decisions step by step
              </CardDescription>
            </CardHeader>
            <CardContent className="flex-1 flex flex-col justify-end">
              <ul className="text-sm text-slate-400 space-y-1 mb-4">
                <li>• AI guides you through trigger → context → options → decision → rationale</li>
                <li>• Automatically extracts and links entities</li>
                <li>• Best for complex decisions</li>
              </ul>
              <Button
                onClick={() => router.push("/capture")}
                className="w-full bg-purple-500/20 text-purple-300 border border-purple-500/30 hover:bg-purple-500/30"
              >
                <MessageSquarePlus className="h-4 w-4 mr-2" />
                Start Interview
              </Button>
            </CardContent>
          </Card>

          {/* Manual Entry */}
          <Card className="bg-white/[0.03] backdrop-blur-xl border-white/[0.06] flex flex-col">
            <CardHeader>
              <div className="flex items-start justify-between">
                <div className="h-10 w-10 rounded-xl bg-slate-500/10 flex items-center justify-center">
                  <PenLine className="h-5 w-5 text-slate-400" />
                </div>
                <Badge className="bg-slate-500/20 text-slate-400 border-slate-500/30">
                  Quick
                </Badge>
              </div>
              <CardTitle className="mt-4 text-slate-100">Manual Entry</CardTitle>
              <CardDescription className="text-slate-400">
                Direct form entry when you know all the details
              </CardDescription>
            </CardHeader>
            <CardContent className="flex-1 flex flex-col justify-end">
              <ul className="text-sm text-slate-400 space-y-1 mb-4">
                <li>• Simple form-based entry</li>
                <li>• No AI processing required</li>
                <li>• Works offline</li>
              </ul>
              <Button
                onClick={() => router.push("/decisions?add=true")}
                variant="outline"
                className="w-full bg-white/[0.05] border-white/10 text-slate-300 hover:bg-white/[0.08]"
              >
                <PenLine className="h-4 w-4 mr-2" />
                Add Manually
              </Button>
            </CardContent>
          </Card>
        </div>

        {/* Info Section */}
        <Card className="bg-white/[0.03] backdrop-blur-xl border-white/[0.06]">
          <CardContent className="pt-6">
            <div className="flex items-start gap-4">
              <div className="h-10 w-10 rounded-xl bg-blue-500/10 flex items-center justify-center shrink-0">
                <FileJson className="h-5 w-5 text-blue-400" />
              </div>
              <div>
                <h3 className="font-medium mb-1 text-slate-100">How Import Works</h3>
                <p className="text-sm text-slate-400">
                  The import feature scans your Claude Code conversation logs stored at{" "}
                  <code className="px-1.5 py-0.5 bg-white/[0.05] rounded text-cyan-400 border border-white/10">~/.claude/projects</code>.
                  It uses NVIDIA&apos;s Llama 3.3 to analyze conversations and extract structured decision traces.
                  Each decision is linked to relevant entities (technologies, concepts, patterns) to build your knowledge graph.
                  Use the project filter to import only from specific projects.
                </p>
              </div>
            </div>
          </CardContent>
        </Card>
      </div>

      {/* Preview Dialog */}
      <Dialog open={showPreview} onOpenChange={setShowPreview}>
        <DialogContent className="max-w-2xl">
          <DialogHeader>
            <DialogTitle>Preview: {selectedProject === "all" ? "All Projects" : selectedProject}</DialogTitle>
            <DialogDescription>
              Conversations that will be processed for decision extraction
            </DialogDescription>
          </DialogHeader>
          <ScrollArea className="max-h-[400px]">
            {previewLoading ? (
              <div className="flex items-center justify-center py-8">
                <Loader2 className="h-6 w-6 animate-spin text-cyan-400" />
              </div>
            ) : preview?.previews.length === 0 ? (
              <p className="text-center text-slate-400 py-8">No conversations found</p>
            ) : (
              <div className="space-y-3">
                {preview?.previews.map((p, i) => (
                  <div key={i} className="p-3 bg-white/[0.03] rounded-lg border border-white/[0.06]">
                    <div className="flex items-center gap-2 mb-2">
                      <Badge variant="outline" className="text-xs">
                        {p.project}
                      </Badge>
                      <span className="text-xs text-slate-500">{p.messages} messages</span>
                    </div>
                    <TooltipProvider>
                      <Tooltip>
                        <TooltipTrigger asChild>
                          <p className="text-sm text-slate-400 line-clamp-3 cursor-help">{p.preview}</p>
                        </TooltipTrigger>
                        <TooltipContent side="bottom" className="max-w-md">
                          <p className="whitespace-pre-wrap">{p.preview}</p>
                        </TooltipContent>
                      </Tooltip>
                    </TooltipProvider>
                  </div>
                ))}
              </div>
            )}
          </ScrollArea>
          <DialogFooter>
            <Button variant="outline" onClick={() => setShowPreview(false)}>
              Close
            </Button>
            <Button onClick={() => {
              setShowPreview(false)
              ingestionMutation.mutate()
            }}>
              Import These
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      {/* Reset Confirmation Dialog */}
      <Dialog open={showResetConfirm} onOpenChange={setShowResetConfirm}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle className="text-red-400">Reset Knowledge Graph</DialogTitle>
            <DialogDescription>
              This will permanently delete all decisions, entities, and relationships.
              This action cannot be undone.
            </DialogDescription>
          </DialogHeader>
          <DialogFooter>
            <Button variant="outline" onClick={() => setShowResetConfirm(false)}>
              Cancel
            </Button>
            <Button
              variant="destructive"
              onClick={() => resetMutation.mutate()}
              disabled={resetMutation.isPending}
            >
              {resetMutation.isPending ? (
                <Loader2 className="h-4 w-4 mr-2 animate-spin" />
              ) : (
                <Trash2 className="h-4 w-4 mr-2" />
              )}
              Delete Everything
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </AppShell>
  )
}
