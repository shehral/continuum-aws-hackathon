"use client"

import React, { useCallback, useEffect, useMemo, useRef, useState } from "react"
import {
  ReactFlow,
  Node,
  Edge,
  Controls,
  Background,
  MiniMap,
  useNodesState,
  useEdgesState,
  Panel,
  NodeProps,
  Handle,
  Position,
  MarkerType,
  BackgroundVariant,
  useReactFlow,
  ReactFlowProvider,
} from "@xyflow/react"
import "@xyflow/react/dist/style.css"

import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card"
import { Badge } from "@/components/ui/badge"
import { Button } from "@/components/ui/button"
import { ScrollArea } from "@/components/ui/scroll-area"
import { Tooltip, TooltipContent, TooltipProvider, TooltipTrigger } from "@/components/ui/tooltip"
import {
  X, Sparkles, GitBranch, Bot, User, FileText, Trash2, Loader2, Link2, Network,
  FolderOpen, Plus, Layout, ChevronDown, ChevronUp, Target, Columns, Lightbulb, Settings,
  Wrench, Code, ArrowUpRight, Box, RefreshCw, Zap, Clock, CircleDot, BarChart3,
  Atom, Brain, Server, Cpu, Layers, Search
} from "lucide-react"
import { Input } from "@/components/ui/input"
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu"
import { applyLayout, bundleEdges, LAYOUT_INFO, type LayoutType } from "./layout-utils"
import { type GraphData, type Decision, type Entity, type SimilarDecision, api } from "@/lib/api"
import Link from "next/link"
import { DeleteConfirmDialog } from "@/components/ui/confirm-dialog"

// Pre-computed style objects for source badges (P1-3)
const SOURCE_BADGE_STYLES = {
  claude_logs: {
    backgroundColor: "rgba(168,85,247,0.2)",
    color: "#c084fc",
    borderColor: "rgba(168,85,247,0.3)",
  },
  interview: {
    backgroundColor: "rgba(16,185,129,0.2)",
    color: "#34d399",
    borderColor: "rgba(16,185,129,0.3)",
  },
  manual: {
    backgroundColor: "rgba(245,158,11,0.2)",
    color: "#fbbf24",
    borderColor: "rgba(245,158,11,0.3)",
  },
  unknown: {
    backgroundColor: "rgba(34,211,238,0.2)",
    color: "#22d3ee",
    borderColor: "rgba(34,211,238,0.3)",
  },
} as const

// Decision source configuration
const SOURCE_STYLES: Record<string, {
  color: string
  borderColor: string
  icon: React.ReactNode
  label: string
  description: string
}> = {
  claude_logs: {
    color: "from-purple-800/90 to-purple-900/90",
    borderColor: "border-purple-500/50",
    icon: <Bot className="h-4 w-4 text-purple-400" />,
    label: "AI Extracted",
    description: "Extracted from Claude Code logs",
  },
  interview: {
    color: "from-emerald-800/90 to-emerald-900/90",
    borderColor: "border-emerald-500/50",
    icon: <User className="h-4 w-4 text-emerald-400" />,
    label: "Human Captured",
    description: "Captured via AI-guided interview",
  },
  manual: {
    color: "from-amber-800/90 to-amber-900/90",
    borderColor: "border-amber-500/50",
    icon: <FileText className="h-4 w-4 text-amber-400" />,
    label: "Manual Entry",
    description: "Manually entered by user",
  },
  unknown: {
    color: "from-slate-800/90 to-slate-900/90",
    borderColor: "border-cyan-500/30",
    icon: <Sparkles className="h-4 w-4 text-cyan-400" />,
    label: "Legacy",
    description: "Created before source tracking",
  },
}

// Relationship type styling configuration with accessibility patterns (P2-4)
const RELATIONSHIP_STYLES: Record<string, {
  color: string
  label: string
  icon: React.ReactNode
  strokeDasharray?: string
  animated?: boolean
}> = {
  INVOLVES: {
    color: "#22D3EE",
    label: "Involves",
    icon: <Link2 className="h-3 w-3" style={{ color: "#22D3EE" }} />,
    strokeDasharray: "5,5",
    animated: true,
  },
  SIMILAR_TO: {
    color: "#A78BFA",
    label: "Similar To",
    icon: <Sparkles className="h-3 w-3" style={{ color: "#A78BFA" }} />,
    animated: true,
  },
  INFLUENCED_BY: {
    color: "#F59E0B",
    label: "Influenced By",
    icon: <Clock className="h-3 w-3" style={{ color: "#F59E0B" }} />,
    strokeDasharray: "10,5",
  },
  IS_A: {
    color: "#10B981",
    label: "Is A",
    icon: <ArrowUpRight className="h-3 w-3" style={{ color: "#10B981" }} />,
  },
  PART_OF: {
    color: "#3B82F6",
    label: "Part Of",
    icon: <Box className="h-3 w-3" style={{ color: "#3B82F6" }} />,
  },
  RELATED_TO: {
    color: "#EC4899",
    label: "Related To",
    icon: <RefreshCw className="h-3 w-3" style={{ color: "#EC4899" }} />,
    strokeDasharray: "3,3",
  },
  DEPENDS_ON: {
    color: "#EF4444",
    label: "Depends On",
    icon: <Zap className="h-3 w-3" style={{ color: "#EF4444" }} />,
  },
}

// Pre-computed entity type config (moved outside component)
const ENTITY_TYPE_CONFIG: Record<string, {
  color: string
  icon: React.ReactNode
  iconClass: string
  bg: string
}> = {
  concept: {
    color: "border-blue-400",
    icon: <Atom className="h-4 w-4 text-blue-400" />,
    iconClass: "text-blue-400",
    bg: "from-blue-500/20 to-blue-600/10",
  },
  system: {
    color: "border-green-400",
    icon: <Server className="h-4 w-4 text-green-400" />,
    iconClass: "text-green-400",
    bg: "from-green-500/20 to-green-600/10",
  },
  person: {
    color: "border-purple-400",
    icon: <User className="h-4 w-4 text-purple-400" />,
    iconClass: "text-purple-400",
    bg: "from-purple-500/20 to-purple-600/10",
  },
  technology: {
    color: "border-orange-400",
    icon: <Code className="h-4 w-4 text-orange-400" />,
    iconClass: "text-orange-400",
    bg: "from-orange-500/20 to-orange-600/10",
  },
  pattern: {
    color: "border-pink-400",
    icon: <Target className="h-4 w-4 text-pink-400" />,
    iconClass: "text-pink-400",
    bg: "from-pink-500/20 to-pink-600/10",
  },
}

// Custom node component for decisions - memoized (P1-1)
const DecisionNode = React.memo(
  function DecisionNode({ data, selected }: NodeProps) {
    const nodeData = data as { label: string; decision?: Decision & { source?: string }; hasEmbedding?: boolean; isFocused?: boolean; isDimmed?: boolean }
    const source = nodeData.decision?.source || "unknown"
    const sourceStyle = SOURCE_STYLES[source] || SOURCE_STYLES.unknown
    const badgeStyle = SOURCE_BADGE_STYLES[source as keyof typeof SOURCE_BADGE_STYLES] || SOURCE_BADGE_STYLES.unknown
    const isFocused = nodeData.isFocused
    const isDimmed = nodeData.isDimmed

    return (
      <div
        className={`
          px-5 py-4 rounded-2xl min-w-[220px] max-w-[320px]
          bg-gradient-to-br ${sourceStyle.color}
          backdrop-blur-xl
          border-2 transition-all duration-300
          ${selected
            ? "border-white shadow-[0_0_40px_rgba(255,255,255,0.3)] scale-105"
            : `${sourceStyle.borderColor} hover:border-white/60 hover:scale-[1.02] shadow-[0_8px_32px_rgba(0,0,0,0.4)]`
          }
          ${isFocused
            ? "ring-2 ring-cyan-400 ring-offset-2 ring-offset-slate-900 animate-pulse"
            : ""
          }
          ${isDimmed ? "opacity-25 scale-95" : "opacity-100"}
        `}
        role="button"
        aria-label={`Decision node: ${nodeData.label}`}
        aria-pressed={selected}
      >
        <Handle
          type="target"
          position={Position.Top}
          className="!w-3 !h-3 !bg-white/80 !border-2 !border-slate-800"
        />
        <div className="flex items-center gap-2 mb-2">
          {sourceStyle.icon}
          <Badge
            className="text-[10px]"
            style={badgeStyle}
          >
            {sourceStyle.label}
          </Badge>
          {nodeData.hasEmbedding && (
            <span title="Has semantic embedding" aria-label="Has semantic embedding">
              <Sparkles className="h-3 w-3 text-purple-400" aria-hidden="true" />
            </span>
          )}
        </div>
        <TooltipProvider>
          <Tooltip>
            <TooltipTrigger asChild>
              <div className="font-semibold text-sm text-slate-100 line-clamp-2">
                {nodeData.label}
              </div>
            </TooltipTrigger>
            <TooltipContent side="top" className="max-w-lg">
              <p>{nodeData.label}</p>
            </TooltipContent>
          </Tooltip>
        </TooltipProvider>
        <TooltipProvider>
          <Tooltip>
            <TooltipTrigger asChild>
              <div className="text-xs text-slate-400 mt-2 line-clamp-2">
                {nodeData.decision?.agent_decision || "Decision trace"}
              </div>
            </TooltipTrigger>
            <TooltipContent side="bottom" className="max-w-lg">
              <p>{nodeData.decision?.agent_decision || "Decision trace"}</p>
            </TooltipContent>
          </Tooltip>
        </TooltipProvider>
        <Handle
          type="source"
          position={Position.Bottom}
          className="!w-3 !h-3 !bg-white/80 !border-2 !border-slate-800"
        />
      </div>
    )
  },
  // Custom comparison function for memoization (P1-1)
  (prev, next) => {
    const prevData = prev.data as { decision?: { id: string }; hasEmbedding?: boolean; isFocused?: boolean; isDimmed?: boolean }
    const nextData = next.data as { decision?: { id: string }; hasEmbedding?: boolean; isFocused?: boolean; isDimmed?: boolean }
    return prev.selected === next.selected &&
      prevData?.decision?.id === nextData?.decision?.id &&
      prevData?.hasEmbedding === nextData?.hasEmbedding &&
      prevData?.isFocused === nextData?.isFocused &&
      prevData?.isDimmed === nextData?.isDimmed
  }
)

