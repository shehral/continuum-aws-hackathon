"use client"

import { useQuery } from "@tanstack/react-query"
import Link from "next/link"
import { useEffect, useState, useCallback } from "react"

import { AppShell } from "@/components/layout/app-shell"
import { AnalyticsCharts } from "@/components/dashboard/analytics-charts"
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from "@/components/ui/card"
import { Badge } from "@/components/ui/badge"
import { Button } from "@/components/ui/button"
import { Tooltip, TooltipContent, TooltipProvider, TooltipTrigger } from "@/components/ui/tooltip"
import { ErrorState } from "@/components/ui/error-state"
import { StatCardSkeleton, DecisionCardSkeleton } from "@/components/ui/skeleton"
import { api, type DashboardStats, type Decision } from "@/lib/api"
import { getEntityStyle } from "@/lib/constants"
import {
  FileText,
  Network,
  MessageSquare,
  GitBranch,
  ArrowRight,
  Plus,
  Sparkles,
  Lightbulb,
  TrendingUp,
  ShieldCheck,
  AlertTriangle,
  AlertCircle,
  Info,
  CheckCircle2,
  ClipboardCheck,
} from "lucide-react"

// Animated number counter for stats
function AnimatedNumber({ value, duration = 1000 }: { value: number; duration?: number }) {
  const [displayValue, setDisplayValue] = useState(0)

  useEffect(() => {
    if (value === 0) {
      setDisplayValue(0)
      return
    }

    const startTime = Date.now()
    const startValue = 0

    const animate = () => {
      const elapsed = Date.now() - startTime
      const progress = Math.min(elapsed / duration, 1)
      // Ease out cubic
      const easeOut = 1 - Math.pow(1 - progress, 3)
      setDisplayValue(Math.floor(startValue + (value - startValue) * easeOut))

      if (progress < 1) {
        requestAnimationFrame(animate)
      }
    }

    requestAnimationFrame(animate)
  }, [value, duration])

  return <>{displayValue}</>
}

const STAT_ICONS = {
  decisions: FileText,
  entities: Network,
  sessions: MessageSquare,
  connections: GitBranch,
}

function StatCard({
  title,
  value,
  description,
  iconType,
  href,
  emptyAction,
  delay = 0,
}: {
  title: string
  value: number | string
  description: string
  iconType: keyof typeof STAT_ICONS
  href?: string
  emptyAction?: { label: string; href: string }
  delay?: number
}) {
  const isEmpty = value === 0 || value === "0"
  const numericValue = typeof value === "number" ? value : parseInt(value) || 0
  const Icon = STAT_ICONS[iconType]

  const content = (
    <Card
      variant="glass"
      className={`animate-in fade-in slide-in-from-bottom-4 ${href ? 'cursor-pointer' : ''}`}
      style={{ animationDelay: `${delay}ms`, animationFillMode: 'backwards' }}
      tabIndex={href ? 0 : undefined}
      role={href ? "link" : undefined}
    >
      <CardHeader className="flex flex-row items-center justify-between pb-2">
        <div className="flex items-center gap-3">
          <div className="w-10 h-10 rounded-xl bg-gradient-to-br from-violet-500/20 to-fuchsia-500/10 border border-violet-500/20 flex items-center justify-center">
            <Icon className="h-5 w-5 text-violet-400" />
          </div>
          <CardTitle className="text-sm font-medium text-slate-400">{title}</CardTitle>
        </div>
      </CardHeader>
      <CardContent>
        <div className={`text-4xl font-bold bg-gradient-to-r ${isEmpty ? 'from-slate-500 to-slate-400' : 'from-violet-400 via-fuchsia-400 to-rose-400'} bg-clip-text text-transparent`}>
          {typeof value === "number" ? <AnimatedNumber value={numericValue} /> : value}
        </div>
        <p className="text-xs text-slate-500 mt-1">{description}</p>
        {isEmpty && emptyAction && (
          <Link
            href={emptyAction.href}
            className="text-xs text-violet-400 hover:text-violet-300 mt-2 inline-flex items-center gap-1 transition-colors group"
          >
            {emptyAction.label}
            <ArrowRight className="h-3 w-3 group-hover:translate-x-1 transition-transform" />
          </Link>
        )}
      </CardContent>
    </Card>
  )

  return href && !isEmpty ? <Link href={href}>{content}</Link> : content
}

