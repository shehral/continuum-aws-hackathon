"use client"

import { useEffect, useRef, useState, useMemo } from "react"

// ---- Graph data ----

interface NodeDef {
  id: number
  label: string
  type: "decision" | "entity"
  subtype: "technology" | "concept" | "pattern"
  x: number
  y: number
}

interface EdgeDef {
  from: number
  to: number
}

const NODES: NodeDef[] = [
  { id: 1, label: "Use Bedrock",     type: "decision", subtype: "technology", x: 200, y: 60 },
  { id: 2, label: "Add Datadog",     type: "decision", subtype: "technology", x: 100, y: 200 },
  { id: 3, label: "Neo4j",           type: "entity",   subtype: "technology", x: 320, y: 140 },
  { id: 4, label: "Agent Memory",    type: "entity",   subtype: "concept",    x: 60,  y: 90 },
  { id: 5, label: "Strands SDK",     type: "entity",   subtype: "pattern",    x: 280, y: 260 },
  { id: 6, label: "Claude Sonnet",   type: "entity",   subtype: "technology", x: 180, y: 320 },
]

const EDGES: EdgeDef[] = [
  { from: 1, to: 3 },
  { from: 1, to: 4 },
  { from: 2, to: 4 },
  { from: 2, to: 5 },
  { from: 3, to: 6 },
  { from: 5, to: 6 },
]

// ---- Color palette ----

function nodeStroke(n: NodeDef): { fill: string; stroke: string; strokeHighlight: string } {
  if (n.type === "decision") {
    return {
      fill: "rgba(139,92,246,0.08)",
      stroke: "rgba(139,92,246,0.4)",
      strokeHighlight: "rgba(139,92,246,1)",
    }
  }
  switch (n.subtype) {
    case "technology":
      return {
        fill: "rgba(249,115,22,0.10)",
        stroke: "rgba(249,115,22,0.4)",
        strokeHighlight: "rgba(249,115,22,1)",
      }
    case "concept":
      return {
        fill: "rgba(139,92,246,0.08)",
        stroke: "rgba(139,92,246,0.4)",
        strokeHighlight: "rgba(139,92,246,1)",
      }
    case "pattern":
      return {
        fill: "rgba(236,72,153,0.10)",
        stroke: "rgba(236,72,153,0.4)",
        strokeHighlight: "rgba(236,72,153,1)",
      }
    default:
      return {
        fill: "rgba(139,92,246,0.08)",
        stroke: "rgba(139,92,246,0.4)",
        strokeHighlight: "rgba(139,92,246,1)",
      }
  }
}

// ---- Helpers ----

function nodeById(id: number): NodeDef {
  return NODES.find((n) => n.id === id)!
}

/** Edges connected to a given node id */
function connectedEdgeIndices(nodeId: number): number[] {
  return EDGES.reduce<number[]>((acc, e, i) => {
    if (e.from === nodeId || e.to === nodeId) acc.push(i)
    return acc
  }, [])
}

/** Compute the length of a line between two nodes (for strokeDasharray) */
function edgeLength(e: EdgeDef): number {
  const a = nodeById(e.from)
  const b = nodeById(e.to)
  return Math.sqrt((b.x - a.x) ** 2 + (b.y - a.y) ** 2)
}

// ---- Component ----