// Custom node component for entities - memoized (P1-1)
const EntityNode = React.memo(
  function EntityNode({ data, selected }: NodeProps) {
    const nodeData = data as { label: string; entity?: Entity; hasEmbedding?: boolean; isFocused?: boolean; isDimmed?: boolean }
    const entityType = nodeData.entity?.type || "concept"
    const config = ENTITY_TYPE_CONFIG[entityType] || ENTITY_TYPE_CONFIG.concept
    const isFocused = nodeData.isFocused
    const isDimmed = nodeData.isDimmed
    const selectedClass = selected
      ? `shadow-[0_0_30px_rgba(59,130,246,0.5)] scale-110 border-white`
      : "hover:scale-105 hover:shadow-[0_4px_20px_rgba(0,0,0,0.3)]"

    return (
      <div
        className={`
          px-4 py-3 rounded-full
          bg-gradient-to-br ${config.bg}
          backdrop-blur-xl
          border-2 ${selected ? "border-white" : config.color}
          transition-all duration-300
          ${selectedClass}
          ${isFocused
            ? "ring-2 ring-cyan-400 ring-offset-2 ring-offset-slate-900 animate-pulse"
            : ""
          }
          ${isDimmed ? "opacity-25 scale-90" : "opacity-100"}
        `}
        role="button"
        aria-label={`Entity node: ${nodeData.label}, type: ${entityType}`}
        aria-pressed={selected}
      >
        <Handle
          type="target"
          position={Position.Top}
          className="!w-2 !h-2 !bg-slate-400 !border-slate-700"
        />
        <div className="flex items-center gap-2">
          <span aria-hidden="true">
            {config.icon}
          </span>
          <span className="font-medium text-sm text-slate-200 whitespace-nowrap">
            {nodeData.label}
          </span>
          {nodeData.hasEmbedding && (
            <span title="Has semantic embedding" aria-label="Has semantic embedding">
              <Sparkles className="h-3 w-3 text-purple-400" aria-hidden="true" />
            </span>
          )}
        </div>
        <Handle
          type="source"
          position={Position.Bottom}
          className="!w-2 !h-2 !bg-slate-400 !border-slate-700"
        />
      </div>
    )
  },
  // Custom comparison function for memoization (P1-1)
  (prev, next) => {
    const prevData = prev.data as { entity?: { id: string }; hasEmbedding?: boolean; isFocused?: boolean; isDimmed?: boolean }
    const nextData = next.data as { entity?: { id: string }; hasEmbedding?: boolean; isFocused?: boolean; isDimmed?: boolean }
    return prev.selected === next.selected &&
      prevData?.entity?.id === nextData?.entity?.id &&
      prevData?.hasEmbedding === nextData?.hasEmbedding &&
      prevData?.isFocused === nextData?.isFocused &&
      prevData?.isDimmed === nextData?.isDimmed
  }
)

const nodeTypes = {
  decision: DecisionNode,
  entity: EntityNode,
}
// Empty state component for when the graph has no nodes (FE-QW-6)
function GraphEmptyState() {
  return (
    <div className="h-full w-full flex items-center justify-center bg-slate-900/50">
      <div className="text-center max-w-md mx-auto p-8 animate-in fade-in zoom-in-95 duration-500">
        {/* Decorative illustration */}
        <div className="relative mx-auto mb-6 w-32 h-32">
          {/* Outer glow */}
          <div className="absolute inset-0 rounded-full bg-cyan-500/10 animate-pulse" />
          {/* Main circle */}
          <div className="absolute inset-2 rounded-full bg-gradient-to-br from-slate-800 to-slate-900 border-2 border-cyan-500/20 flex items-center justify-center">
            <Network className="h-12 w-12 text-cyan-400/70" aria-hidden="true" />
          </div>
          {/* Decorative nodes */}
          <div className="absolute top-0 right-0 w-6 h-6 rounded-full bg-purple-500/20 border border-purple-400/30 animate-bounce" style={{ animationDelay: '0.1s' }} />
          <div className="absolute bottom-2 left-0 w-5 h-5 rounded-full bg-green-500/20 border border-green-400/30 animate-bounce" style={{ animationDelay: '0.3s' }} />
          <div className="absolute bottom-0 right-4 w-4 h-4 rounded-full bg-orange-500/20 border border-orange-400/30 animate-bounce" style={{ animationDelay: '0.5s' }} />
          {/* Connection lines */}
          <svg className="absolute inset-0 w-full h-full" viewBox="0 0 128 128">
            <line x1="64" y1="64" x2="110" y2="20" stroke="rgba(168,85,247,0.3)" strokeWidth="1" strokeDasharray="4,4" />
            <line x1="64" y1="64" x2="20" y2="105" stroke="rgba(34,197,94,0.3)" strokeWidth="1" strokeDasharray="4,4" />
            <line x1="64" y1="64" x2="100" y2="110" stroke="rgba(249,115,22,0.3)" strokeWidth="1" strokeDasharray="4,4" />
          </svg>
        </div>

        <h3 className="text-xl font-semibold text-slate-100 mb-2">
          Your Knowledge Graph is Empty
        </h3>
        <p className="text-slate-400 mb-6 leading-relaxed">
          Import Claude Code conversation logs to automatically extract decisions, 
          or start a guided interview to capture knowledge manually.
        </p>

        <div className="flex flex-col sm:flex-row gap-3 justify-center">
          <Button
            asChild
            className="bg-gradient-to-r from-cyan-500 to-teal-400 text-slate-900 font-semibold shadow-[0_4px_16px_rgba(34,211,238,0.3)] hover:shadow-[0_6px_20px_rgba(34,211,238,0.4)] hover:scale-105 transition-all"
          >
            <Link href="/add">
              <FolderOpen className="h-4 w-4 mr-2" aria-hidden="true" />
              Import Claude Logs
            </Link>
          </Button>
          <Button
            asChild
            variant="outline"
            className="border-white/10 text-slate-300 hover:bg-white/[0.08] hover:text-slate-100"
          >
            <Link href="/decisions?add=true">
              <Plus className="h-4 w-4 mr-2" aria-hidden="true" />
              Add Manually
            </Link>
          </Button>
        </div>

        <p className="text-xs text-slate-500 mt-6">
          Tip: Decisions and their relationships will appear here as connected nodes
        </p>
      </div>
    </div>
  )
}


interface KnowledgeGraphProps {
  data?: GraphData
  onNodeClick?: (node: Node) => void
  sourceFilter?: string | null
  onSourceFilterChange?: (source: string | null) => void
  sourceCounts?: Record<string, number>
  projectFilter?: string | null
  onProjectFilterChange?: (project: string | null) => void
  projectCounts?: Record<string, number>
  onDeleteDecision?: (decisionId: string) => Promise<void>
}