function DecisionCard({ decision, index = 0 }: { decision: Decision; index?: number }) {
  const handleKeyDown = useCallback((e: React.KeyboardEvent) => {
    if (e.key === "Enter" || e.key === " ") {
      e.preventDefault()
      window.location.href = `/decisions?id=${decision.id}`
    }
  }, [decision.id])

  return (
    <Link href={`/decisions?id=${decision.id}`}>
      <Card
        variant="glass"
        className="h-full cursor-pointer group animate-in fade-in slide-in-from-bottom-4"
        style={{ animationDelay: `${400 + index * 100}ms`, animationFillMode: 'backwards' }}
        tabIndex={0}
        role="article"
        aria-label={`Decision: ${decision.trigger}`}
        onKeyDown={handleKeyDown}
      >
        <CardHeader className="pb-2">
          <div className="flex items-start justify-between gap-2">
            <CardTitle className="text-base text-slate-200 group-hover:text-violet-300 transition-colors leading-tight">
              {decision.trigger}
            </CardTitle>
            <Badge className="ml-2 shrink-0 bg-violet-500/20 text-violet-300 border-violet-500/30 group-hover:bg-violet-500/30 transition-colors">
              {Math.round(decision.confidence * 100)}%
            </Badge>
          </div>
          <TooltipProvider>
            <Tooltip>
              <TooltipTrigger asChild>
                <CardDescription className="line-clamp-2 text-slate-400 mt-1 cursor-help">
                  {decision.agent_decision}
                </CardDescription>
              </TooltipTrigger>
              <TooltipContent side="bottom" className="max-w-lg bg-slate-800 border-white/10">
                <p>{decision.agent_decision}</p>
              </TooltipContent>
            </Tooltip>
          </TooltipProvider>
        </CardHeader>
        <CardContent>
          <div className="flex flex-wrap gap-1.5" role="list" aria-label="Related entities">
            {decision.entities.slice(0, 3).map((entity) => {
              const style = getEntityStyle(entity.type)
              return (
                <Badge
                  key={entity.id}
                  variant="outline"
                  className={`text-xs ${style.bg} ${style.text} ${style.border} transition-all hover:scale-105`}
                  role="listitem"
                >
                  {style.icon} {entity.name}
                </Badge>
              )
            })}
            {decision.entities.length > 3 && (
              <Badge variant="outline" className="text-xs text-slate-400 border-slate-600 bg-slate-500/10">
                +{decision.entities.length - 3} more
              </Badge>
            )}
          </div>
        </CardContent>
      </Card>
    </Link>
  )
}

