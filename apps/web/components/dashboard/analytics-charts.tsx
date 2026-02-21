"use client"

import { useMemo, useState, useEffect } from "react"
import {
  LineChart,
  Line,
  PieChart,
  Pie,
  BarChart,
  Bar,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip as RechartsTooltip,
  ResponsiveContainer,
  Cell,
  Legend,
} from "recharts"
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card"
import { TrendingUp, PieChart as PieChartIcon, BarChart3, Activity, Zap, Target, Hash } from "lucide-react"

interface Decision {
  id: string
  created_at: string
  confidence: number
  entities: Array<{ type: string }>
}

interface AnalyticsChartsProps {
  decisions: Decision[]
}

// Nebula-themed colors
const ENTITY_TYPE_COLORS: Record<string, string> = {
  technology: "#fb923c", // Orange
  pattern: "#ec4899",    // Pink/Rose
  concept: "#a78bfa",    // Violet
  person: "#34d399",     // Emerald
  team: "#f472b6",       // Pink
  component: "#38bdf8",  // Sky blue
  system: "#4ade80",     // Green
  other: "#94a3b8",      // Slate
}

// Gradient confidence colors (violet to rose)
const CONFIDENCE_COLORS = [
  "#fecdd3", // Rose 200
  "#fda4af", // Rose 300
  "#fb7185", // Rose 400
  "#f472b6", // Pink 400
  "#a78bfa", // Violet 400
]

// Custom tooltip component for consistent styling
function CustomTooltip({ active, payload, label }: { active?: boolean; payload?: Array<{ value: number; name?: string }>; label?: string }) {
  if (active && payload && payload.length) {
    return (
      <div className="bg-slate-900/95 backdrop-blur-xl border border-white/10 rounded-xl px-3 py-2 shadow-xl">
        <p className="text-xs text-slate-400">{label}</p>
        <p className="text-sm font-semibold text-white">
          {payload[0].value} {payload[0].name || 'count'}
        </p>
      </div>
    )
  }
  return null
}

