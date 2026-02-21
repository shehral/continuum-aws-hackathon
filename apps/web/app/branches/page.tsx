"use client"

import { useState } from "react"
import { useQuery } from "@tanstack/react-query"
import Link from "next/link"
import {
  ArrowLeft,
  GitBranch,
  Clock,
  AlertTriangle,
  ChevronRight,
  ChevronDown,
  Lightbulb,
  XCircle,
  HelpCircle,
  PauseCircle,
  RefreshCw,
} from "lucide-react"

import { AppShell } from "@/components/layout/app-shell"
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card"
import { Badge } from "@/components/ui/badge"
import { Button } from "@/components/ui/button"
import { ErrorState } from "@/components/ui/error-state"
import { Skeleton } from "@/components/ui/skeleton"
import { api, type DormantAlternative } from "@/lib/api"

// --------------------------------------------------------------------------
// Reconsider score → colour
// --------------------------------------------------------------------------

function scoreColor(score: number): string {
  if (score >= 0.7) return "text-rose-400"
  if (score >= 0.4) return "text-amber-400"
  return "text-slate-400"
}

function scoreBg(score: number): string {
  if (score >= 0.7) return "bg-rose-500/10 border-rose-500/30"
  if (score >= 0.4) return "bg-amber-500/10 border-amber-500/30"
  return "bg-white/[0.03] border-white/[0.06]"
}

// --------------------------------------------------------------------------
// Status icon
// --------------------------------------------------------------------------

function StatusIcon({ status }: { status: "rejected" | "unexplored" | "deferred" | string }) {
  if (status === "rejected") return <XCircle className="h-4 w-4 text-rose-400 shrink-0" />
  if (status === "unexplored") return <HelpCircle className="h-4 w-4 text-amber-400 shrink-0" />
  return <PauseCircle className="h-4 w-4 text-slate-400 shrink-0" />
}

// --------------------------------------------------------------------------
// Branch card
// --------------------------------------------------------------------------

interface BranchCardProps {
  alt: DormantAlternative
  expanded: boolean
  onToggle: () => void
}

function BranchCard({ alt, expanded, onToggle }: BranchCardProps) {
  const daysLabel =
    alt.days_dormant >= 365
      ? `${Math.round(alt.days_dormant / 365)}y dormant`
      : `${alt.days_dormant}d dormant`

  return (
    <div className={`rounded-xl border transition-all duration-200 ${scoreBg(alt.reconsider_score)}`}>
      {/* Header row */}
      <button
        onClick={onToggle}
        className="w-full flex items-start gap-3 p-4 text-left group"
      >
        {/* Dashed branch line indicator */}
        <div className="flex flex-col items-center gap-1 pt-0.5 shrink-0">
          <GitBranch className="h-4 w-4 text-fuchsia-400" />
          <div className="flex-1 w-px border-l-2 border-dashed border-fuchsia-400/30 min-h-[16px]" />
        </div>

        <div className="flex-1 min-w-0">
          <p className="text-sm font-medium text-slate-200 group-hover:text-violet-300 transition-colors line-clamp-2">
            {alt.text}
          </p>
          <p className="text-xs text-slate-500 mt-0.5 truncate">
            Rejected when: <span className="text-slate-400">{alt.rejected_by_trigger}</span>
          </p>
        </div>

        <div className="flex items-center gap-2 shrink-0">
          <Badge
            className={`text-[10px] px-2 py-0 font-mono ${scoreColor(alt.reconsider_score)} bg-transparent border border-current/30`}
          >
            {Math.round(alt.reconsider_score * 100)}% reconsidering
          </Badge>
          <Badge className="text-[10px] px-2 py-0 bg-slate-500/15 text-slate-400 gap-1">
            <Clock className="h-2.5 w-2.5" />
            {daysLabel}
          </Badge>
          {expanded ? (
            <ChevronDown className="h-4 w-4 text-slate-400" />
          ) : (
            <ChevronRight className="h-4 w-4 text-slate-400" />
          )}
        </div>
      </button>

      {/* Expanded detail */}
      {expanded && (
        <div className="px-4 pb-4 ml-7 space-y-3 border-t border-white/[0.04] pt-3">
          <div className="space-y-1">
            <p className="text-[11px] uppercase tracking-wider text-slate-500 font-semibold">
              What was chosen instead
            </p>
            <p className="text-sm text-slate-300">{alt.original_decision}</p>
          </div>

          {alt.rejected_at && (
            <div className="space-y-1">
              <p className="text-[11px] uppercase tracking-wider text-slate-500 font-semibold">
                Rejected
              </p>
              <p className="text-xs text-slate-400">
                {new Date(alt.rejected_at).toLocaleDateString("en-US", {
                  month: "long",
                  day: "numeric",
                  year: "numeric",
                })}
              </p>
            </div>
          )}

          <div className="flex items-center gap-2 pt-1">
            <Link
              href={`/decisions?id=${alt.rejected_by_decision_id}`}
              className="text-xs text-violet-400 hover:text-violet-300 underline underline-offset-2 transition-colors"
            >
              View original decision →
            </Link>
          </div>
        </div>
      )}
    </div>
  )
}

