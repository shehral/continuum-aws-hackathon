"use client";

import { useState, useEffect } from "react";

// ── Node & Edge data ────────────────────────────────────────────────

interface GraphNode {
  id: number;
  kind: "decision" | "entity";
  label: string;
  /** Entity sub-type for colour mapping */
  entityType?: "technology" | "pattern" | "concept";
  x: number;
  y: number;
  /** Width; decisions use a fixed width, entities are sized to content */
  w: number;
  h: number;
  /** Animation phase (1-4) */
  phase: number;
  /** Stagger delay within the phase (seconds) */
  stagger: number;
}

interface GraphEdge {
  source: number;
  target: number;
  label?: string;
  /** If true the edge renders dashed in rose */
  dashed?: boolean;
  phase: number;
  stagger: number;
}

const NODES: GraphNode[] = [
  // ── Decisions ──
  { id: 0, kind: "decision", label: "Use PostgreSQL for relational data", x: 150, y: 180, w: 200, h: 44, phase: 1, stagger: 0 },
  { id: 1, kind: "decision", label: "Switch to async ORM", x: 500, y: 120, w: 200, h: 44, phase: 3, stagger: 0 },
  { id: 2, kind: "decision", label: "Add Redis caching layer", x: 620, y: 320, w: 200, h: 44, phase: 4, stagger: 0 },
  // ── Entities ──
  { id: 3, kind: "entity", entityType: "technology", label: "PostgreSQL", x: 80, y: 320, w: 100, h: 30, phase: 2, stagger: 0 },
  { id: 4, kind: "entity", entityType: "technology", label: "SQLAlchemy", x: 330, y: 300, w: 104, h: 30, phase: 2, stagger: 0.3 },
  { id: 5, kind: "entity", entityType: "technology", label: "Redis", x: 720, y: 220, w: 72, h: 30, phase: 4, stagger: 0.3 },
  { id: 6, kind: "entity", entityType: "pattern", label: "Async Pattern", x: 500, y: 380, w: 112, h: 30, phase: 3, stagger: 0.5 },
  { id: 7, kind: "entity", entityType: "concept", label: "Performance", x: 680, y: 420, w: 108, h: 30, phase: 4, stagger: 0.6 },
];

const EDGES: GraphEdge[] = [
  { source: 0, target: 3, label: "INVOLVES", phase: 2, stagger: 0.2 },
  { source: 0, target: 4, label: "INVOLVES", phase: 2, stagger: 0.5 },
  { source: 1, target: 4, label: "INVOLVES", phase: 3, stagger: 0.2 },
  { source: 1, target: 6, label: "INVOLVES", phase: 3, stagger: 0.4 },
  { source: 1, target: 0, label: "SUPERSEDES", dashed: true, phase: 3, stagger: 0.6 },
  { source: 2, target: 5, label: "INVOLVES", phase: 4, stagger: 0.2 },
  { source: 2, target: 7, label: "INVOLVES", phase: 4, stagger: 0.5 },
  { source: 4, target: 6, label: "DEPENDS_ON", phase: 3, stagger: 0.7 },
];

// ── Colour helpers ──────────────────────────────────────────────────

function entityFill(type?: string): string {
  switch (type) {
    case "technology": return "rgba(251,146,60,0.12)";
    case "pattern":    return "rgba(236,72,153,0.12)";
    case "concept":    return "rgba(139,92,246,0.12)";
    default:           return "rgba(139,92,246,0.08)";
  }
}

function entityStroke(type?: string): string {
  switch (type) {
    case "technology": return "rgba(251,146,60,0.3)";
    case "pattern":    return "rgba(236,72,153,0.3)";
    case "concept":    return "rgba(139,92,246,0.3)";
    default:           return "rgba(139,92,246,0.4)";
  }
}

function nodeAccentColor(node: GraphNode): string {
  if (node.kind === "decision") return "rgba(139,92,246,0.8)";
  switch (node.entityType) {
    case "technology": return "rgba(251,146,60,0.8)";
    case "pattern":    return "rgba(236,72,153,0.8)";
    case "concept":    return "rgba(139,92,246,0.8)";
    default:           return "rgba(139,92,246,0.8)";
  }
}

// ── Phase timing ────────────────────────────────────────────────────

function phaseStart(phase: number): number {
  switch (phase) {
    case 1: return 0;
    case 2: return 1.5;
    case 3: return 3.5;
    case 4: return 5.5;
    default: return 0;
  }
}

function nodeDelay(node: GraphNode): number {
  return phaseStart(node.phase) + node.stagger;
}

