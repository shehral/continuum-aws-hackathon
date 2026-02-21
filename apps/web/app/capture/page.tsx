"use client"

import { useState, useCallback } from "react"
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query"
import { Plus, History, X, MessageSquare, Lightbulb, ArrowRight, PanelRightOpen, PanelRightClose } from "lucide-react"

import { AppShell } from "@/components/layout/app-shell"
import { ChatInterface } from "@/components/capture/chat-interface"
import {
  DecisionTraceIndicator,
  type TraceStage,
} from "@/components/capture/decision-trace-indicator"
import { Button } from "@/components/ui/button"
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card"
import { ScrollArea } from "@/components/ui/scroll-area"
import { Badge } from "@/components/ui/badge"
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
  DialogDescription,
  DialogFooter,
} from "@/components/ui/dialog"
import { api, type CaptureSession, type CaptureMessage, type Entity } from "@/lib/api"
import { ProjectSelector } from "@/components/projects/project-selector"

export default function CapturePage() {
  const queryClient = useQueryClient()
  const [activeSession, setActiveSession] = useState<CaptureSession | null>(null)
  const [messages, setMessages] = useState<CaptureMessage[]>([])
  const [currentStage, setCurrentStage] = useState<TraceStage>("trigger")
  const [completedStages, setCompletedStages] = useState<TraceStage[]>([])
  const [suggestedEntities, setSuggestedEntities] = useState<Entity[]>([])
  const [showCompleteDialog, setShowCompleteDialog] = useState(false)
  const [selectedProject, setSelectedProject] = useState<string | null>(null)
  const [showSessionHistory, setShowSessionHistory] = useState(false)

  // Fetch available projects
  const { data: projectCounts } = useQuery({
    queryKey: ["project-counts"],
    queryFn: () => api.getProjectCounts(),
    staleTime: 5 * 60 * 1000,
  })

  const projects = Object.keys(projectCounts || {}).filter((p) => p !== "unassigned")

  // Start session mutation
  const startSessionMutation = useMutation({
    mutationFn: () => api.startCaptureSession(selectedProject),
    onSuccess: (session) => {
      setActiveSession(session)
      setMessages([
        {
          id: "welcome",
          role: "assistant",
          content:
            "Hello! I'm here to help you capture a decision or piece of knowledge. Let's start with the basics.\n\nWhat triggered this decision or what problem were you trying to solve?",
          timestamp: new Date().toISOString(),
        },
      ])
      setCurrentStage("trigger")
      setCompletedStages([])
    },
  })

  // Send message mutation
  const sendMessageMutation = useMutation({
    mutationFn: async (content: string) => {
      if (!activeSession) throw new Error("No active session")
      return api.sendCaptureMessage(activeSession.id, content)
    },
    onSuccess: (response) => {
      // Add response to messages
      setMessages((prev) => [...prev, response])

      // Update stage based on response (simulated logic)
      // In real implementation, this would come from the API
      if (currentStage === "trigger") {
        setCompletedStages((prev) => [...prev, "trigger"])
        setCurrentStage("context")
      } else if (currentStage === "context") {
        setCompletedStages((prev) => [...prev, "context"])
        setCurrentStage("options")
      } else if (currentStage === "options") {
        setCompletedStages((prev) => [...prev, "options"])
        setCurrentStage("decision")
      } else if (currentStage === "decision") {
        setCompletedStages((prev) => [...prev, "decision"])
        setCurrentStage("rationale")
      } else if (currentStage === "rationale") {
        setCompletedStages((prev) => [...prev, "rationale"])
        setShowCompleteDialog(true)
      }

      // Update suggested entities
      if (response.extracted_entities) {
        setSuggestedEntities((prev) => [
          ...prev,
          ...response.extracted_entities!.filter(
            (e) => !prev.some((p) => p.id === e.id)
          ),
        ])
      }
    },
  })

  // Complete session mutation
  const completeSessionMutation = useMutation({
    mutationFn: async () => {
      if (!activeSession) throw new Error("No active session")
      return api.completeCaptureSession(activeSession.id)
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["dashboard-stats"] })
      queryClient.invalidateQueries({ queryKey: ["decisions"] })
      setActiveSession(null)
      setMessages([])
      setCurrentStage("trigger")
      setCompletedStages([])
      setSuggestedEntities([])
      setShowCompleteDialog(false)
    },
  })

  const handleSendMessage = useCallback(
    async (content: string) => {
      // Add user message immediately
      const userMessage: CaptureMessage = {
        id: `user-${Date.now()}`,
        role: "user",
        content,
        timestamp: new Date().toISOString(),
      }
      setMessages((prev) => [...prev, userMessage])

      // Send to API
      await sendMessageMutation.mutateAsync(content)
    },
    [sendMessageMutation]
  )

  const handleLinkEntity = (entity: Entity) => {
    // In real implementation, this would call the API
    setSuggestedEntities((prev) => prev.filter((e) => e.id !== entity.id))
  }

  const handleAbandonSession = () => {
    setActiveSession(null)
    setMessages([])
    setCurrentStage("trigger")
    setCompletedStages([])
    setSuggestedEntities([])
  }

  return (
    <AppShell>
      <div className="h-full flex">
        {/* Main chat area */}
        <div className="flex-1 flex flex-col">
          {/* Header */}
          <div className="flex items-center justify-between px-6 py-4 border-b border-white/[0.06] bg-slate-900/80 backdrop-blur-xl">
            <div>
              <h1 className="text-2xl font-bold tracking-tight text-slate-100">
                Knowledge Capture
              </h1>
              <p className="text-sm text-slate-400">
                {activeSession
                  ? "Recording decision trace..."
                  : "Start a session to capture knowledge"}
              </p>
            </div>
            <div className="flex gap-2 items-center">
              <Button
                variant="ghost"
                size="sm"
                onClick={() => setShowSessionHistory(!showSessionHistory)}
                className="text-slate-400 hover:text-slate-200 hidden lg:flex"
              >
                {showSessionHistory ? (
                  <PanelRightClose className="h-4 w-4 mr-2" />
                ) : (
                  <PanelRightOpen className="h-4 w-4 mr-2" />
                )}
                Session History
              </Button>
              {activeSession ? (
                <>
                  <Button
                    variant="outline"
                    size="sm"
                    onClick={handleAbandonSession}
                    className="border-red-500/30 text-red-400 hover:bg-red-500/10 hover:text-red-300"
                  >
                    <X className="h-4 w-4 mr-2" />
                    Abandon
                  </Button>
                  <Button
                    size="sm"
                    onClick={() => setShowCompleteDialog(true)}
                    disabled={completedStages.length < 3}
                    className="bg-gradient-to-r from-green-500 to-emerald-400 text-slate-900 hover:shadow-[0_0_20px_rgba(34,197,94,0.3)] disabled:opacity-50"
                  >
                    Complete Session
                  </Button>
                </>
              ) : (
                <Button
                  onClick={() => startSessionMutation.mutate()}
                  disabled={startSessionMutation.isPending}
                  className="bg-gradient-to-r from-cyan-500 to-teal-400 text-slate-900 font-semibold shadow-[0_4px_16px_rgba(34,211,238,0.3)] hover:shadow-[0_6px_20px_rgba(34,211,238,0.4)] hover:scale-105 transition-all"
                >
                  <Plus className="h-4 w-4 mr-2" />
                  New Session
                </Button>
              )}
            </div>
          </div>

          {/* Decision trace indicator */}
          {activeSession && (
            <DecisionTraceIndicator
              currentStage={currentStage}
              completedStages={completedStages}
            />
          )}

          {/* Chat interface or empty state */}
          {activeSession ? (
            <ChatInterface
              messages={messages}
              onSendMessage={handleSendMessage}
              isLoading={sendMessageMutation.isPending}
              suggestedEntities={suggestedEntities}
              onLinkEntity={handleLinkEntity}
            />
          ) : (
            <div className="flex-1 flex items-center justify-center bg-slate-900/50">
              <div className="text-center max-w-lg mx-auto p-8 animate-in fade-in zoom-in-95 duration-500">
                {/* Decorative illustration */}
                <div className="relative mx-auto mb-6 w-32 h-32">
                  {/* Outer glow */}
                  <div className="absolute inset-0 rounded-full bg-cyan-500/10 animate-pulse" />
                  {/* Main circle */}
                  <div className="absolute inset-2 rounded-full bg-gradient-to-br from-slate-800 to-slate-900 border-2 border-cyan-500/20 flex items-center justify-center">
                    <MessageSquare className="h-12 w-12 text-cyan-400/70" aria-hidden="true" />
                  </div>
                  {/* Decorative elements */}
                  <div className="absolute -top-1 right-2 w-8 h-8 rounded-full bg-purple-500/20 border border-purple-400/30 flex items-center justify-center animate-bounce" style={{ animationDelay: '0.1s' }}>
                    <Lightbulb className="h-4 w-4 text-purple-400/70" />
                  </div>
                  <div className="absolute bottom-0 -left-1 w-6 h-6 rounded-full bg-green-500/20 border border-green-400/30 animate-bounce" style={{ animationDelay: '0.3s' }} />
                </div>

                <h3 className="text-xl font-semibold text-slate-100 mb-2">
                  AI-Guided Decision Capture
                </h3>
                <p className="text-slate-400 mb-6 leading-relaxed">
                  I&apos;ll walk you through documenting a decision step by step,
                  helping you capture the trigger, context, options considered, and rationale.
                </p>

                <div className="flex flex-col gap-3 w-full max-w-sm mx-auto">
                  {/* Project Selection */}
                  <div className="space-y-2">
                    <label htmlFor="project-selector" className="text-sm font-medium text-slate-300">
                      Project <span className="text-slate-500">(optional)</span>
                    </label>
                    <ProjectSelector
                      value={selectedProject}
                      onChange={setSelectedProject}
                      projects={projects}
                      placeholder="Select or create project..."
                    />
                    {selectedProject && (
                      <p className="text-xs text-slate-500">
                        Session will be tagged with project: <span className="text-cyan-400">{selectedProject}</span>
                      </p>
                    )}
                  </div>

                  {/* Start Button */}
                  <Button
                    onClick={() => startSessionMutation.mutate()}
                    disabled={startSessionMutation.isPending}
                    className="bg-gradient-to-r from-cyan-500 to-teal-400 text-slate-900 font-semibold shadow-[0_4px_16px_rgba(34,211,238,0.3)] hover:shadow-[0_6px_20px_rgba(34,211,238,0.4)] hover:scale-105 transition-all"
                  >
                    <Plus className="h-4 w-4 mr-2" aria-hidden="true" />
                    Start Interview Session
                    <ArrowRight className="h-4 w-4 ml-2" aria-hidden="true" />
                  </Button>
                </div>

                <p className="text-xs text-slate-500 mt-6">
                  Tip: Each session guides you through all stages of a decision trace
                </p>
              </div>
            </div>
          )}
        </div>

        {/* Sidebar with session history (slide-over, hidden by default) */}
        {showSessionHistory && (
          <div className="w-72 border-l bg-background hidden lg:block animate-in slide-in-from-right duration-200">
            <div className="p-4 border-b flex items-center justify-between">
              <div className="flex items-center gap-2">
                <History className="h-4 w-4" />
                <h2 className="font-medium">Recent Sessions</h2>
              </div>
              <Button variant="ghost" size="sm" onClick={() => setShowSessionHistory(false)} className="h-6 w-6 p-0">
                <X className="h-3.5 w-3.5" />
              </Button>
            </div>
            <ScrollArea className="h-[calc(100%-57px)]">
              <div className="p-4 space-y-2">
                <div className="text-center py-8">
                  <History className="h-8 w-8 text-slate-600 mx-auto mb-2" aria-hidden="true" />
                  <p className="text-sm text-slate-500">
                    No recent sessions
                  </p>
                  <p className="text-xs text-slate-600 mt-1">
                    Your session history will appear here
                  </p>
                </div>
              </div>
            </ScrollArea>
          </div>
        )}

        {/* Complete session dialog */}
        <Dialog open={showCompleteDialog} onOpenChange={setShowCompleteDialog}>
          <DialogContent>
            <DialogHeader>
              <DialogTitle>Complete Capture Session</DialogTitle>
              <DialogDescription>
                This will save the decision trace to your knowledge graph.
              </DialogDescription>
            </DialogHeader>
            <div className="py-4">
              <h4 className="text-sm font-medium mb-2">Captured Stages:</h4>
              <div className="flex flex-wrap gap-2">
                {completedStages.map((stage) => (
                  <Badge key={stage} variant="secondary">
                    {stage}
                  </Badge>
                ))}
              </div>
              {suggestedEntities.length > 0 && (
                <>
                  <h4 className="text-sm font-medium mt-4 mb-2">
                    Linked Entities:
                  </h4>
                  <div className="flex flex-wrap gap-2">
                    {suggestedEntities.map((entity) => (
                      <Badge key={entity.id} variant="outline">
                        {entity.name}
                      </Badge>
                    ))}
                  </div>
                </>
              )}
            </div>
            <DialogFooter>
              <Button
                variant="outline"
                onClick={() => setShowCompleteDialog(false)}
              >
                Continue Editing
              </Button>
              <Button
                onClick={() => completeSessionMutation.mutate()}
                disabled={completeSessionMutation.isPending}
              >
                Save Decision
              </Button>
            </DialogFooter>
          </DialogContent>
        </Dialog>
      </div>
    </AppShell>
  )
}