export function AnalyticsCharts({ decisions }: AnalyticsChartsProps) {
  // Prevent hydration mismatch - Recharts renders differently on server vs client
  const [mounted, setMounted] = useState(false)
  useEffect(() => {
    setMounted(true)
  }, [])

  const decisionsOverTime = useMemo(() => {
    const now = new Date()
    const thirtyDaysAgo = new Date(now.getTime() - 30 * 24 * 60 * 60 * 1000)
    const dateCounts: Record<string, number> = {}

    for (let d = new Date(thirtyDaysAgo); d <= now; d.setDate(d.getDate() + 1)) {
      const dateStr = d.toISOString().split("T")[0]
      dateCounts[dateStr] = 0
    }

    decisions.forEach((decision) => {
      const dateStr = decision.created_at.split("T")[0]
      if (dateCounts[dateStr] !== undefined) {
        dateCounts[dateStr]++
      }
    })

    return Object.entries(dateCounts)
      .map(([date, count]) => ({
        date: new Date(date).toLocaleDateString("en-US", { month: "short", day: "numeric" }),
        fullDate: date,
        count,
      }))
      .slice(-14)
  }, [decisions])

  const entityTypeDistribution = useMemo(() => {
    const typeCounts: Record<string, number> = {}

    decisions.forEach((decision) => {
      decision.entities?.forEach((entity) => {
        const type = entity.type || "other"
        typeCounts[type] = (typeCounts[type] || 0) + 1
      })
    })

    return Object.entries(typeCounts)
      .map(([name, value]) => ({
        name: name.charAt(0).toUpperCase() + name.slice(1),
        value,
        color: ENTITY_TYPE_COLORS[name] || ENTITY_TYPE_COLORS.other,
      }))
      .sort((a, b) => b.value - a.value)
  }, [decisions])

  const confidenceDistribution = useMemo(() => {
    const buckets = [
      { range: "0-20%", min: 0, max: 0.2, count: 0 },
      { range: "20-40%", min: 0.2, max: 0.4, count: 0 },
      { range: "40-60%", min: 0.4, max: 0.6, count: 0 },
      { range: "60-80%", min: 0.6, max: 0.8, count: 0 },
      { range: "80-100%", min: 0.8, max: 1.0, count: 0 },
    ]

    decisions.forEach((decision) => {
      const conf = decision.confidence || 0
      const bucket = buckets.find((b) => conf >= b.min && conf < b.max) || buckets[buckets.length - 1]
      bucket.count++
    })

    return buckets
  }, [decisions])

  const quickStats = useMemo(() => {
    const avgConfidence = decisions.length > 0
      ? decisions.reduce((sum, d) => sum + (d.confidence || 0), 0) / decisions.length
      : 0

    const totalEntities = decisions.reduce((sum, d) => sum + (d.entities?.length || 0), 0)

    const recentCount = decisions.filter((d) => {
      const created = new Date(d.created_at)
      const weekAgo = new Date(Date.now() - 7 * 24 * 60 * 60 * 1000)
      return created >= weekAgo
    }).length

    return {
      avgConfidence: Math.round(avgConfidence * 100),
      totalEntities,
      recentCount,
      avgEntitiesPerDecision: decisions.length > 0 ? (totalEntities / decisions.length).toFixed(1) : "0",
    }
  }, [decisions])

  if (decisions.length === 0) {
    return (
      <Card variant="glass" className="col-span-full">
        <CardContent className="flex items-center justify-center py-12">
          <p className="text-muted-foreground">No decisions yet to analyze</p>
        </CardContent>
      </Card>
    )
  }

  // Render placeholder until mounted to prevent hydration mismatch
  if (!mounted) {
    return (
      <div className="grid gap-4 md:grid-cols-2">
        {[...Array(4)].map((_, i) => (
          <Card key={i} variant="glass">
            <CardContent className="h-[280px] flex items-center justify-center">
              <div className="w-8 h-8 border-2 border-violet-500/30 border-t-violet-500 rounded-full animate-spin" />
            </CardContent>
          </Card>
        ))}
      </div>
    )
  }

  return (
    <div className="grid gap-4 md:grid-cols-2">
      {/* Decisions Over Time */}
      <Card variant="glass">
        <CardHeader className="pb-2">
          <div className="flex items-center gap-2">
            <div className="w-8 h-8 rounded-lg bg-gradient-to-br from-violet-500/20 to-fuchsia-500/10 border border-violet-500/20 flex items-center justify-center">
              <TrendingUp className="h-4 w-4 text-violet-400" />
            </div>
            <div>
              <CardTitle className="text-base">Decisions Over Time</CardTitle>
              <CardDescription>Last 14 days</CardDescription>
            </div>
          </div>
        </CardHeader>
        <CardContent>
          <div className="h-[200px]">
            <ResponsiveContainer width="100%" height="100%" minHeight={1} minWidth={1}>
              <LineChart data={decisionsOverTime}>
                <defs>
                  <linearGradient id="lineGradient" x1="0" y1="0" x2="1" y2="0">
                    <stop offset="0%" stopColor="#a78bfa" />
                    <stop offset="50%" stopColor="#ec4899" />
                    <stop offset="100%" stopColor="#fb923c" />
                  </linearGradient>
                </defs>
                <CartesianGrid strokeDasharray="3 3" stroke="rgba(255,255,255,0.05)" />
                <XAxis dataKey="date" fontSize={11} tickLine={false} axisLine={false} interval="preserveStartEnd" stroke="#64748b" />
                <YAxis fontSize={11} tickLine={false} axisLine={false} allowDecimals={false} stroke="#64748b" />
                <RechartsTooltip content={<CustomTooltip />} />
                <Line
                  type="monotone"
                  dataKey="count"
                  stroke="url(#lineGradient)"
                  strokeWidth={3}
                  dot={{ fill: "#a78bfa", strokeWidth: 0, r: 4 }}
                  activeDot={{ fill: "#ec4899", strokeWidth: 0, r: 6 }}
                />
              </LineChart>
            </ResponsiveContainer>
          </div>
        </CardContent>
      </Card>

      {/* Entity Types */}
      <Card variant="glass">
        <CardHeader className="pb-2">
          <div className="flex items-center gap-2">
            <div className="w-8 h-8 rounded-lg bg-gradient-to-br from-fuchsia-500/20 to-rose-500/10 border border-fuchsia-500/20 flex items-center justify-center">
              <PieChartIcon className="h-4 w-4 text-fuchsia-400" />
            </div>
            <div>
              <CardTitle className="text-base">Entity Types</CardTitle>
              <CardDescription>Distribution of extracted entities</CardDescription>
            </div>
          </div>
        </CardHeader>
        <CardContent>
          <div className="h-[200px]">
            {entityTypeDistribution.length > 0 ? (
              <ResponsiveContainer width="100%" height="100%" minHeight={1} minWidth={1}>
                <PieChart>
                  <Pie
                    data={entityTypeDistribution}
                    cx="50%"
                    cy="50%"
                    innerRadius={45}
                    outerRadius={75}
                    paddingAngle={3}
                    dataKey="value"
                    stroke="rgba(0,0,0,0.2)"
                    strokeWidth={2}
                  >
                    {entityTypeDistribution.map((entry, index) => (
                      <Cell key={index} fill={entry.color} />
                    ))}
                  </Pie>
                  <RechartsTooltip content={<CustomTooltip />} />
                  <Legend
                    verticalAlign="middle"
                    align="right"
                    layout="vertical"
                    iconType="circle"
                    iconSize={8}
                    wrapperStyle={{ fontSize: '11px', color: '#94a3b8' }}
                  />
                </PieChart>
              </ResponsiveContainer>
            ) : (
              <div className="flex h-full items-center justify-center">
                <p className="text-sm text-muted-foreground">No entities extracted yet</p>
              </div>
            )}
          </div>
        </CardContent>
      </Card>

      {/* Confidence Distribution */}
      <Card variant="glass">
        <CardHeader className="pb-2">
          <div className="flex items-center gap-2">
            <div className="w-8 h-8 rounded-lg bg-gradient-to-br from-rose-500/20 to-orange-500/10 border border-rose-500/20 flex items-center justify-center">
              <BarChart3 className="h-4 w-4 text-rose-400" />
            </div>
            <div>
              <CardTitle className="text-base">Confidence Distribution</CardTitle>
              <CardDescription>Extraction confidence levels</CardDescription>
            </div>
          </div>
        </CardHeader>
        <CardContent>
          <div className="h-[200px]">
            <ResponsiveContainer width="100%" height="100%" minHeight={1} minWidth={1}>
              <BarChart data={confidenceDistribution}>
                <CartesianGrid strokeDasharray="3 3" stroke="rgba(255,255,255,0.05)" />
                <XAxis dataKey="range" fontSize={11} tickLine={false} axisLine={false} stroke="#64748b" />
                <YAxis fontSize={11} tickLine={false} axisLine={false} allowDecimals={false} stroke="#64748b" />
                <RechartsTooltip content={<CustomTooltip />} />
                <Bar dataKey="count" radius={[6, 6, 0, 0]}>
                  {confidenceDistribution.map((_, index) => (
                    <Cell key={index} fill={CONFIDENCE_COLORS[index]} />
                  ))}
                </Bar>
              </BarChart>
            </ResponsiveContainer>
          </div>
        </CardContent>
      </Card>

      {/* Quick Stats */}
      <Card variant="glass">
        <CardHeader className="pb-2">
          <div className="flex items-center gap-2">
            <div className="w-8 h-8 rounded-lg bg-gradient-to-br from-orange-500/20 to-amber-500/10 border border-orange-500/20 flex items-center justify-center">
              <Activity className="h-4 w-4 text-orange-400" />
            </div>
            <div>
              <CardTitle className="text-base">Quick Stats</CardTitle>
              <CardDescription>Summary metrics</CardDescription>
            </div>
          </div>
        </CardHeader>
        <CardContent>
          <div className="grid grid-cols-2 gap-4">
            <div className="p-3 rounded-xl bg-white/[0.02] border border-white/[0.06] hover:border-violet-500/30 transition-colors">
              <div className="flex items-center gap-2 mb-1">
                <Target className="h-4 w-4 text-violet-400" />
                <p className="text-2xl font-bold gradient-text">{quickStats.avgConfidence}%</p>
              </div>
              <p className="text-xs text-muted-foreground">Avg Confidence</p>
            </div>
            <div className="p-3 rounded-xl bg-white/[0.02] border border-white/[0.06] hover:border-fuchsia-500/30 transition-colors">
              <div className="flex items-center gap-2 mb-1">
                <Hash className="h-4 w-4 text-fuchsia-400" />
                <p className="text-2xl font-bold gradient-text">{quickStats.totalEntities}</p>
              </div>
              <p className="text-xs text-muted-foreground">Total Entities</p>
            </div>
            <div className="p-3 rounded-xl bg-white/[0.02] border border-white/[0.06] hover:border-rose-500/30 transition-colors">
              <div className="flex items-center gap-2 mb-1">
                <Zap className="h-4 w-4 text-rose-400" />
                <p className="text-2xl font-bold gradient-text">{quickStats.recentCount}</p>
              </div>
              <p className="text-xs text-muted-foreground">This Week</p>
            </div>
            <div className="p-3 rounded-xl bg-white/[0.02] border border-white/[0.06] hover:border-orange-500/30 transition-colors">
              <div className="flex items-center gap-2 mb-1">
                <Activity className="h-4 w-4 text-orange-400" />
                <p className="text-2xl font-bold gradient-text">{quickStats.avgEntitiesPerDecision}</p>
              </div>
              <p className="text-xs text-muted-foreground">Entities/Decision</p>
            </div>
          </div>
        </CardContent>
      </Card>
    </div>
  )
}