// --------------------------------------------------------------------------
// Summary stat card
// --------------------------------------------------------------------------

function StatCard({
  label,
  value,
  icon: Icon,
  color,
}: {
  label: string
  value: number | string
  icon: React.ElementType
  color: string
}) {
  return (
    <Card className="bg-white/[0.03] border-white/[0.06]">
      <CardContent className="p-4 flex items-center gap-3">
        <div className={`p-2 rounded-lg ${color}`}>
          <Icon className="h-4 w-4" />
        </div>
        <div>
          <p className="text-xl font-bold text-slate-100">{value}</p>
          <p className="text-xs text-slate-400">{label}</p>
        </div>
      </CardContent>
    </Card>
  )
}

// --------------------------------------------------------------------------
// Main page
// --------------------------------------------------------------------------

export default function BranchExplorerPage() {
  const [expandedId, setExpandedId] = useState<string | null>(null)
  const [minDays, setMinDays] = useState(14)

  const { data: alternatives, isLoading, error, refetch } = useQuery({
    queryKey: ["dormant-alternatives", minDays],
    queryFn: () => api.getDormantAlternatives({ minDaysDormant: minDays, limit: 100 }),
    staleTime: 60 * 1000,
  })

  const highPriority = alternatives?.filter((a) => a.reconsider_score >= 0.7) ?? []
  const medium = alternatives?.filter((a) => a.reconsider_score >= 0.4 && a.reconsider_score < 0.7) ?? []
  const low = alternatives?.filter((a) => a.reconsider_score < 0.4) ?? []

  const longestDormant = alternatives?.reduce(
    (max, a) => (a.days_dormant > max ? a.days_dormant : max),
    0
  ) ?? 0

  const toggle = (id: string) => setExpandedId((prev) => (prev === id ? null : id))

  return (
    <AppShell>
      <div className="max-w-4xl mx-auto p-6 space-y-6">
        {/* Header */}
        <div className="flex items-start justify-between">
          <div>
            <div className="flex items-center gap-3 mb-1">
              <Button variant="ghost" size="sm" asChild className="text-slate-400 hover:text-slate-200 -ml-2">
                <Link href="/decisions" className="flex items-center gap-1">
                  <ArrowLeft className="h-4 w-4" />
                  Decisions
                </Link>
              </Button>
            </div>
            <h1 className="text-2xl font-bold tracking-tight text-slate-100 flex items-center gap-2">
              <GitBranch className="h-6 w-6 text-fuchsia-400" />
              Branch Explorer
            </h1>
            <p className="text-sm text-slate-400 mt-1">
              Rejected and unexplored paths — alternatives worth reconsidering
            </p>
          </div>

          <div className="flex items-center gap-2">
            {/* Dormancy filter */}
            <div className="flex items-center gap-1.5 text-xs text-slate-400 bg-white/[0.04] rounded-lg px-3 py-1.5 border border-white/[0.08]">
              <Clock className="h-3.5 w-3.5" />
              <span>Dormant &gt;</span>
              <select
                value={minDays}
                onChange={(e) => setMinDays(Number(e.target.value))}
                className="bg-transparent text-slate-300 outline-none cursor-pointer"
              >
                <option value={7}>7d</option>
                <option value={14}>14d</option>
                <option value={30}>30d</option>
                <option value={90}>90d</option>
                <option value={180}>180d</option>
              </select>
            </div>
            <Button
              variant="ghost"
              size="sm"
              onClick={() => refetch()}
              className="text-slate-400 hover:text-slate-200"
            >
              <RefreshCw className="h-4 w-4" />
            </Button>
          </div>
        </div>

        {/* Stats row */}
        {!isLoading && alternatives && (
          <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
            <StatCard
              label="Total branches"
              value={alternatives.length}
              icon={GitBranch}
              color="bg-fuchsia-500/15 text-fuchsia-400"
            />
            <StatCard
              label="High priority"
              value={highPriority.length}
              icon={AlertTriangle}
              color="bg-rose-500/15 text-rose-400"
            />
            <StatCard
              label="Worth revisiting"
              value={medium.length}
              icon={Lightbulb}
              color="bg-amber-500/15 text-amber-400"
            />
            <StatCard
              label="Longest dormant"
              value={
                longestDormant >= 365
                  ? `${Math.round(longestDormant / 365)}y`
                  : `${longestDormant}d`
              }
              icon={Clock}
              color="bg-slate-500/15 text-slate-400"
            />
          </div>
        )}

        {isLoading && (
          <div className="space-y-3">
            {[...Array(5)].map((_, i) => (
              <Skeleton key={i} className="h-20 w-full rounded-xl" />
            ))}
          </div>
        )}

        {error && (
          <ErrorState
            title="Failed to load alternatives"
            message="Could not fetch dormant decision alternatives."
            retry={() => refetch()}
          />
        )}

        {!isLoading && !error && alternatives?.length === 0 && (
          <Card className="bg-white/[0.03] border-white/[0.06]">
            <CardContent className="flex flex-col items-center justify-center py-16 gap-3">
              <GitBranch className="h-10 w-10 text-slate-600" />
              <p className="text-slate-400 text-sm">
                No dormant alternatives found for the selected time window.
              </p>
              <p className="text-slate-500 text-xs">
                Alternatives appear here when rejected options haven't been revisited.
              </p>
            </CardContent>
          </Card>
        )}

        {/* High priority section */}
        {highPriority.length > 0 && (
          <section className="space-y-3">
            <div className="flex items-center gap-2">
              <AlertTriangle className="h-4 w-4 text-rose-400" />
              <h2 className="text-sm font-semibold text-slate-300 uppercase tracking-wider">
                High Priority
              </h2>
              <Badge className="text-[10px] bg-rose-500/15 text-rose-400 border-rose-500/30">
                {highPriority.length}
              </Badge>
              <p className="text-xs text-slate-500">Reconsider score ≥ 70%</p>
            </div>
            <div className="space-y-2">
              {highPriority.map((alt) => (
                <BranchCard
                  key={alt.candidate_id}
                  alt={alt}
                  expanded={expandedId === alt.candidate_id}
                  onToggle={() => toggle(alt.candidate_id)}
                />
              ))}
            </div>
          </section>
        )}

        {/* Medium priority section */}
        {medium.length > 0 && (
          <section className="space-y-3">
            <div className="flex items-center gap-2">
              <Lightbulb className="h-4 w-4 text-amber-400" />
              <h2 className="text-sm font-semibold text-slate-300 uppercase tracking-wider">
                Worth Revisiting
              </h2>
              <Badge className="text-[10px] bg-amber-500/15 text-amber-400 border-amber-500/30">
                {medium.length}
              </Badge>
              <p className="text-xs text-slate-500">Reconsider score 40–70%</p>
            </div>
            <div className="space-y-2">
              {medium.map((alt) => (
                <BranchCard
                  key={alt.candidate_id}
                  alt={alt}
                  expanded={expandedId === alt.candidate_id}
                  onToggle={() => toggle(alt.candidate_id)}
                />
              ))}
            </div>
          </section>
        )}

        {/* Low priority section */}
        {low.length > 0 && (
          <section className="space-y-3">
            <div className="flex items-center gap-2">
              <PauseCircle className="h-4 w-4 text-slate-400" />
              <h2 className="text-sm font-semibold text-slate-300 uppercase tracking-wider">
                Low Priority
              </h2>
              <Badge className="text-[10px] bg-slate-500/15 text-slate-400 border-slate-500/30">
                {low.length}
              </Badge>
            </div>
            <div className="space-y-2">
              {low.map((alt) => (
                <BranchCard
                  key={alt.candidate_id}
                  alt={alt}
                  expanded={expandedId === alt.candidate_id}
                  onToggle={() => toggle(alt.candidate_id)}
                />
              ))}
            </div>
          </section>
        )}
      </div>
    </AppShell>
  )
}