function edgeDelay(edge: GraphEdge): number {
  return phaseStart(edge.phase) + edge.stagger;
}

// ── Geometry helpers ────────────────────────────────────────────────

function nodeCx(n: GraphNode): number { return n.x + n.w / 2; }
function nodeCy(n: GraphNode): number { return n.y + n.h / 2; }

function edgeLength(x1: number, y1: number, x2: number, y2: number): number {
  return Math.sqrt((x2 - x1) ** 2 + (y2 - y1) ** 2);
}

// ── Deterministic pseudo-random float 0..1 per index ────────────────

function pseudoRandom(index: number): number {
  return ((index * 2654435761) % 97) / 97;
}

// ── Component ───────────────────────────────────────────────────────

export function HeroGraph() {
  const [mounted, setMounted] = useState(false);

  useEffect(() => {
    setMounted(true);
  }, []);

  if (!mounted) {
    return <div className="w-full" style={{ aspectRatio: "800 / 500" }} />;
  }

  return (
    <div className="w-full" style={{ aspectRatio: "800 / 500" }}>
      <svg
        viewBox="0 0 800 500"
        xmlns="http://www.w3.org/2000/svg"
        className="w-full h-full"
        role="img"
        aria-label="Animated knowledge graph showing decisions, technologies, and patterns connecting over time"
      >
        {/* ── Global keyframes (defined once) ─────────────────── */}
        <style>{`
          @media (prefers-reduced-motion: no-preference) {
            .hg-node-enter {
              opacity: 0;
              transform: translateY(8px);
              animation: hgNodeIn 0.6s ease-out forwards;
            }
            @keyframes hgNodeIn {
              to { opacity: 1; transform: translateY(0); }
            }

            .hg-edge-enter {
              opacity: 0;
              animation: hgEdgeFadeIn 0.1s ease-out forwards;
            }
            @keyframes hgEdgeFadeIn {
              to { opacity: 1; }
            }

            @keyframes hgDrawLine {
              to { stroke-dashoffset: 0; }
            }

            .hg-edge-label {
              opacity: 0;
              animation: hgLabelIn 0.4s ease-out forwards;
            }
            @keyframes hgLabelIn {
              to { opacity: 0.5; }
            }

            .hg-idle-float {
              animation: hgFloat 4s ease-in-out infinite;
            }
            @keyframes hgFloat {
              0%, 100% { transform: translateY(0); }
              50% { transform: translateY(-3px); }
            }

            .hg-idle-pulse {
              animation: hgPulse 3s ease-in-out infinite;
            }
            @keyframes hgPulse {
              0%, 100% { opacity: 0.3; }
              50% { opacity: 0.5; }
            }
          }

          @media (prefers-reduced-motion: reduce) {
            .hg-node-enter,
            .hg-edge-enter,
            .hg-edge-label,
            .hg-idle-float,
            .hg-idle-pulse {
              animation: none !important;
            }
            .hg-node-enter {
              opacity: 1 !important;
              transform: none !important;
            }
            .hg-edge-enter {
              opacity: 1 !important;
            }
            .hg-edge-enter line {
              stroke-dashoffset: 0 !important;
            }
            .hg-edge-label {
              opacity: 0.5 !important;
            }
            .hg-idle-pulse {
              opacity: 0.4 !important;
            }
          }
        `}</style>

        {/* ── Edge gradient defs ───────────────────────────────── */}
        <defs>
          {EDGES.map((edge, i) => {
            const sNode = NODES[edge.source];
            const tNode = NODES[edge.target];
            return (
              <linearGradient
                key={`eg-${i}`}
                id={`eg-${i}`}
                x1={nodeCx(sNode)}
                y1={nodeCy(sNode)}
                x2={nodeCx(tNode)}
                y2={nodeCy(tNode)}
                gradientUnits="userSpaceOnUse"
              >
                <stop offset="0%" stopColor={nodeAccentColor(sNode)} />
                <stop offset="100%" stopColor={nodeAccentColor(tNode)} />
              </linearGradient>
            );
          })}
        </defs>

        {/* ── Edges ────────────────────────────────────────────── */}
        {EDGES.map((edge, i) => {
          const sNode = NODES[edge.source];
          const tNode = NODES[edge.target];
          const sx = nodeCx(sNode);
          const sy = nodeCy(sNode);
          const tx = nodeCx(tNode);
          const ty = nodeCy(tNode);
          const len = edgeLength(sx, sy, tx, ty);
          const delay = edgeDelay(edge);
          const drawDuration = 0.6;

          const isSupersedesEdge = edge.dashed === true;
          const strokeRef = isSupersedesEdge
            ? "rgba(236,72,153,0.5)"
            : `url(#eg-${i})`;

          // For dashed edges, use dash pattern for visual style but still
          // animate via a longer dasharray trick: total = dash+gap repeated
          // enough to cover the line, then offset the full length.
          const dashArray = isSupersedesEdge
            ? `6 3`
            : `${len}`;

          // For the SUPERSEDES dashed edge, we animate by offsetting
          // the total pattern length. The total number of (6+3)=9px segments
          // to cover `len` is Math.ceil(len/9)*9.
          const dashedTotalLen = Math.ceil(len / 9) * 9;

          const mx = (sx + tx) / 2;
          const my = (sy + ty) / 2;

          return (
            <g key={`edge-${i}`}>
              {/* Draw-in line */}
              <g
                className="hg-edge-enter"
                style={{ animationDelay: `${delay}s` }}
              >
                <line
                  x1={sx}
                  y1={sy}
                  x2={tx}
                  y2={ty}
                  stroke={strokeRef}
                  strokeWidth={1}
                  strokeOpacity={0.4}
                  strokeDasharray={dashArray}
                  strokeDashoffset={isSupersedesEdge ? dashedTotalLen : len}
                  style={{
                    animation: `hgDrawLine ${drawDuration}s ease-out ${delay}s forwards`,
                  }}
                />
              </g>

              {/* Idle pulse overlay (kicks in after ~8s) */}
              <line
                x1={sx}
                y1={sy}
                x2={tx}
                y2={ty}
                stroke={strokeRef}
                strokeWidth={1}
                strokeDasharray={isSupersedesEdge ? "6 3" : "none"}
                className="hg-idle-pulse"
                style={{
                  opacity: 0,
                  animationDelay: `${8 + pseudoRandom(i) * 2}s`,
                }}
              />

              {/* Edge label at midpoint */}
              {edge.label && (
                <text
                  x={mx}
                  y={my - 6}
                  textAnchor="middle"
                  fill="rgba(255,255,255,0.5)"
                  fontSize={8}
                  fontFamily="'Instrument Sans', sans-serif"
                  className="hg-edge-label"
                  style={{ animationDelay: `${delay + 0.3}s` }}
                >
                  {edge.label}
                </text>
              )}
            </g>
          );
        })}

        {/* ── Nodes ────────────────────────────────────────────── */}
        {NODES.map((node) => {
          const delay = nodeDelay(node);
          const idleDelay = 8 + pseudoRandom(node.id) * 3;

          if (node.kind === "decision") {
            return (
              <g
                key={`node-${node.id}`}
                className="hg-node-enter"
                style={{ animationDelay: `${delay}s` }}
              >
                <g
                  className="hg-idle-float"
                  style={{ animationDelay: `${idleDelay}s` }}
                >
                  <rect
                    x={node.x}
                    y={node.y}
                    width={node.w}
                    height={node.h}
                    rx={12}
                    ry={12}
                    fill="rgba(139,92,246,0.08)"
                    stroke="rgba(139,92,246,0.4)"
                    strokeWidth={1.5}
                  />
                  <text
                    x={node.x + node.w / 2}
                    y={node.y + node.h / 2 + 1}
                    textAnchor="middle"
                    dominantBaseline="central"
                    fill="rgba(255,255,255,0.9)"
                    fontSize={11}
                    fontFamily="'Instrument Sans', sans-serif"
                  >
                    {node.label.length > 28
                      ? node.label.slice(0, 26) + "\u2026"
                      : node.label}
                  </text>
                </g>
              </g>
            );
          }

          // Entity node -- pill shape
          return (
            <g
              key={`node-${node.id}`}
              className="hg-node-enter"
              style={{ animationDelay: `${delay}s` }}
            >
              <g
                className="hg-idle-float"
                style={{ animationDelay: `${idleDelay}s` }}
              >
                <rect
                  x={node.x}
                  y={node.y}
                  width={node.w}
                  height={node.h}
                  rx={16}
                  ry={16}
                  fill={entityFill(node.entityType)}
                  stroke={entityStroke(node.entityType)}
                  strokeWidth={1}
                />
                <text
                  x={node.x + node.w / 2}
                  y={node.y + node.h / 2 + 1}
                  textAnchor="middle"
                  dominantBaseline="central"
                  fill="rgba(255,255,255,0.8)"
                  fontSize={10}
                  fontFamily="'Instrument Sans', sans-serif"
                >
                  {node.label}
                </text>
              </g>
            </g>
          );
        })}
      </svg>
    </div>
  );
}