export function PulsingNetwork({ isVisible }: { isVisible: boolean }) {
  const [entryDone, setEntryDone] = useState(false)
  const [highlightIdx, setHighlightIdx] = useState(-1)
  const [prefersReduced, setPrefersReduced] = useState(false)
  const intervalRef = useRef<ReturnType<typeof setInterval> | null>(null)

  // Detect prefers-reduced-motion once on mount
  useEffect(() => {
    if (typeof window !== "undefined") {
      setPrefersReduced(
        window.matchMedia("(prefers-reduced-motion: reduce)").matches
      )
    }
  }, [])

  // If reduced motion, show everything immediately when visible
  const skipAnimation = prefersReduced

  // Entry animation completion timer
  useEffect(() => {
    if (!isVisible) {
      setEntryDone(false)
      setHighlightIdx(-1)
      return
    }

    if (skipAnimation) {
      setEntryDone(true)
      return
    }

    // Total entry time: nodes (6 * 100ms stagger + 400ms anim) + edges (~600ms after)
    // ~1600ms total
    const timer = setTimeout(() => {
      setEntryDone(true)
    }, 1600)

    return () => clearTimeout(timer)
  }, [isVisible, skipAnimation])

  // Highlight cycling after entry completes
  useEffect(() => {
    if (!entryDone || skipAnimation) return

    // Start cycling immediately with first node
    setHighlightIdx(0)

    intervalRef.current = setInterval(() => {
      setHighlightIdx((prev) => (prev + 1) % NODES.length)
    }, 3000)

    return () => {
      if (intervalRef.current) {
        clearInterval(intervalRef.current)
        intervalRef.current = null
      }
    }
  }, [entryDone, skipAnimation])

  // Clean up interval on unmount
  useEffect(() => {
    return () => {
      if (intervalRef.current) {
        clearInterval(intervalRef.current)
        intervalRef.current = null
      }
    }
  }, [])

  // Pre-compute highlighted node id and connected edge indices
  const highlightedNodeId = entryDone && highlightIdx >= 0 ? NODES[highlightIdx].id : -1
  const highlightedEdgeSet = useMemo(() => {
    if (highlightedNodeId < 0) return new Set<number>()
    return new Set(connectedEdgeIndices(highlightedNodeId))
  }, [highlightedNodeId])

  // Pre-compute edge lengths for dash animation
  const edgeLengths = useMemo(() => EDGES.map(edgeLength), [])

  return (
    <svg
      viewBox="0 0 400 380"
      fill="none"
      xmlns="http://www.w3.org/2000/svg"
      className="w-full h-auto"
      role="img"
      aria-label="Animated knowledge graph showing connections between decisions and entities"
    >
      {/* ---- Edges ---- */}
      {EDGES.map((edge, i) => {
        const from = nodeById(edge.from)
        const to = nodeById(edge.to)
        const isHighlighted = highlightedEdgeSet.has(i)
        const len = edgeLengths[i]

        // Entry animation delay: edges start after nodes finish (~1000ms), stagger by 80ms each
        const edgeDelay = skipAnimation ? 0 : 1000 + i * 80

        const showEdge = skipAnimation || isVisible

        return (
          <line
            key={`edge-${i}`}
            x1={from.x}
            y1={from.y}
            x2={to.x}
            y2={to.y}
            stroke={isHighlighted ? "rgba(139,92,246,0.6)" : "rgba(139,92,246,0.2)"}
            strokeWidth={isHighlighted ? 1.5 : 1}
            strokeDasharray={skipAnimation ? "none" : `${len}`}
            strokeDashoffset={showEdge && entryDone ? 0 : skipAnimation ? 0 : len}
            style={{
              transition: skipAnimation
                ? "none"
                : entryDone
                  ? "stroke 0.3s ease, stroke-width 0.3s ease"
                  : `stroke-dashoffset 0.5s ease ${edgeDelay}ms, stroke 0.3s ease, stroke-width 0.3s ease`,
              opacity: showEdge ? 1 : 0,
            }}
          />
        )
      })}

      {/* ---- Nodes ---- */}
      {NODES.map((node, i) => {
        const colors = nodeStroke(node)
        const isHighlighted = node.id === highlightedNodeId
        const nodeDelay = skipAnimation ? 0 : i * 100

        // Decide on visibility/scale
        const show = skipAnimation || isVisible

        if (node.type === "decision") {
          // Decision node: rounded rect, 120x32, rx=10
          const w = 120
          const h = 32
          const rx = 10

          return (
            <g
              key={`node-${node.id}`}
              style={{
                transform: show
                  ? "scale(1)"
                  : "scale(0)",
                transformOrigin: `${node.x}px ${node.y}px`,
                transition: skipAnimation
                  ? "none"
                  : `transform 0.4s cubic-bezier(0.34, 1.56, 0.64, 1) ${nodeDelay}ms`,
              }}
            >
              <rect
                x={node.x - w / 2}
                y={node.y - h / 2}
                width={w}
                height={h}
                rx={rx}
                fill={colors.fill}
                stroke={isHighlighted ? colors.strokeHighlight : colors.stroke}
                strokeWidth={isHighlighted ? 2.5 : 1}
                style={{
                  opacity: isHighlighted ? 1 : 0.8,
                  transition: skipAnimation
                    ? "none"
                    : "stroke 0.3s ease, stroke-width 0.3s ease, opacity 0.3s ease",
                }}
              />
              <text
                x={node.x}
                y={node.y}
                textAnchor="middle"
                dominantBaseline="central"
                fontSize={10}
                className="text-foreground"
                fill="currentColor"
                opacity={isHighlighted ? 0.95 : 0.7}
                style={{
                  transition: skipAnimation ? "none" : "opacity 0.3s ease",
                  pointerEvents: "none",
                  fontFamily: "var(--font-sans), system-ui, sans-serif",
                }}
              >
                {node.label}
              </text>
            </g>
          )
        }

        // Entity node: pill shape, auto-width based on label, rx=14
        const textLen = node.label.length * 6.5 + 24
        const pillW = Math.max(textLen, 60)
        const pillH = 28
        const pillRx = 14

        return (
          <g
            key={`node-${node.id}`}
            style={{
              transform: show
                ? "scale(1)"
                : "scale(0)",
              transformOrigin: `${node.x}px ${node.y}px`,
              transition: skipAnimation
                ? "none"
                : `transform 0.4s cubic-bezier(0.34, 1.56, 0.64, 1) ${nodeDelay}ms`,
            }}
          >
            <rect
              x={node.x - pillW / 2}
              y={node.y - pillH / 2}
              width={pillW}
              height={pillH}
              rx={pillRx}
              fill={colors.fill}
              stroke={isHighlighted ? colors.strokeHighlight : colors.stroke}
              strokeWidth={isHighlighted ? 2.5 : 1}
              style={{
                opacity: isHighlighted ? 1 : 0.8,
                transition: skipAnimation
                  ? "none"
                  : "stroke 0.3s ease, stroke-width 0.3s ease, opacity 0.3s ease",
              }}
            />
            <text
              x={node.x}
              y={node.y}
              textAnchor="middle"
              dominantBaseline="central"
              fontSize={10}
              className="text-foreground"
              fill="currentColor"
              opacity={isHighlighted ? 0.95 : 0.7}
              style={{
                transition: skipAnimation ? "none" : "opacity 0.3s ease",
                pointerEvents: "none",
                fontFamily: "var(--font-sans), system-ui, sans-serif",
              }}
            >
              {node.label}
            </text>
          </g>
        )
      })}
    </svg>
  )
}
