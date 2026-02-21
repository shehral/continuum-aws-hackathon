"use client"

import { useMemo, useState } from "react"
import { useQuery } from "@tanstack/react-query"
import Link from "next/link"
import {
  ArrowLeft,
  Calendar,
  Circle,
  BarChart2,
  List,
} from "lucide-react"

import { AppShell } from "@/components/layout/app-shell"
import { Card, CardContent } from "@/components/ui/card"
import { Badge } from "@/components/ui/badge"
import { Button } from "@/components/ui/button"
import { ErrorState } from "@/components/ui/error-state"
import { DecisionListSkeleton } from "@/components/ui/skeleton"
import { api, type Decision, type TimelineBucket } from "@/lib/api"
import { getEntityStyle } from "@/lib/constants"

// --------------------------------------------------------------------------
// Scope colours (mirrors the backend SCOPE_STALENESS_DAYS taxonomy)
// --------------------------------------------------------------------------

const SCOPE_COLORS: Record<string, { bar: string; badge: string; label: string }> = {
  strategic:     { bar: "bg-violet-500",  badge: "bg-violet-500/15 text-violet-300",  label: "Strategic"     },
  architectural: { bar: "bg-sky-500",     badge: "bg-sky-500/15 text-sky-300",        label: "Architectural"  },
  library:       { bar: "bg-emerald-500", badge: "bg-emerald-500/15 text-emerald-300",label: "Library"        },
  config:        { bar: "bg-amber-500",   badge: "bg-amber-500/15 text-amber-300",    label: "Config"         },
  operational:   { bar: "bg-rose-500",    badge: "bg-rose-500/15 text-rose-300",      label: "Operational"    },
  unknown:       { bar: "bg-slate-500",   badge: "bg-slate-500/15 text-slate-400",    label: "Unknown"        },
}

const SCOPE_ORDER = ["strategic", "architectural", "library", "config", "operational", "unknown"]

// --------------------------------------------------------------------------
// Month-group types (for list mode)
// --------------------------------------------------------------------------

interface MonthGroup {
  label: string
  sortKey: string
  decisions: Decision[]
}

// --------------------------------------------------------------------------
// Chart mode component
// --------------------------------------------------------------------------