export default function DashboardPage() {
  const { data: stats, isLoading, error, refetch } = useQuery({
    queryKey: ["dashboard-stats"],
    queryFn: () => api.getDashboardStats(),
    staleTime: 60 * 1000, // 1 minute
  })

  const { data: graphStats } = useQuery({
    queryKey: ["graph-stats"],
    queryFn: () => api.getGraphStats(),
    staleTime: 60 * 1000,
  })

  const { data: validation } = useQuery({
    queryKey: ["graph-validation"],
    queryFn: () => api.getGraphValidation(),
    staleTime: 5 * 60 * 1000, // 5 minutes — validation is expensive
  })

  // Fallback data for when API is not available
  const displayStats: DashboardStats = stats || {
    total_decisions: 0,
    total_entities: 0,
    total_sessions: 0,
    needs_review: 0,
    recent_decisions: [],
  }

  return (
    <AppShell>
      <div className="p-6 space-y-6">
        {/* Header */}
        <div className="flex items-center justify-between animate-in fade-in slide-in-from-top-4 duration-500">
          <div>
            <h1 className="text-3xl font-bold tracking-tight gradient-text">
              Welcome back
            </h1>
            <p className="text-slate-400 flex items-center gap-2 mt-1">
              <Sparkles className="h-4 w-4 text-violet-400" />
              Your knowledge graph at a glance
            </p>
          </div>
          <div className="flex gap-3">
            <Button
              variant="outline"
              asChild
            >
              <Link href="/graph" className="flex items-center gap-2">
                <Network className="h-4 w-4" />
                View Graph
              </Link>
            </Button>
            <Button
              variant="gradient"
              asChild
            >
              <Link href="/add" className="flex items-center gap-2">
                <Plus className="h-4 w-4" />
                Add Knowledge
              </Link>
            </Button>
          </div>
        </div>

        {/* Stats Grid */}
        {error ? (
          <ErrorState
            title="Failed to load dashboard"
            message="We couldn't load your dashboard statistics. Please try again."
            error={error instanceof Error ? error : null}
            retry={() => refetch()}
          />
        ) : isLoading ? (
          <div className="grid gap-4 md:grid-cols-2 lg:grid-cols-4" aria-live="polite" aria-busy="true">
            <StatCardSkeleton />
            <StatCardSkeleton />
            <StatCardSkeleton />
            <StatCardSkeleton />
            <span className="sr-only">Loading dashboard statistics...</span>
          </div>
        ) : (
          <div className="grid gap-4 md:grid-cols-2 lg:grid-cols-4">
            <StatCard
              title="Total Decisions"
              value={displayStats.total_decisions}
              description="Decision traces captured"
              iconType="decisions"
              href="/decisions"
              emptyAction={{ label: "Import from Claude logs", href: "/add" }}
              delay={0}
            />
            <StatCard
              title="Entities"
              value={displayStats.total_entities}
              description="Concepts, systems, patterns"
              iconType="entities"
              href="/graph"
              emptyAction={{ label: "Add knowledge", href: "/add" }}
              delay={100}
            />
            <StatCard
              title="Capture Sessions"
              value={displayStats.total_sessions}
              description="AI-guided interviews"
              iconType="sessions"
              href="/capture"
              emptyAction={{ label: "Start an interview", href: "/capture" }}
              delay={200}
            />
            <StatCard
              title="Graph Connections"
              value={graphStats?.relationships ?? 0}
              description="Relationships mapped"
              iconType="connections"
              href="/graph"
              delay={300}
            />
          </div>
        )}

        {/* Needs Review Nudge */}
        {!isLoading && !error && displayStats.needs_review > 0 && (
          <Link href="/decisions/review">
            <Card
              variant="glass"
              className="cursor-pointer group border-amber-500/20 hover:border-amber-500/40 transition-colors animate-in fade-in slide-in-from-bottom-4 duration-500"
              style={{ animationDelay: "350ms", animationFillMode: "backwards" }}
            >
              <CardContent className="flex items-center gap-4 py-4">
                <div className="w-10 h-10 rounded-xl bg-gradient-to-br from-amber-500/20 to-orange-500/10 border border-amber-500/20 flex items-center justify-center shrink-0">
                  <ClipboardCheck className="h-5 w-5 text-amber-400" />
                </div>
                <div className="flex-1 min-w-0">
                  <p className="text-sm font-medium text-amber-300">
                    {displayStats.needs_review} decision{displayStats.needs_review !== 1 ? "s" : ""} awaiting your review
                  </p>
                  <p className="text-xs text-slate-400 mt-0.5">
                    Add your rationale to confirm or override agent decisions
                  </p>
                </div>
                <ArrowRight className="h-4 w-4 text-amber-400 group-hover:translate-x-1 transition-transform shrink-0" />
              </CardContent>
            </Card>
          </Link>
        )}

        {/* Analytics Charts */}
        {!isLoading && !error && displayStats.recent_decisions.length > 0 && (
          <div className="animate-in fade-in slide-in-from-bottom-4 duration-500" style={{ animationDelay: "400ms" }}>
            <h2 className="text-xl font-semibold text-slate-100 mb-4 flex items-center gap-2">
              <TrendingUp className="h-5 w-5 text-violet-400" />
              Analytics
            </h2>
            <AnalyticsCharts decisions={displayStats.recent_decisions} />
          </div>
        )}

        {/* Graph Health */}
        {validation && validation.total_issues > 0 && (
          <div className="animate-in fade-in slide-in-from-bottom-4 duration-500" style={{ animationDelay: "500ms" }}>
            <h2 className="text-xl font-semibold text-slate-100 mb-4 flex items-center gap-2">
              <ShieldCheck className="h-5 w-5 text-emerald-400" />
              Graph Health
            </h2>
            <Card variant="glass">
              <CardContent className="pt-6">
                <div className="flex items-center gap-6 mb-4">
                  {(validation.by_severity.error ?? 0) > 0 && (
                    <div className="flex items-center gap-2">
                      <AlertCircle className="h-4 w-4 text-red-400" aria-hidden="true" />
                      <span className="text-sm font-medium text-red-400">{validation.by_severity.error} errors</span>
                    </div>
                  )}
                  {(validation.by_severity.warning ?? 0) > 0 && (
                    <div className="flex items-center gap-2">
                      <AlertTriangle className="h-4 w-4 text-amber-400" aria-hidden="true" />
                      <span className="text-sm font-medium text-amber-400">{validation.by_severity.warning} warnings</span>
                    </div>
                  )}
                  {(validation.by_severity.info ?? 0) > 0 && (
                    <div className="flex items-center gap-2">
                      <Info className="h-4 w-4 text-sky-400" aria-hidden="true" />
                      <span className="text-sm font-medium text-sky-400">{validation.by_severity.info} info</span>
                    </div>
                  )}
                  {validation.total_issues === 0 && (
                    <div className="flex items-center gap-2">
                      <CheckCircle2 className="h-4 w-4 text-emerald-400" aria-hidden="true" />
                      <span className="text-sm font-medium text-emerald-400">No issues found</span>
                    </div>
                  )}
                </div>
                <div className="flex flex-wrap gap-2">
                  {Object.entries(validation.by_type).map(([type, count]) => (
                    <Badge
                      key={type}
                      className="bg-white/[0.04] text-slate-300 border-white/[0.08]"
                    >
                      {type.replace(/_/g, " ")}: {count}
                    </Badge>
                  ))}
                </div>
                <div className="mt-4">
                  <Button variant="ghost" size="sm" asChild className="text-violet-400 hover:text-violet-300 hover:bg-violet-500/10">
                    <Link href="/graph" className="flex items-center gap-1">
                      View in Graph
                      <ArrowRight className="h-4 w-4" />
                    </Link>
                  </Button>
                </div>
              </CardContent>
            </Card>
          </div>
        )}

        {/* Recent Decisions */}
        <Card variant="glass">
          <CardHeader>
            <div className="flex items-center justify-between">
              <CardTitle className="text-xl text-slate-100 flex items-center gap-2">
                <Lightbulb className="h-5 w-5 text-violet-400" />
                Recent Decisions
              </CardTitle>
              <Button
                variant="ghost"
                size="sm"
                asChild
                className="text-violet-400 hover:text-violet-300 hover:bg-violet-500/10"
              >
                <Link href="/decisions" className="flex items-center gap-1">
                  View all
                  <ArrowRight className="h-4 w-4" />
                </Link>
              </Button>
            </div>
          </CardHeader>
          <CardContent>
            {isLoading ? (
              <div className="grid gap-4 md:grid-cols-2 lg:grid-cols-3" aria-live="polite" aria-busy="true">
                <DecisionCardSkeleton />
                <DecisionCardSkeleton />
                <DecisionCardSkeleton />
                <span className="sr-only">Loading recent decisions...</span>
              </div>
            ) : displayStats.recent_decisions.length === 0 ? (
              <div className="py-12 text-center">
                <div className="mx-auto mb-4 h-16 w-16 rounded-2xl bg-gradient-to-br from-violet-500/20 to-fuchsia-500/10 border border-violet-500/20 flex items-center justify-center">
                  <Lightbulb className="h-8 w-8 text-violet-400" />
                </div>
                <h3 className="text-lg font-medium mb-1 text-slate-200">No decisions yet</h3>
                <p className="text-slate-400 mb-6 max-w-md mx-auto">
                  Start capturing knowledge from your Claude Code sessions or through guided interviews.
                </p>
                <Button variant="gradient" asChild>
                  <Link href="/add" className="flex items-center gap-2">
                    <Plus className="h-4 w-4" />
                    Add Knowledge
                  </Link>
                </Button>
              </div>
            ) : (
              <div className="grid gap-4 md:grid-cols-2 lg:grid-cols-3" role="feed" aria-label="Recent decisions">
                {displayStats.recent_decisions.map((decision, index) => (
                  <DecisionCard key={decision.id} decision={decision} index={index} />
                ))}
              </div>
            )}
          </CardContent>
        </Card>
      </div>
    </AppShell>
  )
}