// Inner component that uses useReactFlow hook (P0-3: Keyboard navigation)
function KnowledgeGraphInner({
  data,
  onNodeClick,
  sourceFilter,
  onSourceFilterChange,
  sourceCounts = {},
  projectFilter,
  onProjectFilterChange,
  projectCounts = {},
  onDeleteDecision,
}: KnowledgeGraphProps) {
  const [selectedNode, setSelectedNode] = useState<Node | null>(null)
  const [focusedNodeId, setFocusedNodeId] = useState<string | null>(null)
  const [hoveredNodeId, setHoveredNodeId] = useState<string | null>(null)
  const [showRelationshipLegend, setShowRelationshipLegend] = useState(true)
  const [showSourceLegend, setShowSourceLegend] = useState(true)
  const [showProjectFilter, setShowProjectFilter] = useState(true)
  const [deleteTarget, setDeleteTarget] = useState<{ id: string; name: string } | null>(null)
  const [layoutType, setLayoutType] = useState<LayoutType>("clustered") // Default to clustered for better UX
  // Graph search state
  const [graphSearchQuery, setGraphSearchQuery] = useState("")
  const [graphSearchMatchIds, setGraphSearchMatchIds] = useState<string[]>([])
  const [graphSearchIndex, setGraphSearchIndex] = useState(0)
  // Collapsible panel states
  const [sourcesExpanded, setSourcesExpanded] = useState(true)
  const [projectsExpanded, setProjectsExpanded] = useState(true)
  const [entityTypesExpanded, setEntityTypesExpanded] = useState(true)
  const [relationshipsExpanded, setRelationshipsExpanded] = useState(true)
  // Part 4.7: Scope layer filter — null means "show all scopes"
  const [scopeFilter, setScopeFilter] = useState<string | null>(null)
  const [showScopePanel, setShowScopePanel] = useState(true)
  const [scopeExpanded, setScopeExpanded] = useState(true)
  // Pathfinding state
  const [pathfindingMode, setPathfindingMode] = useState(false)
  const [pathStart, setPathStart] = useState<string | null>(null)
  const [pathEnd, setPathEnd] = useState<string | null>(null)
  const [pathNodeIds, setPathNodeIds] = useState<Set<string>>(new Set())
  const [pathEdgeIds, setPathEdgeIds] = useState<Set<string>>(new Set())
  // P1-3: Related decisions state
  const [relatedDecisions, setRelatedDecisions] = useState<SimilarDecision[]>([])
  const [relatedLoading, setRelatedLoading] = useState(false)
  const containerRef = useRef<HTMLDivElement>(null)
  const { setCenter, getZoom } = useReactFlow()

  // Build adjacency map for hover highlighting
  const adjacencyMap = useMemo(() => {
    if (!data?.edges) return new Map<string, Set<string>>()
    const map = new Map<string, Set<string>>()
    data.edges.forEach(edge => {
      if (!map.has(edge.source)) map.set(edge.source, new Set())
      if (!map.has(edge.target)) map.set(edge.target, new Set())
      map.get(edge.source)!.add(edge.target)
      map.get(edge.target)!.add(edge.source)
    })
    return map
  }, [data?.edges])

  // Convert graph data to React Flow format with layout
  const initialNodes: Node[] = useMemo(() => {
    if (!data?.nodes) return []

    // First, create nodes with placeholder positions
    const rawNodes: Node[] = data.nodes.map((node) => {
      // Determine if node should be highlighted (connected to hovered node)
      const isHighlighted = hoveredNodeId
        ? (node.id === hoveredNodeId || adjacencyMap.get(hoveredNodeId)?.has(node.id))
        : true // No hover = all visible
      const isDimmed = hoveredNodeId && !isHighlighted

      return {
        id: node.id,
        type: node.type,
        position: { x: 0, y: 0 }, // Will be set by layout
        data: {
          label: node.label,
          // Include the node.id in the decision/entity data for related decisions lookup
          decision: node.type === "decision" ? { ...node.data, id: node.id } : undefined,
          entity: node.type === "entity" ? { ...node.data, id: node.id } : undefined,
          hasEmbedding: node.has_embedding,
          isFocused: false,
          isHighlighted,
          isDimmed,
        },
      }
    })

    // Create edges for layout algorithm
    const rawEdges: Edge[] = data.edges?.map((edge) => ({
      id: edge.id,
      source: edge.source,
      target: edge.target,
    })) || []

    // Apply the selected layout algorithm
    return applyLayout(rawNodes, rawEdges, layoutType, { type: layoutType })
  }, [data, layoutType]) // Removed hoveredNodeId and adjacencyMap to prevent flickering on hover

  const initialEdges: Edge[] = useMemo(() => {
    if (!data?.edges) return []

    return data.edges.map((edge) => {
      const relStyle = RELATIONSHIP_STYLES[edge.relationship] || RELATIONSHIP_STYLES.INVOLVES
      const weight = edge.weight ?? 1.0

      // Calculate stroke width based on weight (similarity score)
      const strokeWidth = Math.max(2, Math.min(5, weight * 3.5))

      return {
        id: edge.id,
        source: edge.source,
        target: edge.target,
        label: weight < 1.0 ? `${relStyle.label} (${(weight * 100).toFixed(0)}%)` : relStyle.label,
        animated: relStyle.animated ?? false,
        labelStyle: {
          fill: "#fff",
          fontSize: 11,
          fontWeight: 600,
          textShadow: "0 1px 2px rgba(0,0,0,0.5)",
        },
        labelBgStyle: {
          fill: relStyle.color,
          fillOpacity: 0.85,
          rx: 8,
          ry: 8,
        },
        labelBgPadding: [8, 5] as [number, number],
        labelBgBorderRadius: 8,
        markerEnd: {
          type: MarkerType.ArrowClosed,
          color: relStyle.color,
          width: 18,
          height: 18,
        },
        style: {
          stroke: relStyle.color,
          strokeWidth,
          strokeDasharray: relStyle.strokeDasharray,
          opacity: 0.85 + (weight * 0.15),
          filter: `drop-shadow(0 0 ${Math.max(2, weight * 4)}px ${relStyle.color}40)`,
        },
      }
    })
  }, [data])

  const [nodes, setNodes, onNodesChange] = useNodesState(initialNodes)
  const [edges, setEdges, onEdgesChange] = useEdgesState(initialEdges)

  // BFS shortest path between two nodes
  const findShortestPath = useCallback((startId: string, endId: string) => {
    if (!adjacencyMap.size) return
    const queue: string[][] = [[startId]]
    const visited = new Set<string>([startId])

    while (queue.length > 0) {
      const path = queue.shift()!
      const current = path[path.length - 1]

      if (current === endId) {
        const nodeIds = new Set(path)
        const edgeIds = new Set<string>()
        for (let i = 0; i < path.length - 1; i++) {
          data?.edges.forEach((e: { id: string; source: string; target: string }) => {
            if ((e.source === path[i] && e.target === path[i + 1]) ||
                (e.source === path[i + 1] && e.target === path[i])) {
              edgeIds.add(e.id)
            }
          })
        }
        setPathNodeIds(nodeIds)
        setPathEdgeIds(edgeIds)
        setNodes(nds => nds.map(n => ({
          ...n,
          style: { ...n.style, opacity: nodeIds.has(n.id) ? 1 : 0.15 },
        })))
        setEdges(eds => eds.map(e => ({
          ...e,
          style: {
            ...e.style,
            opacity: edgeIds.has(e.id) ? 1 : 0.08,
            strokeWidth: edgeIds.has(e.id) ? 3 : 1,
            stroke: edgeIds.has(e.id) ? "#a78bfa" : undefined,
          },
          animated: edgeIds.has(e.id),
        })))
        return
      }

      const neighbors = adjacencyMap.get(current)
      if (neighbors) {
        for (const neighbor of neighbors) {
          if (!visited.has(neighbor)) {
            visited.add(neighbor)
            queue.push([...path, neighbor])
          }
        }
      }
    }
    setPathNodeIds(new Set())
    setPathEdgeIds(new Set())
  }, [adjacencyMap, data?.edges, setNodes, setEdges])

  const handlePathfindingClick = useCallback((nodeId: string) => {
    if (!pathfindingMode) return
    if (!pathStart) {
      setPathStart(nodeId)
    } else if (!pathEnd && nodeId !== pathStart) {
      setPathEnd(nodeId)
      findShortestPath(pathStart, nodeId)
    }
  }, [pathfindingMode, pathStart, pathEnd, findShortestPath])

  const clearPathfinding = useCallback(() => {
    setPathfindingMode(false)
    setPathStart(null)
    setPathEnd(null)
    setPathNodeIds(new Set())
    setPathEdgeIds(new Set())
    setNodes(nds => nds.map(n => ({ ...n, style: { ...n.style, opacity: 1 } })))
    setEdges(eds => eds.map(e => ({
      ...e,
      style: { ...e.style, opacity: 1, strokeWidth: 1, stroke: undefined },
      animated: false,
    })))
  }, [setNodes, setEdges])

  // Update nodes when layout changes or initialNodes recalculates
  useEffect(() => {
    setNodes(initialNodes)
  }, [initialNodes, setNodes])

  // Update nodes when focusedNodeId changes to add focus indicator (P0-3)
  useEffect(() => {
    setNodes((prevNodes) =>
      prevNodes.map((node) => ({
        ...node,
        data: {
          ...node.data,
          isFocused: node.id === focusedNodeId,
        },
      }))
    )
  }, [focusedNodeId, setNodes])

  // Part 4.7: Apply scope layer filter — dim nodes that don't match the active scope
  useEffect(() => {
    if (!scopeFilter) {
      // Clear scope dimming — restore all nodes
      setNodes((prevNodes) =>
        prevNodes.map((node) => ({
          ...node,
          data: { ...node.data, isDimmed: false },
        }))
      )
      return
    }
    setNodes((prevNodes) =>
      prevNodes.map((node) => {
        if (node.type !== "decision") {
          // Entity nodes: dim if no decision at this scope is connected
          return { ...node, data: { ...node.data, isDimmed: true } }
        }
        const nodeScope = (node.data as { decision?: { scope?: string } }).decision?.scope
        const matches = !nodeScope || nodeScope === scopeFilter
        return { ...node, data: { ...node.data, isDimmed: !matches } }
      })
    )
  }, [scopeFilter, setNodes])

  // P1-3: Fetch related decisions when a decision node is selected
  useEffect(() => {
    if (!selectedNode || selectedNode.type !== "decision") {
      setRelatedDecisions([])
      return
    }

    const decisionData = selectedNode.data as { decision?: Decision }
    if (!decisionData.decision?.id) return

    const fetchRelated = async () => {
      setRelatedLoading(true)
      try {
        const similar = await api.getSimilarDecisions(decisionData.decision!.id, 5, 0.3)
        setRelatedDecisions(similar)
      } catch (error) {
        console.error("Failed to fetch related decisions:", error)
        setRelatedDecisions([])
      } finally {
        setRelatedLoading(false)
      }
    }

    fetchRelated()
  }, [selectedNode])

  // Count relationships by type
  const relationshipCounts = useMemo(() => {
    if (!data?.edges) return {}
    return data.edges.reduce((acc, edge) => {
      acc[edge.relationship] = (acc[edge.relationship] || 0) + 1
      return acc
    }, {} as Record<string, number>)
  }, [data])

  // Find the nearest node in a given direction (P0-3: Keyboard navigation)
  const findNearestNode = useCallback(
    (currentNode: Node, direction: "up" | "down" | "left" | "right"): Node | null => {
      if (nodes.length === 0) return null

      const currentPos = currentNode.position
      let nearestNode: Node | null = null
      let nearestDistance = Infinity

      for (const node of nodes) {
        if (node.id === currentNode.id) continue

        const nodePos = node.position
        const dx = nodePos.x - currentPos.x
        const dy = nodePos.y - currentPos.y

        // Check if node is in the correct direction
        let isInDirection = false
        switch (direction) {
          case "up":
            isInDirection = dy < -20 && Math.abs(dx) < Math.abs(dy) * 2
            break
          case "down":
            isInDirection = dy > 20 && Math.abs(dx) < Math.abs(dy) * 2
            break
          case "left":
            isInDirection = dx < -20 && Math.abs(dy) < Math.abs(dx) * 2
            break
          case "right":
            isInDirection = dx > 20 && Math.abs(dy) < Math.abs(dx) * 2
            break
        }

        if (isInDirection) {
          const distance = Math.sqrt(dx * dx + dy * dy)
          if (distance < nearestDistance) {
            nearestDistance = distance
            nearestNode = node
          }
        }
      }

      return nearestNode
    },
    [nodes]
  )

  // Center view on a node (P0-3: Keyboard navigation)
  const centerOnNode = useCallback(
    (node: Node) => {
      const zoom = getZoom()
      setCenter(node.position.x + 100, node.position.y + 50, { zoom, duration: 200 })
    },
    [setCenter, getZoom]
  )

  // Keyboard navigation handler (P0-3)
  const handleKeyDown = useCallback(
    (event: React.KeyboardEvent) => {
      // Ignore if user is typing in an input
      if (
        event.target instanceof HTMLInputElement ||
        event.target instanceof HTMLTextAreaElement
      ) {
        return
      }

      switch (event.key) {
        case "ArrowUp":
        case "ArrowDown":
        case "ArrowLeft":
        case "ArrowRight": {
          event.preventDefault()
          const direction = event.key.replace("Arrow", "").toLowerCase() as
            | "up"
            | "down"
            | "left"
            | "right"

          // If no node is focused, focus the first node
          if (!focusedNodeId) {
            const firstNode = nodes[0]
            if (firstNode) {
              setFocusedNodeId(firstNode.id)
              centerOnNode(firstNode)
            }
            return
          }

          // Find the currently focused node
          const currentNode = nodes.find((n) => n.id === focusedNodeId)
          if (!currentNode) return

          // Find and focus the nearest node in the direction
          const nearestNode = findNearestNode(currentNode, direction)
          if (nearestNode) {
            setFocusedNodeId(nearestNode.id)
            centerOnNode(nearestNode)
          }
          break
        }

        case "Enter":
        case " ": {
          event.preventDefault()
          // Select the focused node (open detail panel)
          if (focusedNodeId) {
            const node = nodes.find((n) => n.id === focusedNodeId)
            if (node) {
              setSelectedNode(node)
              onNodeClick?.(node)
            }
          }
          break
        }

        case "Escape": {
          event.preventDefault()
          // Deselect node and clear focus
          if (selectedNode) {
            setSelectedNode(null)
          } else if (focusedNodeId) {
            setFocusedNodeId(null)
          }
          break
        }

        case "Tab": {
          // Let Tab work naturally for focus management
          // but if we are inside the graph, move to next node
          if (!event.shiftKey && focusedNodeId) {
            const currentIndex = nodes.findIndex((n) => n.id === focusedNodeId)
            const nextIndex = (currentIndex + 1) % nodes.length
            const nextNode = nodes[nextIndex]
            if (nextNode) {
              event.preventDefault()
              setFocusedNodeId(nextNode.id)
              centerOnNode(nextNode)
            }
          } else if (event.shiftKey && focusedNodeId) {
            const currentIndex = nodes.findIndex((n) => n.id === focusedNodeId)
            const prevIndex = currentIndex === 0 ? nodes.length - 1 : currentIndex - 1
            const prevNode = nodes[prevIndex]
            if (prevNode) {
              event.preventDefault()
              setFocusedNodeId(prevNode.id)
              centerOnNode(prevNode)
            }
          }
          break
        }

        case "Home": {
          event.preventDefault()
          // Focus first node
          const firstNode = nodes[0]
          if (firstNode) {
            setFocusedNodeId(firstNode.id)
            centerOnNode(firstNode)
          }
          break
        }

        case "End": {
          event.preventDefault()
          // Focus last node
          const lastNode = nodes[nodes.length - 1]
          if (lastNode) {
            setFocusedNodeId(lastNode.id)
            centerOnNode(lastNode)
          }
          break
        }
      }
    },
    [focusedNodeId, nodes, selectedNode, findNearestNode, centerOnNode, onNodeClick]
  )

  // Memoized event handlers (P1-4)
  const handleNodeClick = useCallback(
    (_: React.MouseEvent, node: Node) => {
      if (pathfindingMode) {
        handlePathfindingClick(node.id)
        return
      }
      setSelectedNode(node)
      setFocusedNodeId(node.id)
      onNodeClick?.(node)
    },
    [onNodeClick, pathfindingMode, handlePathfindingClick]
  )

  const closeDetailPanel = useCallback(() => setSelectedNode(null), [])

  const handleDeleteClick = useCallback((id: string, name: string) => {
    setDeleteTarget({ id, name })
  }, [])

  const handleDeleteConfirm = useCallback(async () => {
    if (deleteTarget && onDeleteDecision) {
      await onDeleteDecision(deleteTarget.id)
      setDeleteTarget(null)
      setSelectedNode(null)
    }
  }, [deleteTarget, onDeleteDecision])

  const handleSourceFilterClick = useCallback((source: string | null) => {
    onSourceFilterChange?.(source)
  }, [onSourceFilterChange])

  // Handle node hover for highlighting connected nodes
  const handleNodeMouseEnter = useCallback((_: React.MouseEvent, node: Node) => {
    setHoveredNodeId(node.id)
  }, [])

  const handleNodeMouseLeave = useCallback(() => {
    setHoveredNodeId(null)
  }, [])

  // Handle focus on container click
  const handleContainerFocus = useCallback(() => {
    if (!focusedNodeId && nodes.length > 0) {
      setFocusedNodeId(nodes[0].id)
    }
  }, [focusedNodeId, nodes])

  // Graph search: find nodes matching query
  const handleGraphSearch = useCallback(
    (query: string) => {
      setGraphSearchQuery(query)
      if (!query.trim()) {
        setGraphSearchMatchIds([])
        setGraphSearchIndex(0)
        // Remove highlight from nodes
        setNodes((prev) => prev.map((n) => ({ ...n, data: { ...n.data, isFocused: false, isDimmed: false } })))
        return
      }
      const q = query.toLowerCase()
      const matches = nodes
        .filter((n) => {
          const label = (n.data as { label?: string }).label?.toLowerCase() || ""
          return label.includes(q)
        })
        .map((n) => n.id)
      setGraphSearchMatchIds(matches)
      setGraphSearchIndex(0)
      if (matches.length > 0) {
        const matchNode = nodes.find((n) => n.id === matches[0])
        if (matchNode) {
          setFocusedNodeId(matchNode.id)
          centerOnNode(matchNode)
        }
        // Dim non-matching nodes
        setNodes((prev) =>
          prev.map((n) => ({
            ...n,
            data: {
              ...n.data,
              isFocused: n.id === matches[0],
              isDimmed: !matches.includes(n.id),
            },
          }))
        )
      } else {
        setNodes((prev) => prev.map((n) => ({ ...n, data: { ...n.data, isFocused: false, isDimmed: false } })))
      }
    },
    [nodes, centerOnNode, setNodes]
  )

  const handleGraphSearchNext = useCallback(() => {
    if (graphSearchMatchIds.length === 0) return
    const nextIndex = (graphSearchIndex + 1) % graphSearchMatchIds.length
    setGraphSearchIndex(nextIndex)
    const matchNode = nodes.find((n) => n.id === graphSearchMatchIds[nextIndex])
    if (matchNode) {
      setFocusedNodeId(matchNode.id)
      centerOnNode(matchNode)
      setNodes((prev) =>
        prev.map((n) => ({
          ...n,
          data: { ...n.data, isFocused: n.id === graphSearchMatchIds[nextIndex] },
        }))
      )
    }
  }, [graphSearchMatchIds, graphSearchIndex, nodes, centerOnNode, setNodes])

  // Show empty state when there are no nodes (FE-QW-6)
  if (!data?.nodes || data.nodes.length === 0) {
    return <GraphEmptyState />
  }

  return (
    <div
      ref={containerRef}
      className="h-full w-full relative focus:outline-none"
      role="application"
      aria-label="Knowledge graph visualization. Use arrow keys to navigate between nodes, Enter to select, Escape to deselect."
      tabIndex={0}
      onKeyDown={handleKeyDown}
      onFocus={handleContainerFocus}
    >
      {/* Screen reader instructions */}
      <div className="sr-only" aria-live="polite">
        {focusedNodeId
          ? `Focused on node: ${nodes.find((n) => n.id === focusedNodeId)?.data?.label || "unknown"}. Press Enter to view details, arrow keys to navigate.`
          : "Press Tab or arrow keys to start navigating the graph."}
      </div>

      <ReactFlow
        nodes={nodes}
        edges={edges}
        onNodesChange={onNodesChange}
        onEdgesChange={onEdgesChange}
        onNodeClick={handleNodeClick}
        onNodeMouseEnter={handleNodeMouseEnter}
        onNodeMouseLeave={handleNodeMouseLeave}
        nodeTypes={nodeTypes}
        nodesDraggable={true}
        nodesConnectable={false}
        fitViewOptions={{ padding: 0.2, maxZoom: 1.2 }}
        minZoom={0.05}
        maxZoom={2.5}
        defaultViewport={{ x: 0, y: 0, zoom: 0.4 }}
        className="!bg-transparent"
        proOptions={{ hideAttribution: true }}
      >
        <Controls
          className="!bg-slate-800/80 !border-white/10 !rounded-xl !shadow-xl [&>button]:!bg-slate-700/50 [&>button]:!border-white/10 [&>button]:!text-slate-300 [&>button:hover]:!bg-slate-600/50 !left-4 !bottom-4"
          aria-label="Graph controls"
          showInteractive={false}
        />
        <MiniMap
          nodeColor={(node) =>
            node.type === "decision" ? "#22D3EE" : "#64748B"
          }
          maskColor="rgba(15, 23, 42, 0.8)"
          className="!bg-slate-800/80 !border-white/10 !rounded-xl"
          aria-label="Graph minimap"
        />
        <Background
          variant={BackgroundVariant.Dots}
          gap={24}
          size={1}
          color="rgba(148, 163, 184, 0.15)"
        />

        {/* Graph Search */}
        <Panel position="top-center" className="m-4">
          <div className="flex items-center gap-2">
            <div className="relative">
              <Search className="absolute left-2.5 top-1/2 -translate-y-1/2 h-3.5 w-3.5 text-slate-500" />
              <Input
                placeholder="Find node..."
                value={graphSearchQuery}
                onChange={(e) => handleGraphSearch(e.target.value)}
                onKeyDown={(e) => {
                  if (e.key === "Enter") {
                    e.preventDefault()
                    handleGraphSearchNext()
                  }
                  e.stopPropagation()
                }}
                className="h-8 w-52 pl-8 pr-8 text-xs bg-slate-800/90 border-white/10 text-slate-200 placeholder:text-slate-500 focus:border-violet-500/50"
              />
              {graphSearchQuery && (
                <button
                  onClick={() => handleGraphSearch("")}
                  className="absolute right-2 top-1/2 -translate-y-1/2 text-slate-500 hover:text-slate-300"
                  aria-label="Clear search"
                >
                  <X className="h-3 w-3" />
                </button>
              )}
            </div>
            {graphSearchMatchIds.length > 0 && (
              <span className="text-[10px] text-slate-400 bg-slate-800/80 px-2 py-1 rounded">
                {graphSearchIndex + 1}/{graphSearchMatchIds.length}
              </span>
            )}
            <Button
              variant={pathfindingMode ? "default" : "ghost"}
              size="sm"
              onClick={() => {
                if (pathfindingMode) {
                  clearPathfinding()
                } else {
                  setPathfindingMode(true)
                  setSelectedNode(null)
                }
              }}
              className={`h-8 text-xs ${pathfindingMode ? "bg-violet-600 hover:bg-violet-700 text-white" : "text-slate-400 hover:text-slate-200 bg-slate-800/80"}`}
            >
              <Link2 className="h-3.5 w-3.5 mr-1" />
              Path
            </Button>
          </div>
          {pathfindingMode && (
            <div className="mt-2 text-[10px] text-center bg-slate-800/90 border border-violet-500/30 rounded-lg px-3 py-1.5 text-slate-300">
              {!pathStart
                ? "Click a start node"
                : !pathEnd
                ? "Click an end node"
                : `Path: ${pathNodeIds.size} nodes, ${pathEdgeIds.size} edges`}
              {(pathStart || pathEnd) && (
                <button onClick={clearPathfinding} className="ml-2 text-violet-400 hover:text-violet-300 underline">
                  Reset
                </button>
              )}
            </div>
          )}
        </Panel>

        {/* Left Side Panels - Stacked vertically */}
        <Panel position="top-left" className="m-4">
          <div className="flex flex-col gap-3 max-h-[calc(100vh-180px)] overflow-y-auto scrollbar-thin scrollbar-thumb-slate-600 scrollbar-track-transparent">
            {/* Source Filter Panel */}
            {showSourceLegend && (
              <Card className="w-48 bg-slate-800/90 backdrop-blur-xl border-white/10 shrink-0">
                <CardHeader className="py-2 px-3 flex flex-row items-center justify-between cursor-pointer" onClick={() => setSourcesExpanded(!sourcesExpanded)}>
                  <CardTitle className="text-xs text-slate-200 flex items-center gap-2">
                    <Bot className="h-3.5 w-3.5" aria-hidden="true" /> Sources
                  </CardTitle>
                  <div className="flex items-center gap-1">
                    <Button
                      variant="ghost"
                      size="icon"
                      className="h-5 w-5 text-slate-400 hover:text-slate-200"
                      aria-label={sourcesExpanded ? "Collapse" : "Expand"}
                      onClick={(e) => { e.stopPropagation(); setSourcesExpanded(!sourcesExpanded) }}
                    >
                      {sourcesExpanded ? <ChevronUp className="h-3 w-3" /> : <ChevronDown className="h-3 w-3" />}
                    </Button>
                    <Button
                      variant="ghost"
                      size="icon"
                      onClick={(e) => { e.stopPropagation(); setShowSourceLegend(false) }}
                      className="h-5 w-5 text-slate-400 hover:text-slate-200"
                      aria-label="Close source legend"
                    >
                      <X className="h-3 w-3" />
                    </Button>
                  </div>
                </CardHeader>
                {sourcesExpanded && <CardContent className="py-1.5 px-3 space-y-1">
                  {/* All sources button */}
                  <button
                    onClick={() => handleSourceFilterClick(null)}
                    aria-pressed={!sourceFilter}
                    aria-label="Show all decision sources"
                    className={`w-full flex items-center gap-2 px-2 py-1 rounded-md transition-colors text-[11px] ${
                      !sourceFilter
                        ? "bg-white/10 border border-white/20"
                        : "hover:bg-white/5"
                    }`}
                  >
                    <div className="w-3 h-3 rounded bg-gradient-to-br from-slate-600 to-slate-700 border border-white/20" aria-hidden="true" />
                    <span className="text-slate-300 flex-1 text-left">All</span>
                    <Badge className="text-[9px] px-1 py-0 bg-slate-700 text-slate-300 border-slate-600">
                      {Object.values(sourceCounts).reduce((a, b) => a + b, 0)}
                    </Badge>
                  </button>

                  {/* Individual source filters */}
                  {Object.entries(SOURCE_STYLES).map(([key, style]) => {
                    const count = sourceCounts[key] || 0
                    if (count === 0 && key !== "unknown") return null
                    const badgeStyle = SOURCE_BADGE_STYLES[key as keyof typeof SOURCE_BADGE_STYLES] || SOURCE_BADGE_STYLES.unknown
                    return (
                      <button
                        key={key}
                        onClick={() => handleSourceFilterClick(sourceFilter === key ? null : key)}
                        aria-pressed={sourceFilter === key}
                        aria-label={`Filter by ${style.label}`}
                        className={`w-full flex items-center gap-2 px-2 py-1 rounded-md transition-colors text-[11px] ${
                          sourceFilter === key
                            ? "bg-white/10 border border-white/20"
                            : "hover:bg-white/5"
                        }`}
                      >
                        <span className="[&>svg]:h-3 [&>svg]:w-3">{style.icon}</span>
                        <span className="text-slate-300 flex-1 text-left">{style.label}</span>
                        <Badge
                          className="text-[9px] px-1 py-0"
                          style={{
                            backgroundColor: badgeStyle.backgroundColor,
                            color: badgeStyle.color,
                            borderColor: "transparent",
                          }}
                        >
                          {count}
                        </Badge>
                      </button>
                    )
                  })}
                </CardContent>}
              </Card>
            )}

            {/* Part 4.7: Scope Layer Toggle Panel */}
            {showScopePanel && (
              <Card className="w-48 bg-slate-800/90 backdrop-blur-xl border-white/10 shrink-0">
                <CardHeader className="py-2 px-3 flex flex-row items-center justify-between cursor-pointer" onClick={() => setScopeExpanded(!scopeExpanded)}>
                  <CardTitle className="text-xs text-slate-200 flex items-center gap-2">
                    <Layers className="h-3.5 w-3.5" aria-hidden="true" /> Scope Layer
                  </CardTitle>
                  <div className="flex items-center gap-1">
                    <Button
                      variant="ghost"
                      size="icon"
                      className="h-5 w-5 text-slate-400 hover:text-slate-200"
                      aria-label={scopeExpanded ? "Collapse" : "Expand"}
                      onClick={(e) => { e.stopPropagation(); setScopeExpanded(!scopeExpanded) }}
                    >
                      {scopeExpanded ? <ChevronUp className="h-3 w-3" /> : <ChevronDown className="h-3 w-3" />}
                    </Button>
                    <Button
                      variant="ghost"
                      size="icon"
                      onClick={(e) => { e.stopPropagation(); setShowScopePanel(false); setScopeFilter(null) }}
                      className="h-5 w-5 text-slate-400 hover:text-slate-200"
                      aria-label="Close scope filter"
                    >
                      <X className="h-3 w-3" />
                    </Button>
                  </div>
                </CardHeader>
                {scopeExpanded && (
                  <CardContent className="py-1.5 px-3 space-y-1">
                    <p className="text-[9px] text-slate-500 mb-1">Filter by decision half-life</p>
                    {/* All scopes */}
                    <button
                      onClick={() => setScopeFilter(null)}
                      aria-pressed={scopeFilter === null}
                      className={`w-full flex items-center gap-2 px-2 py-1 rounded-md transition-colors text-[11px] ${
                        !scopeFilter ? "bg-white/10 border border-white/20" : "hover:bg-white/5"
                      }`}
                    >
                      <div className="w-2.5 h-2.5 rounded-full bg-slate-400" />
                      <span className="text-slate-300 flex-1 text-left">All scopes</span>
                    </button>
                    {/* Individual scope levels — ordered by half-life (strategic at top) */}
                    {[
                      { scope: "strategic",     color: "#ef4444", label: "Strategic",     halfLife: "2yr" },
                      { scope: "architectural", color: "#f97316", label: "Architectural",  halfLife: "6mo" },
                      { scope: "library",       color: "#eab308", label: "Library",        halfLife: "3mo" },
                      { scope: "config",        color: "#22c55e", label: "Config",         halfLife: "1mo" },
                      { scope: "operational",   color: "#3b82f6", label: "Operational",    halfLife: "2wk" },
                    ].map(({ scope, color, label, halfLife }) => (
                      <button
                        key={scope}
                        onClick={() => setScopeFilter(scopeFilter === scope ? null : scope)}
                        aria-pressed={scopeFilter === scope}
                        aria-label={`Show only ${label} decisions`}
                        className={`w-full flex items-center gap-2 px-2 py-1 rounded-md transition-colors text-[11px] ${
                          scopeFilter === scope ? "bg-white/10 border border-white/20" : "hover:bg-white/5"
                        }`}
                      >
                        <div className="w-2.5 h-2.5 rounded-full flex-shrink-0" style={{ backgroundColor: color }} />
                        <span className="text-slate-300 flex-1 text-left">{label}</span>
                        <span className="text-slate-500 text-[9px]">{halfLife}</span>
                      </button>
                    ))}
                  </CardContent>
                )}
              </Card>
            )}

            {/* Project Filter Panel */}
            {showProjectFilter && (
              <Card className="w-48 bg-slate-800/90 backdrop-blur-xl border-white/10 shrink-0">
                <CardHeader className="py-2 px-3 flex flex-row items-center justify-between cursor-pointer" onClick={() => setProjectsExpanded(!projectsExpanded)}>
                  <CardTitle className="text-xs text-slate-200 flex items-center gap-2">
                    <FolderOpen className="h-3.5 w-3.5" aria-hidden="true" /> Projects
                  </CardTitle>
                  <div className="flex items-center gap-1">
                    <Button
                      variant="ghost"
                      size="icon"
                      className="h-5 w-5 text-slate-400 hover:text-slate-200"
                      aria-label={projectsExpanded ? "Collapse" : "Expand"}
                      onClick={(e) => { e.stopPropagation(); setProjectsExpanded(!projectsExpanded) }}
                    >
                      {projectsExpanded ? <ChevronUp className="h-3 w-3" /> : <ChevronDown className="h-3 w-3" />}
                    </Button>
                    <Button
                      variant="ghost"
                      size="icon"
                      onClick={(e) => { e.stopPropagation(); setShowProjectFilter(false) }}
                      className="h-5 w-5 text-slate-400 hover:text-slate-200"
                      aria-label="Close project filter"
                    >
                      <X className="h-3 w-3" />
                    </Button>
                  </div>
                </CardHeader>
                {projectsExpanded && <CardContent className="py-1.5 px-3 space-y-1">
                  {/* All Projects button */}
                  <button
                    onClick={() => onProjectFilterChange?.(null)}
                    className={`w-full text-left px-2 py-1 rounded-md transition-all text-[11px] flex items-center justify-between ${
                      projectFilter === null
                        ? "bg-cyan-500/20 text-cyan-300 border border-cyan-500/30"
                        : "bg-white/5 text-slate-300 hover:bg-white/10 border border-transparent"
                    }`}
                    aria-pressed={projectFilter === null}
                    aria-label="Show all projects"
                  >
                    <span>All Projects</span>
                    <Badge
                      variant="secondary"
                      className={`text-[9px] px-1 py-0 ${projectFilter === null ? "bg-cyan-500/30 text-cyan-200" : "bg-slate-700 text-slate-300"}`}
                    >
                      {Object.values(projectCounts).reduce((sum, count) => sum + count, 0)}
                    </Badge>
                  </button>

                  {/* Individual project buttons - limited to prevent overflow */}
                  <div className="max-h-[120px] overflow-y-auto space-y-1 scrollbar-thin scrollbar-thumb-slate-600">
                    {Object.entries(projectCounts)
                      .filter(([name]) => name !== "unassigned" || projectCounts[name] > 0)
                      .sort(([, a], [, b]) => b - a)
                      .map(([project, count]) => (
                        <button
                          key={project}
                          onClick={() => onProjectFilterChange?.(projectFilter === project ? null : project)}
                          className={`w-full text-left px-2 py-1 rounded-md transition-all text-[11px] flex items-center justify-between ${
                            projectFilter === project
                              ? "bg-cyan-500/20 text-cyan-300 border border-cyan-500/30"
                              : "bg-white/5 text-slate-300 hover:bg-white/10 border border-transparent"
                          }`}
                          aria-pressed={projectFilter === project}
                          aria-label={`Filter by project: ${project}`}
                        >
                          <span className="truncate max-w-[100px]">{project}</span>
                          <Badge
                            variant="secondary"
                            className={`text-[9px] px-1 py-0 shrink-0 ${
                              projectFilter === project ? "bg-cyan-500/30 text-cyan-200" : "bg-slate-700 text-slate-300"
                            }`}
                          >
                            {count}
                          </Badge>
                        </button>
                      ))}
                  </div>
                </CardContent>}
              </Card>
            )}

            {/* Entity Types Legend */}
            <Card className="w-48 bg-slate-800/90 backdrop-blur-xl border-white/10 shrink-0" role="region" aria-label="Entity types legend">
              <CardHeader className="py-2 px-3 cursor-pointer" onClick={() => setEntityTypesExpanded(!entityTypesExpanded)}>
                <CardTitle className="text-xs text-slate-200 flex items-center justify-between">
                  <span className="flex items-center gap-2">
                    <BarChart3 className="h-3.5 w-3.5" aria-hidden="true" /> Entity Types
                  </span>
                  {entityTypesExpanded ? <ChevronUp className="h-3 w-3 text-slate-400" /> : <ChevronDown className="h-3 w-3 text-slate-400" />}
                </CardTitle>
              </CardHeader>
              {entityTypesExpanded && <CardContent className="py-1.5 px-3 space-y-1.5">
                <div className="flex items-center gap-2">
                  <div className="w-4 h-4 rounded-full bg-blue-500/20 border border-blue-400 flex items-center justify-center" aria-hidden="true">
                    <Atom className="h-2.5 w-2.5 text-blue-400" />
                  </div>
                  <span className="text-[11px] text-slate-300">Concept</span>
                </div>
                <div className="flex items-center gap-2">
                  <div className="w-4 h-4 rounded-full bg-green-500/20 border border-green-400 flex items-center justify-center" aria-hidden="true">
                    <Server className="h-2.5 w-2.5 text-green-400" />
                  </div>
                  <span className="text-[11px] text-slate-300">System</span>
                </div>
                <div className="flex items-center gap-2">
                  <div className="w-4 h-4 rounded-full bg-orange-500/20 border border-orange-400 flex items-center justify-center" aria-hidden="true">
                    <Code className="h-2.5 w-2.5 text-orange-400" />
                  </div>
                  <span className="text-[11px] text-slate-300">Technology</span>
                </div>
                <div className="flex items-center gap-2">
                  <div className="w-4 h-4 rounded-full bg-purple-500/20 border border-purple-400 flex items-center justify-center" aria-hidden="true">
                    <User className="h-2.5 w-2.5 text-purple-400" />
                  </div>
                  <span className="text-[11px] text-slate-300">Person</span>
                </div>
                <div className="flex items-center gap-2">
                  <div className="w-4 h-4 rounded-full bg-pink-500/20 border border-pink-400 flex items-center justify-center" aria-hidden="true">
                    <Target className="h-2.5 w-2.5 text-pink-400" />
                  </div>
                  <span className="text-[11px] text-slate-300">Pattern</span>
                </div>
                <div className="flex items-center gap-2 pt-1 border-t border-white/10 mt-1">
                  <Sparkles className="h-3.5 w-3.5 text-purple-400" aria-hidden="true" />
                  <span className="text-[10px] text-slate-400">= Has embedding</span>
                </div>
              </CardContent>}
            </Card>
          </div>
        </Panel>

        {/* Relationship Legend */}
        {showRelationshipLegend && (
          <Panel position="top-right" className="m-4">
            <Card className="w-44 bg-slate-800/90 backdrop-blur-xl border-white/10" role="region" aria-label="Relationship types legend">
              <CardHeader className="py-2 px-3 flex flex-row items-center justify-between cursor-pointer" onClick={() => setRelationshipsExpanded(!relationshipsExpanded)}>
                <CardTitle className="text-xs text-slate-200 flex items-center gap-2">
                  <GitBranch className="h-3.5 w-3.5" aria-hidden="true" /> Relationships
                </CardTitle>
                <div className="flex items-center gap-1">
                  <Button
                    variant="ghost"
                    size="icon"
                    className="h-5 w-5 text-slate-400 hover:text-slate-200"
                    aria-label={relationshipsExpanded ? "Collapse" : "Expand"}
                    onClick={(e) => { e.stopPropagation(); setRelationshipsExpanded(!relationshipsExpanded) }}
                  >
                    {relationshipsExpanded ? <ChevronUp className="h-3 w-3" /> : <ChevronDown className="h-3 w-3" />}
                  </Button>
                  <Button
                    variant="ghost"
                    size="icon"
                    onClick={(e) => { e.stopPropagation(); setShowRelationshipLegend(false) }}
                    className="h-5 w-5 text-slate-400 hover:text-slate-200"
                    aria-label="Close relationship legend"
                  >
                    <X className="h-3 w-3" />
                  </Button>
                </div>
              </CardHeader>
              {relationshipsExpanded && <CardContent className="py-1.5 px-3 space-y-1">
                {Object.entries(RELATIONSHIP_STYLES).map(([key, style]) => {
                  const count = relationshipCounts[key] || 0
                  if (count === 0 && key !== "INVOLVES") return null
                  return (
                    <div key={key} className="flex items-center gap-1.5 text-[11px]">
                      <div
                        className="w-4 h-0.5 rounded shrink-0"
                        style={{
                          backgroundColor: style.color,
                          opacity: count > 0 ? 1 : 0.3,
                        }}
                        aria-hidden="true"
                      />
                      <span className="text-slate-300 flex-1 flex items-center gap-1">
                        <span className="[&>svg]:h-2.5 [&>svg]:w-2.5">{style.icon}</span>
                        {style.label}
                      </span>
                      {count > 0 && (
                        <Badge
                          className="text-[9px] px-1 py-0"
                          style={{
                            backgroundColor: `${style.color}20`,
                            color: style.color,
                            borderColor: `${style.color}40`,
                          }}
                        >
                          {count}
                        </Badge>
                      )}
                    </div>
                  )
                })}
              </CardContent>}
            </Card>
          </Panel>
        )}


        {/* Layout Selector */}
        <Panel position="bottom-center" className="m-4">
          <DropdownMenu>
            <DropdownMenuTrigger asChild>
              <Button
                variant="outline"
                size="sm"
                className="bg-slate-800/90 border-white/10 text-slate-300 hover:bg-slate-700/90 hover:text-slate-100"
              >
                <Layout className="h-4 w-4 mr-2" />
                {LAYOUT_INFO[layoutType].label}
                <ChevronDown className="h-4 w-4 ml-2" />
              </Button>
            </DropdownMenuTrigger>
            <DropdownMenuContent className="bg-slate-800 border-white/10">
              <DropdownMenuItem
                onClick={() => setLayoutType("force")}
                className={`cursor-pointer ${layoutType === "force" ? "bg-cyan-500/20 text-cyan-300" : "text-slate-300 hover:text-slate-100"}`}
              >
                <Network className="h-4 w-4 mr-2" />
                <div className="flex flex-col">
                  <span>Force-Directed</span>
                  <span className="text-xs text-slate-500">Physics-based clustering</span>
                </div>
              </DropdownMenuItem>
              <DropdownMenuItem
                onClick={() => setLayoutType("clustered")}
                className={`cursor-pointer ${layoutType === "clustered" ? "bg-cyan-500/20 text-cyan-300" : "text-slate-300 hover:text-slate-100"}`}
              >
                <Layers className="h-4 w-4 mr-2" />
                <div className="flex flex-col">
                  <span>Clustered</span>
                  <span className="text-xs text-slate-500">Group by decision</span>
                </div>
              </DropdownMenuItem>
              <DropdownMenuItem
                onClick={() => setLayoutType("hierarchical")}
                className={`cursor-pointer ${layoutType === "hierarchical" ? "bg-cyan-500/20 text-cyan-300" : "text-slate-300 hover:text-slate-100"}`}
              >
                <GitBranch className="h-4 w-4 mr-2" />
                <div className="flex flex-col">
                  <span>Hierarchical</span>
                  <span className="text-xs text-slate-500">Tree-like structure</span>
                </div>
              </DropdownMenuItem>
              <DropdownMenuItem
                onClick={() => setLayoutType("radial")}
                className={`cursor-pointer ${layoutType === "radial" ? "bg-cyan-500/20 text-cyan-300" : "text-slate-300 hover:text-slate-100"}`}
              >
                <Target className="h-4 w-4 mr-2" />
                <div className="flex flex-col">
                  <span>Radial</span>
                  <span className="text-xs text-slate-500">Decisions at center</span>
                </div>
              </DropdownMenuItem>
            </DropdownMenuContent>
          </DropdownMenu>
        </Panel>

        {/* Stats Panel */}
        <Panel position="bottom-right" className="m-4">
          <div className="px-3 py-2 rounded-lg bg-slate-800/80 backdrop-blur-xl border border-white/10 text-xs text-slate-400 flex gap-4">
            <span className="flex items-center gap-1.5">
              <CircleDot className="h-3 w-3" aria-hidden="true" />
              {data?.nodes?.length || 0} nodes
            </span>
            <span className="flex items-center gap-1.5">
              <Link2 className="h-3 w-3" aria-hidden="true" />
              {data?.edges?.length || 0} edges
            </span>
          </div>
        </Panel>
      </ReactFlow>

      {/* Detail Panel - responsive width and dynamic positioning */}
      {selectedNode && (
        <div className={`absolute right-4 w-80 max-w-[90vw] z-10 ${showRelationshipLegend ? "top-[260px]" : "top-4"}`}>
          <Card className="bg-slate-800/95 backdrop-blur-xl border-white/10 shadow-2xl">
            <CardHeader className="flex flex-row items-center justify-between py-3 border-b border-white/10">
              <CardTitle className="text-base text-slate-100 flex items-center gap-2">
                {selectedNode.type === "decision" ? (
                  <Lightbulb className="h-4 w-4 text-cyan-400" aria-hidden="true" />
                ) : (
                  <Atom className="h-4 w-4 text-blue-400" aria-hidden="true" />
                )}
                {selectedNode.type === "decision" ? "Decision" : "Entity"} Details
              </CardTitle>
              <div className="flex items-center gap-1">
                {selectedNode.type === "decision" && onDeleteDecision && (
                  <TooltipProvider>
                    <Tooltip>
                      <TooltipTrigger asChild>
                        <Button
                          variant="ghost"
                          size="icon"
                          onClick={() => {
                            const decisionData = selectedNode.data as { decision?: Decision }
                            if (decisionData.decision) {
                              handleDeleteClick(decisionData.decision.id, decisionData.decision.trigger)
                            }
                          }}
                          className="h-8 w-8 text-slate-400 hover:text-red-400 hover:bg-red-500/10"
                          aria-label="Delete decision"
                        >
                          <Trash2 className="h-4 w-4" />
                        </Button>
                      </TooltipTrigger>
                      <TooltipContent>Delete this decision</TooltipContent>
                    </Tooltip>
                  </TooltipProvider>
                )}
                <TooltipProvider>
                  <Tooltip>
                    <TooltipTrigger asChild>
                      <Button
                        variant="ghost"
                        size="icon"
                        onClick={closeDetailPanel}
                        className="h-8 w-8 text-slate-400 hover:text-slate-200 hover:bg-white/10"
                        aria-label="Close details panel"
                      >
                        <X className="h-4 w-4" />
                      </Button>
                    </TooltipTrigger>
                    <TooltipContent>Close panel</TooltipContent>
                  </Tooltip>
                </TooltipProvider>
              </div>
            </CardHeader>
            <CardContent className="pt-4">
              <ScrollArea className="h-[320px] max-h-[50vh] pr-2">
                {selectedNode.type === "decision" && (() => {
                  const decisionData = selectedNode.data as { decision?: Decision; hasEmbedding?: boolean }
                  if (!decisionData.decision) return null
                  const decision = decisionData.decision
                  return (
                    <div className="space-y-4">
                      {decisionData.hasEmbedding && (
                        <div className="flex items-center gap-2 text-xs text-purple-400 bg-purple-500/10 rounded-lg px-3 py-2">
                          <Sparkles className="h-3 w-3" aria-hidden="true" />
                          <span>Semantic search enabled</span>
                        </div>
                      )}
                      <div>
                        <h4 className="text-xs font-medium text-cyan-400 uppercase tracking-wider mb-1">
                          Trigger
                        </h4>
                        <p className="text-sm text-slate-200">{decision.trigger}</p>
                      </div>
                      <div>
                        <h4 className="text-xs font-medium text-cyan-400 uppercase tracking-wider mb-1">
                          Context
                        </h4>
                        <p className="text-sm text-slate-300">{decision.context}</p>
                      </div>
                      <div>
                        <h4 className="text-xs font-medium text-cyan-400 uppercase tracking-wider mb-1">
                          Decision
                        </h4>
                        <p className="text-sm text-slate-200 font-medium">{decision.agent_decision}</p>
                      </div>
                      <div>
                        <h4 className="text-xs font-medium text-cyan-400 uppercase tracking-wider mb-1">
                          Rationale
                        </h4>
                        <p className="text-sm text-slate-300">{decision.agent_rationale}</p>
                      </div>
                      <div>
                        <h4 className="text-xs font-medium text-cyan-400 uppercase tracking-wider mb-2">
                          Related Entities
                        </h4>
                        <div className="flex flex-wrap gap-2" role="list" aria-label="Related entities">
                          {(() => {
                            // Find connected entities from graph edges
                            const connectedEntityIds = new Set<string>()
                            data?.edges?.forEach(edge => {
                              if (edge.source === selectedNode.id && edge.relationship === "INVOLVES") {
                                connectedEntityIds.add(edge.target)
                              }
                            })
                            const connectedEntities = data?.nodes?.filter(
                              n => n.type === "entity" && connectedEntityIds.has(n.id)
                            ) || []

                            if (connectedEntities.length === 0) {
                              return <span className="text-sm text-slate-500">No entities linked</span>
                            }

                            return connectedEntities.map((entityNode) => {
                              const entityData = entityNode.data as { name?: string; type?: string }
                              const entityType = (entityData.type || "concept") as keyof typeof ENTITY_TYPE_CONFIG
                              const entityConfig = ENTITY_TYPE_CONFIG[entityType] || ENTITY_TYPE_CONFIG.concept
                              return (
                                <Badge
                                  key={entityNode.id}
                                  className="bg-blue-500/20 text-blue-400 border-blue-500/30 flex items-center gap-1.5 cursor-pointer hover:bg-blue-500/30 transition-colors"
                                  role="listitem"
                                  onClick={() => {
                                    const node = nodes.find(n => n.id === entityNode.id)
                                    if (node) {
                                      setSelectedNode(node)
                                      setFocusedNodeId(node.id)
                                      centerOnNode(node)
                                    }
                                  }}
                                >
                                  <span className="h-3 w-3 flex items-center justify-center [&>svg]:h-3 [&>svg]:w-3">
                                    {entityConfig.icon}
                                  </span>
                                  {entityData.name || entityNode.label}
                                </Badge>
                              )
                            })
                          })()}
                        </div>
                      </div>
                      {/* P1-3: Related Decisions Sidebar */}
                      <div className="pt-3 border-t border-white/10">
                        <h4 className="text-xs font-medium text-cyan-400 uppercase tracking-wider mb-2 flex items-center gap-2">
                          <Link2 className="h-3 w-3" />
                          Related Decisions
                        </h4>
                        {relatedLoading ? (
                          <div className="flex items-center justify-center py-4">
                            <Loader2 className="h-5 w-5 text-slate-400 animate-spin" />
                            <span className="ml-2 text-xs text-slate-400">Finding similar decisions...</span>
                          </div>
                        ) : relatedDecisions.length > 0 ? (
                          <div className="space-y-2" role="list" aria-label="Related decisions">
                            {relatedDecisions.map((related) => (
                              <button
                                key={related.id}
                                onClick={() => {
                                  // Find and select the related decision node
                                  const relatedNode = nodes.find((n) => n.id === related.id)
                                  if (relatedNode) {
                                    setSelectedNode(relatedNode)
                                    setFocusedNodeId(relatedNode.id)
                                    centerOnNode(relatedNode)
                                  }
                                }}
                                className="w-full text-left p-2 rounded-lg bg-slate-700/50 hover:bg-slate-700 transition-colors group"
                                role="listitem"
                              >
                                <div className="flex items-start justify-between gap-2">
                                  <p className="text-xs text-slate-200 line-clamp-2 group-hover:text-white">
                                    {related.trigger}
                                  </p>
                                  <Badge
                                    className="shrink-0 text-[9px] px-1.5 py-0"
                                    style={{
                                      backgroundColor: `rgba(168,85,247,${0.1 + related.similarity * 0.3})`,
                                      color: "#c084fc",
                                      borderColor: "rgba(168,85,247,0.3)",
                                    }}
                                  >
                                    {(related.similarity * 100).toFixed(0)}%
                                  </Badge>
                                </div>
                                {related.shared_entities.length > 0 && (
                                  <div className="flex flex-wrap gap-1 mt-1.5">
                                    {related.shared_entities.slice(0, 3).map((entity) => (
                                      <span
                                        key={entity}
                                        className="text-[10px] text-slate-400 bg-slate-800 px-1.5 py-0.5 rounded"
                                      >
                                        {entity}
                                      </span>
                                    ))}
                                    {related.shared_entities.length > 3 && (
                                      <span className="text-[10px] text-slate-500">
                                        +{related.shared_entities.length - 3} more
                                      </span>
                                    )}
                                  </div>
                                )}
                              </button>
                            ))}
                          </div>
                        ) : (
                          <p className="text-xs text-slate-500 py-2">
                            No similar decisions found
                          </p>
                        )}
                      </div>
                    </div>
                  )
                })()}
                {selectedNode.type === "entity" && (() => {
                  const entityData = selectedNode.data as { entity?: Entity; hasEmbedding?: boolean }
                  if (!entityData.entity) return null
                  const entity = entityData.entity
                  return (
                    <div className="space-y-4">
                      {entityData.hasEmbedding && (
                        <div className="flex items-center gap-2 text-xs text-purple-400 bg-purple-500/10 rounded-lg px-3 py-2">
                          <Sparkles className="h-3 w-3" aria-hidden="true" />
                          <span>Semantic search enabled</span>
                        </div>
                      )}
                      <div>
                        <h4 className="text-xs font-medium text-cyan-400 uppercase tracking-wider mb-1">
                          Name
                        </h4>
                        <p className="text-lg font-semibold text-slate-100">{entity.name}</p>
                      </div>
                      <div>
                        <h4 className="text-xs font-medium text-cyan-400 uppercase tracking-wider mb-1">
                          Type
                        </h4>
                        <Badge className="bg-slate-700 text-slate-200 border-slate-600 capitalize">
                          {entity.type}
                        </Badge>
                      </div>
                    </div>
                  )
                })()}
              </ScrollArea>
            </CardContent>
          </Card>
        </div>
      )}

      {/* Delete Confirmation Dialog */}
      <DeleteConfirmDialog
        open={!!deleteTarget}
        onOpenChange={(open) => !open && setDeleteTarget(null)}
        itemType="Decision"
        itemName={deleteTarget?.name}
        onConfirm={handleDeleteConfirm}
      />
    </div>
  )
}

// Wrapper component with ReactFlowProvider (P0-3: Keyboard navigation requires useReactFlow hook)
export function KnowledgeGraph(props: KnowledgeGraphProps) {
  return (
    <ReactFlowProvider>
      <KnowledgeGraphInner {...props} />
    </ReactFlowProvider>
  )
}