function ChartMode({ buckets }: { buckets: TimelineBucket[] }) {
  const maxCount = Math.max(...buckets.map((b) => b.count), 1)

  return (
    <div className="space-y-6">
      {/* Legend */}
      <div className="flex flex-wrap gap-3">
        {SCOPE_ORDER.filter((s) => s !== "unknown").map((scope) => {
          const c = SCOPE_COLORS[scope]
          return (
            <div key={scope} className="flex items-center gap-1.5">
              <div className={`h-2.5 w-2.5 rounded-sm ${c.bar}`} />
              <span className="text-xs text-slate-400">{c.label}</span>
            </div>
          )
        })}
      </div>

      {/* Bar chart */}
      <div className="overflow-x-auto pb-2">
        <div className="flex items-end gap-2 min-w-[320px]" style={{ minHeight: 180 }}>
          {buckets.map((bucket) => {
            const totalHeight = Math.max(4, (bucket.count / maxCount) * 160)

            // Build stacked segments in scope order
            const segments = SCOPE_ORDER.map((scope) => {
              const cnt = bucket.by_scope[scope] ?? 0
              return { scope, cnt }
            }).filter((s) => s.cnt > 0)

            return (
              <div key={bucket.period} className="flex flex-col items-center gap-1 flex-1 min-w-[32px]">
                {/* Tooltip trigger wrapper */}
                <div
                  className="group relative flex flex-col justify-end w-full cursor-default"
                  style={{ height: 164 }}
                >
                  {/* Stacked bar */}
                  <div
                    className="w-full flex flex-col-reverse rounded-sm overflow-hidden transition-all duration-300 group-hover:ring-1 group-hover:ring-white/20"
                    style={{ height: totalHeight }}
                  >
                    {segments.map(({ scope, cnt }) => {
                      const segHeight = (cnt / bucket.count) * totalHeight
                      return (
                        <div
                          key={scope}
                          className={`${SCOPE_COLORS[scope]?.bar ?? "bg-slate-500"} opacity-80 group-hover:opacity-100 transition-opacity`}
                          style={{ height: segHeight }}
                        />
                      )
                    })}
                  </div>

                  {/* Hover tooltip */}
                  <div className="absolute bottom-full left-1/2 -translate-x-1/2 mb-2 hidden group-hover:block z-10 pointer-events-none">
                    <div className="bg-slate-900 border border-white/10 rounded-lg p-2.5 text-xs text-slate-300 whitespace-nowrap shadow-xl">
                      <p className="font-semibold text-slate-100 mb-1">{bucket.period}</p>
                      <p>{bucket.count} decision{bucket.count !== 1 ? "s" : ""}</p>
                      {Object.entries(bucket.by_scope).map(([scope, cnt]) => (
                        cnt > 0 && (
                          <p key={scope} className="text-slate-400">
                            {SCOPE_COLORS[scope]?.label ?? scope}: {cnt}
                          </p>
                        )
                      ))}
                      <p className="text-slate-500 mt-0.5">
                        avg conf {Math.round(bucket.avg_confidence * 100)}%
                      </p>
                    </div>
                  </div>
                </div>

                {/* Period label */}
                <p className="text-[10px] text-slate-500 truncate w-full text-center leading-tight">
                  {bucket.period.replace(/^\d{4}-/, "")}
                </p>
              </div>
            )
          })}
        </div>
      </div>

      {/* Summary stats */}
      <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
        {SCOPE_ORDER.filter((s) => s !== "unknown").map((scope) => {
          const total = buckets.reduce((sum, b) => sum + (b.by_scope[scope] ?? 0), 0)
          const c = SCOPE_COLORS[scope]
          return (
            <div key={scope} className={`rounded-lg border px-3 py-2 ${c.badge} border-current/20`}>
              <p className="text-lg font-bold">{total}</p>
              <p className="text-[11px] opacity-80">{c.label}</p>
            </div>
          )
        })}
      </div>
    </div>
  )
}

// --------------------------------------------------------------------------
// Main page
// --------------------------------------------------------------------------

