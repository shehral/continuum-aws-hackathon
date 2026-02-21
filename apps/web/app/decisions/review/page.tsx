"use client"

import { useState, useCallback, useEffect, useRef } from "react"
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query"
import Link from "next/link"
import { useRouter } from "next/navigation"
import {
  Bot,
  UserCircle,
  ChevronLeft,
  ChevronRight,
  Check,
  Loader2,
  ArrowLeft,
  Sparkles,
  MessageSquarePlus,
} from "lucide-react"

import { AppShell } from "@/components/layout/app-shell"
import { Card, CardContent } from "@/components/ui/card"
import { Badge } from "@/components/ui/badge"
import { Button } from "@/components/ui/button"
import { api, type Decision } from "@/lib/api"
import { getEntityStyle } from "@/lib/constants"

export default function ReviewQueuePage() {
  const router = useRouter()
  const queryClient = useQueryClient()
  const [currentIndex, setCurrentIndex] = useState(0)
  const [mode, setMode] = useState<"agree" | "disagree" | null>(null)
  const [humanDecision, setHumanDecision] = useState("")
  const [humanRationale, setHumanRationale] = useState("")
  const rationaleRef = useRef<HTMLTextAreaElement>(null)
  const initialTotalRef = useRef<number | null>(null)

  const { data, isLoading, error } = useQuery({
    queryKey: ["decisions-needs-review"],
    queryFn: () => api.getDecisionsNeedingReview(50, 0),
    staleTime: 30 * 1000,
  })

  const decisions = data?.decisions ?? []
  const totalNeedsReview = data?.total_needs_review ?? 0
  const currentDecision = decisions[currentIndex] as Decision | undefined

  // Capture initial total on first load so progress bar reflects session progress
  if (initialTotalRef.current === null && totalNeedsReview > 0) {
    initialTotalRef.current = totalNeedsReview
  }
  const sessionTotal = initialTotalRef.current ?? totalNeedsReview

  const updateMutation = useMutation({
    mutationFn: ({ id, data }: { id: string; data: Parameters<typeof api.updateDecision>[1] }) =>
      api.updateDecision(id, data),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["decisions-needs-review"] })
      queryClient.invalidateQueries({ queryKey: ["decisions"] })
      queryClient.invalidateQueries({ queryKey: ["dashboard-stats"] })
    },
  })

  // Reset form when navigating to a new decision
  useEffect(() => {
    setMode(null)
    setHumanDecision("")
    setHumanRationale("")
  }, [currentIndex])

  // Auto-focus rationale textarea when mode is selected
  useEffect(() => {
    if (mode && rationaleRef.current) {
      rationaleRef.current.focus()
    }
  }, [mode])

  const handleSaveAndNext = useCallback(async () => {
    if (!currentDecision || !humanRationale.trim()) return

    const payload: Parameters<typeof api.updateDecision>[1] = {
      human_rationale: humanRationale.trim(),
    }
    if (mode === "disagree" && humanDecision.trim()) {
      payload.human_decision = humanDecision.trim()
    }

    await updateMutation.mutateAsync({ id: currentDecision.id, data: payload })

    // Advance to next or stay at same index (list shifts when this one leaves the queue)
    if (currentIndex >= decisions.length - 1) {
      // Was last item — stay at same index (or go back if needed)
      setCurrentIndex(Math.max(0, decisions.length - 2))
    }
    // Otherwise index stays, and the refetched list will have a new item at this position
  }, [currentDecision, humanRationale, humanDecision, mode, updateMutation, currentIndex, decisions.length])

  const handlePrev = useCallback(() => {
    setCurrentIndex((i) => Math.max(0, i - 1))
  }, [])

  const handleNext = useCallback(() => {
    setCurrentIndex((i) => Math.min(decisions.length - 1, i + 1))
  }, [decisions.length])

  // Keyboard shortcuts
  useEffect(() => {
    const handler = (e: KeyboardEvent) => {
      // Don't capture when typing in inputs
      if (e.target instanceof HTMLTextAreaElement || e.target instanceof HTMLInputElement) {
        if (e.key === "Enter" && (e.metaKey || e.ctrlKey)) {
          e.preventDefault()
          handleSaveAndNext()
        }
        return
      }

      if (e.key === "ArrowLeft") handlePrev()
      if (e.key === "ArrowRight") handleNext()
      if (e.key === "Enter") handleSaveAndNext()
    }

    window.addEventListener("keydown", handler)
    return () => window.removeEventListener("keydown", handler)
  }, [handlePrev, handleNext, handleSaveAndNext])

  const progressPercent = sessionTotal > 0
    ? Math.round(((sessionTotal - decisions.length) / sessionTotal) * 100)
    : 100

  return (
    <AppShell>
      <div className="h-full flex flex-col">
        {/* Header */}
        <div className="px-6 py-4 border-b border-border bg-background/80 backdrop-blur-xl">
          <div className="flex items-center justify-between">
            <div className="flex items-center gap-3">
              <Button variant="ghost" size="icon" asChild className="text-muted-foreground hover:text-foreground">
                <Link href="/decisions">
                  <ArrowLeft className="h-4 w-4" />
                </Link>
              </Button>
              <div>
                <h1 className="text-xl font-bold tracking-tight text-foreground">Review Queue</h1>
                <p className="text-sm text-muted-foreground">
                  {decisions.length > 0
                    ? `${currentIndex + 1} of ${decisions.length} decisions to review`
                    : "All caught up!"}
                </p>
              </div>
            </div>

            {/* Progress bar */}
            {totalNeedsReview > 0 && (
              <div className="flex items-center gap-3">
                <span className="text-xs text-muted-foreground">{progressPercent}% reviewed</span>
                <div className="w-32 h-2 rounded-full bg-muted overflow-hidden">
                  <div
                    className="h-full rounded-full bg-gradient-to-r from-emerald-500 to-teal-400 transition-all duration-500"
                    style={{ width: `${progressPercent}%` }}
                  />
                </div>
              </div>
            )}
          </div>
        </div>

        {/* Content */}
        <div className="flex-1 overflow-auto p-6">
          {isLoading ? (
            <div className="flex items-center justify-center h-64">
              <Loader2 className="h-8 w-8 animate-spin text-violet-400" />
            </div>
          ) : error ? (
            <div className="text-center py-16">
              <p className="text-destructive">Failed to load review queue</p>
              <Button variant="ghost" className="mt-4 text-muted-foreground" onClick={() => router.refresh()}>
                Try again
              </Button>
            </div>
          ) : decisions.length === 0 ? (
            <div className="text-center py-16 animate-in fade-in duration-500">
              <div className="mx-auto mb-4 h-20 w-20 rounded-2xl bg-emerald-500/10 flex items-center justify-center">
                <Sparkles className="h-10 w-10 text-emerald-400/50" aria-hidden="true" />
              </div>
              <h2 className="text-xl font-medium text-foreground mb-2">All caught up!</h2>
              <p className="text-muted-foreground mb-6">Every decision has been reviewed. Nice work.</p>
              <Button variant="outline" asChild>
                <Link href="/decisions">Back to Decisions</Link>
              </Button>
            </div>
          ) : currentDecision ? (
            <div className="max-w-3xl mx-auto space-y-6 animate-in fade-in duration-300">
              {/* Decision Card */}
              <Card variant="glass">
                <CardContent className="pt-6 space-y-5">
                  {/* Trigger */}
                  <h2 className="text-xl font-semibold text-foreground">{currentDecision.trigger}</h2>

                  {/* Context */}
                  <div className="p-3 rounded-lg bg-muted/50 border border-border">
                    <span className="text-xs text-muted-foreground uppercase tracking-wider">Context</span>
                    <p className="text-sm text-muted-foreground leading-relaxed mt-1">{currentDecision.context}</p>
                  </div>

                  {/* Options */}
                  {currentDecision.options.length > 0 && (
                    <div className="p-3 rounded-lg bg-muted/50 border border-border">
                      <span className="text-xs text-muted-foreground uppercase tracking-wider">Options Considered</span>
                      <ul className="mt-2 space-y-1">
                        {currentDecision.options.map((option, i) => (
                          <li key={i} className="text-sm text-muted-foreground flex items-start gap-2">
                            <span className="text-muted-foreground font-mono">{i + 1}.</span>
                            {option}
                          </li>
                        ))}
                      </ul>
                    </div>
                  )}

                  {/* Agent's Choice */}
                  <div className="p-4 rounded-lg bg-gradient-to-r from-violet-500/10 to-purple-500/10 border border-violet-500/20">
                    <h4 className="text-sm font-medium text-violet-400 mb-3 flex items-center gap-2">
                      <Bot className="h-4 w-4" aria-hidden="true" />
                      Agent&apos;s Choice
                    </h4>
                    <div className="space-y-2">
                      <div>
                        <span className="text-xs text-muted-foreground uppercase tracking-wider">Decision</span>
                        <p className="text-sm font-medium text-foreground mt-0.5">{currentDecision.agent_decision}</p>
                      </div>
                      <div>
                        <span className="text-xs text-muted-foreground uppercase tracking-wider">Rationale</span>
                        <p className="text-sm text-muted-foreground leading-relaxed mt-0.5">{currentDecision.agent_rationale}</p>
                      </div>
                      <div className="flex items-center gap-2 pt-1">
                        <Badge className="text-[10px] px-1.5 py-0 bg-violet-500/20 text-violet-300 border-violet-500/30">
                          {Math.round(currentDecision.confidence * 100)}% confidence
                        </Badge>
                        {currentDecision.source && currentDecision.source !== "unknown" && (
                          <Badge className="text-[10px] px-1.5 py-0 bg-muted text-muted-foreground border-border">
                            {currentDecision.source === "claude_logs" ? "claude-log" : currentDecision.source}
                          </Badge>
                        )}
                      </div>
                    </div>
                  </div>

                  {/* Entity badges */}
                  {currentDecision.entities.length > 0 && (
                    <div className="flex flex-wrap gap-1.5">
                      {currentDecision.entities.map((entity) => {
                        const style = getEntityStyle(entity.type)
                        return (
                          <Badge
                            key={entity.id}
                            className={`text-xs ${style.bg} ${style.text} ${style.border}`}
                          >
                            <style.lucideIcon className="h-3 w-3 mr-1" aria-hidden="true" />
                            {entity.name}
                          </Badge>
                        )
                      })}
                    </div>
                  )}
                </CardContent>
              </Card>

              {/* Your Review */}
              <Card variant="glass" className="border-amber-500/20">
                <CardContent className="pt-6 space-y-4">
                  <h4 className="text-sm font-medium text-amber-400 flex items-center gap-2">
                    <UserCircle className="h-4 w-4" aria-hidden="true" />
                    Your Review
                  </h4>

                  {/* Agree / Disagree toggle */}
                  <div className="flex gap-2" role="group" aria-label="Review decision">
                    <Button
                      variant={mode === "agree" ? "default" : "outline"}
                      size="sm"
                      onClick={() => setMode("agree")}
                      className={
                        mode === "agree"
                          ? "bg-emerald-500/20 text-emerald-300 border-emerald-500/30 hover:bg-emerald-500/30"
                          : "border-border text-muted-foreground hover:text-foreground"
                      }
                    >
                      <Check className="h-4 w-4 mr-1" aria-hidden="true" />
                      Agree
                    </Button>
                    <Button
                      variant={mode === "disagree" ? "default" : "outline"}
                      size="sm"
                      onClick={() => setMode("disagree")}
                      className={
                        mode === "disagree"
                          ? "bg-violet-500/20 text-violet-300 border-violet-500/30 hover:bg-violet-500/30"
                          : "border-border text-muted-foreground hover:text-foreground"
                      }
                    >
                      <MessageSquarePlus className="h-4 w-4 mr-1" aria-hidden="true" />
                      Override
                    </Button>
                  </div>

                  {/* Override decision field (only when disagreeing) */}
                  {mode === "disagree" && (
                    <div className="animate-in fade-in slide-in-from-top-2 duration-200">
                      <label className="text-xs text-muted-foreground uppercase tracking-wider" htmlFor="human-decision">
                        Your Decision
                      </label>
                      <input
                        id="human-decision"
                        type="text"
                        value={humanDecision}
                        onChange={(e) => setHumanDecision(e.target.value)}
                        placeholder="What would you choose instead?"
                        className="mt-1 w-full rounded-md border bg-muted/50 border-border text-foreground placeholder:text-muted-foreground px-3 py-2 text-sm focus:border-primary/50 focus:ring-1 focus:ring-primary/20 focus:outline-none"
                      />
                    </div>
                  )}

                  {/* Rationale (always visible once mode selected) */}
                  {mode && (
                    <div className="animate-in fade-in slide-in-from-top-2 duration-200">
                      <label className="text-xs text-muted-foreground uppercase tracking-wider" htmlFor="human-rationale">
                        Your Rationale
                      </label>
                      <textarea
                        id="human-rationale"
                        ref={rationaleRef}
                        value={humanRationale}
                        onChange={(e) => setHumanRationale(e.target.value)}
                        placeholder={mode === "agree"
                          ? "Why do you agree? (e.g., 'Confirmed after testing...')"
                          : "Why would you choose differently?"
                        }
                        className="mt-1 w-full min-h-[80px] rounded-md border bg-muted/50 border-border text-foreground placeholder:text-muted-foreground px-3 py-2 text-sm focus:border-primary/50 focus:ring-1 focus:ring-primary/20 focus:outline-none resize-y"
                      />
                      <p className="text-[10px] text-muted-foreground/60 mt-1">Ctrl+Enter to save and advance</p>
                    </div>
                  )}

                  {/* Save & Next */}
                  <div className="flex items-center justify-between pt-2">
                    <div className="flex items-center gap-2">
                      <Button
                        variant="ghost"
                        size="sm"
                        onClick={handlePrev}
                        disabled={currentIndex === 0}
                        className="text-muted-foreground hover:text-foreground"
                      >
                        <ChevronLeft className="h-4 w-4 mr-1" />
                        Prev
                      </Button>
                      <Button
                        variant="ghost"
                        size="sm"
                        onClick={handleNext}
                        disabled={currentIndex >= decisions.length - 1}
                        className="text-muted-foreground hover:text-foreground"
                      >
                        Next
                        <ChevronRight className="h-4 w-4 ml-1" />
                      </Button>
                    </div>
                    <Button
                      onClick={handleSaveAndNext}
                      disabled={!mode || !humanRationale.trim() || updateMutation.isPending}
                      className="bg-gradient-to-r from-emerald-500 to-teal-400 text-slate-900 font-semibold hover:shadow-[0_0_20px_rgba(52,211,153,0.3)] disabled:opacity-50"
                    >
                      {updateMutation.isPending ? (
                        <>
                          <Loader2 className="h-4 w-4 mr-2 animate-spin" aria-hidden="true" />
                          Saving...
                        </>
                      ) : (
                        <>
                          <Check className="h-4 w-4 mr-2" aria-hidden="true" />
                          Save &amp; Next
                        </>
                      )}
                    </Button>
                  </div>
                </CardContent>
              </Card>

              {/* Keyboard hint */}
              <div className="flex justify-center gap-4 text-[10px] text-muted-foreground/50">
                <span>← → navigate</span>
                <span>Enter save &amp; next</span>
              </div>
            </div>
          ) : null}
        </div>
      </div>
    </AppShell>
  )
}