export default function TimelinePage() {
  const [viewMode, setViewMode] = useState<"list" | "chart">("list")
  const [granularity, setGranularity] = useState<"week" | "month">("month")
  const [monthsBack, setMonthsBack] = useState(6)

  // List mode: fetch all decisions
  const {
    data: allDecisions,
    isLoading: listLoading,
    error: listError,
    refetch: refetchList,
  } = useQuery({
    queryKey: ["all-decisions"],
    queryFn: () => api.getDecisions(),
    staleTime: 60 * 1000,
    enabled: viewMode === "list",
  })

  // Chart mode: fetch timeline buckets
  const {
    data: buckets,
    isLoading: chartLoading,
    error: chartError,
    refetch: refetchChart,
  } = useQuery({
    queryKey: ["analytics-timeline", granularity, monthsBack],
    queryFn: () => api.getTimeline({ granularity, monthsBack }),
    staleTime: 60 * 1000,
    enabled: viewMode === "chart",
  })

  // Build month groups for list mode
  const monthGroups = useMemo(() => {
    if (!allDecisions?.length) return []

    const groups: Record<string, Decision[]> = {}
    allDecisions.forEach((decision) => {
      const date = new Date(decision.created_at)
      const key = `${date.getFullYear()}-${String(date.getMonth() + 1).padStart(2, "0")}`
      if (!groups[key]) groups[key] = []
      groups[key].push(decision)
    })

    return Object.entries(groups)
      .map(([sortKey, decisions]): MonthGroup => ({
        label: new Date(sortKey + "-01").toLocaleDateString("en-US", {
          month: "long",
          year: "numeric",
        }),
        sortKey,
        decisions: decisions.sort(
          (a, b) => new Date(b.created_at).getTime() - new Date(a.created_at).getTime()
        ),
      }))
      .sort((a, b) => b.sortKey.localeCompare(a.sortKey))
  }, [allDecisions])

  const isLoading = viewMode === "list" ? listLoading : chartLoading
  const error = viewMode === "list" ? listError : chartError
  const refetch = viewMode === "list" ? refetchList : refetchChart

  return (
    <AppShell>
      <div className="max-w-3xl mx-auto p-6 space-y-6">
        {/* Header */}
        <div className="flex items-start justify-between gap-4 flex-wrap">
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
              <Calendar className="h-6 w-6 text-violet-400" />
              Decision Timeline
            </h1>
            <p className="text-sm text-slate-400 mt-1">
              {viewMode === "list"
                ? `${allDecisions?.length ?? 0} decisions across ${monthGroups.length} months`
                : `Decision rate by ${granularity}, last ${monthsBack} months`}
            </p>
          </div>

          {/* Controls */}
          <div className="flex items-center gap-2 flex-wrap">
            {/* Chart controls */}
            {viewMode === "chart" && (
              <>
                <select
                  value={granularity}
                  onChange={(e) => setGranularity(e.target.value as "week" | "month")}
                  className="text-xs bg-white/[0.04] border border-white/[0.08] text-slate-300 rounded-lg px-2.5 py-1.5 outline-none cursor-pointer"
                >
                  <option value="month">Monthly</option>
                  <option value="week">Weekly</option>
                </select>
                <select
                  value={monthsBack}
                  onChange={(e) => setMonthsBack(Number(e.target.value))}
                  className="text-xs bg-white/[0.04] border border-white/[0.08] text-slate-300 rounded-lg px-2.5 py-1.5 outline-none cursor-pointer"
                >
                  <option value={3}>3 months</option>
                  <option value={6}>6 months</option>
                  <option value={12}>12 months</option>
                  <option value={24}>24 months</option>
                </select>
              </>
            )}

            {/* View toggle */}
            <div className="flex items-center rounded-lg border border-white/[0.08] bg-white/[0.04] p-0.5">
              <Button
                variant="ghost"
                size="sm"
                onClick={() => setViewMode("list")}
                className={`h-7 px-2.5 rounded-md text-xs gap-1.5 transition-all ${
                  viewMode === "list"
                    ? "bg-violet-500/20 text-violet-300"
                    : "text-slate-400 hover:text-slate-200"
                }`}
              >
                <List className="h-3.5 w-3.5" />
                List
              </Button>
              <Button
                variant="ghost"
                size="sm"
                onClick={() => setViewMode("chart")}
                className={`h-7 px-2.5 rounded-md text-xs gap-1.5 transition-all ${
                  viewMode === "chart"
                    ? "bg-violet-500/20 text-violet-300"
                    : "text-slate-400 hover:text-slate-200"
                }`}
              >
                <BarChart2 className="h-3.5 w-3.5" />
                Chart
              </Button>
            </div>
          </div>
        </div>

        {isLoading && <DecisionListSkeleton />}

        {error && (
          <ErrorState
            title="Failed to load timeline"
            message="Could not fetch your decisions."
            retry={() => refetch()}
          />
        )}

        {/* ---- CHART MODE ---- */}
        {!isLoading && !error && viewMode === "chart" && buckets && (
          <Card className="bg-white/[0.03] border-white/[0.06]">
            <CardContent className="p-6">
              {buckets.length === 0 ? (
                <div className="flex items-center justify-center py-12">
                  <p className="text-muted-foreground text-sm">No decision data for this period</p>
                </div>
              ) : (
                <ChartMode buckets={buckets} />
              )}
            </CardContent>
          </Card>
        )}

        {/* ---- LIST MODE ---- */}
        {!isLoading && !error && viewMode === "list" && (
          <>
            {monthGroups.length === 0 && (
              <Card variant="glass">
                <CardContent className="flex items-center justify-center py-12">
                  <p className="text-muted-foreground">No decisions yet to show on the timeline</p>
                </CardContent>
              </Card>
            )}

            <div className="relative">
              {/* Vertical line */}
              <div className="absolute left-4 top-0 bottom-0 w-px bg-gradient-to-b from-violet-500/40 via-fuchsia-500/30 to-transparent" />

              {monthGroups.map((group) => (
                <div key={group.sortKey} className="mb-8">
                  {/* Month header */}
                  <div className="flex items-center gap-3 mb-4 relative">
                    <div className="w-8 h-8 rounded-full bg-violet-500/20 border border-violet-500/30 flex items-center justify-center z-10">
                      <Calendar className="h-4 w-4 text-violet-400" />
                    </div>
                    <h2 className="text-lg font-semibold text-slate-100">{group.label}</h2>
                    <Badge className="bg-white/[0.04] text-slate-400 border-white/[0.08]">
                      {group.decisions.length}
                    </Badge>
                  </div>

                  {/* Decision items */}
                  <div className="space-y-3 ml-4 pl-7 border-l border-transparent">
                    {group.decisions.map((decision) => (
                      <Link
                        key={decision.id}
                        href={`/decisions?id=${decision.id}`}
                        className="block group"
                      >
                        <div className="relative">
                          {/* Timeline dot */}
                          <div className="absolute -left-[31px] top-3 z-10">
                            <Circle className="h-2.5 w-2.5 text-fuchsia-400 fill-fuchsia-400/50" />
                          </div>

                          <Card className="bg-white/[0.03] border-white/[0.06] hover:bg-white/[0.06] hover:border-violet-500/30 transition-all duration-200 cursor-pointer">
                            <CardContent className="p-4">
                              <div className="flex items-start justify-between gap-3">
                                <div className="flex-1 min-w-0">
                                  <p className="text-sm font-medium text-slate-200 group-hover:text-violet-300 transition-colors truncate">
                                    {decision.trigger}
                                  </p>
                                  <p className="text-xs text-slate-500 mt-1 line-clamp-1">
                                    {decision.agent_decision}
                                  </p>
                                </div>
                                <div className="flex items-center gap-2 shrink-0">
                                  {/* Scope badge if present */}
                                  {(decision as Decision & { scope?: string }).scope && (
                                    <Badge
                                      className={`text-[10px] px-1.5 py-0 ${
                                        SCOPE_COLORS[(decision as Decision & { scope?: string }).scope!]?.badge ??
                                        SCOPE_COLORS.unknown.badge
                                      }`}
                                    >
                                      {(decision as Decision & { scope?: string }).scope}
                                    </Badge>
                                  )}
                                  <Badge
                                    className={`text-[10px] px-1.5 py-0 ${
                                      decision.confidence >= 0.8
                                        ? "bg-emerald-500/15 text-emerald-400"
                                        : decision.confidence >= 0.6
                                        ? "bg-amber-500/15 text-amber-400"
                                        : "bg-rose-500/15 text-rose-400"
                                    }`}
                                  >
                                    {Math.round(decision.confidence * 100)}%
                                  </Badge>
                                  <span className="text-[10px] text-slate-600">
                                    {new Date(decision.created_at).toLocaleDateString("en-US", {
                                      month: "short",
                                      day: "numeric",
                                    })}
                                  </span>
                                </div>
                              </div>

                              {decision.entities.length > 0 && (
                                <div className="flex flex-wrap gap-1 mt-2">
                                  {decision.entities.slice(0, 3).map((entity) => {
                                    const style = getEntityStyle(entity.type)
                                    return (
                                      <Badge
                                        key={entity.id}
                                        className={`text-[10px] px-1.5 py-0 ${style.bg} ${style.text} ${style.border}`}
                                      >
                                        <style.lucideIcon className="h-2.5 w-2.5 mr-0.5" aria-hidden="true" />
                                        {entity.name}
                                      </Badge>
                                    )
                                  })}
                                  {decision.entities.length > 3 && (
                                    <Badge className="text-[10px] px-1.5 py-0 bg-slate-500/15 text-slate-400">
                                      +{decision.entities.length - 3}
                                    </Badge>
                                  )}
                                </div>
                              )}
                            </CardContent>
                          </Card>
                        </div>
                      </Link>
                    ))}
                  </div>
                </div>
              ))}
            </div>
          </>
        )}
      </div>
    </AppShell>
  )
}
