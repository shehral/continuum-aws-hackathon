"use client";

import { useRef } from "react";
import {
  motion,
  useScroll,
  useTransform,
  useReducedMotion,
  type MotionValue,
} from "framer-motion";
import { Sparkles } from "lucide-react";
import { HeroDeskScene } from "./hero-desk-scene";
import { HeroMonitorChat } from "./hero-monitor-chat";
import { HeroMonitorCode } from "./hero-monitor-code";
import {
  GRAPH_NODES,
  GRAPH_EDGES,
  nodeColor,
  nodeBg,
  nodeBorder,
  type GraphNode,
} from "./hero-data";

// ── Sub-components (hooks outside .map) ──────────────────────────────

function EdgeLabel({
  x,
  y,
  label,
  scrollYProgress,
}: {
  x: number;
  y: number;
  label: string;
  scrollYProgress: MotionValue<number>;
}) {
  const opacity = useTransform(scrollYProgress, [0.68, 0.82], [0, 0.5]);
  return (
    <motion.text
      x={x}
      y={y}
      textAnchor="middle"
      className="text-foreground"
      fill="currentColor"
      fillOpacity={0.5}
      fontSize="11"
      fontFamily="'Instrument Sans', sans-serif"
      style={{ opacity }}
    >
      {label}
    </motion.text>
  );
}

function GraphNodePill({
  node,
  index,
  scrollYProgress,
}: {
  node: GraphNode;
  index: number;
  scrollYProgress: MotionValue<number>;
}) {
  const left = 600 + node.x;
  const top = 360 + node.y;
  const isDecision = node.kind === "decision";
  const delay = index * 0.015;
  const nodeOpacity = useTransform(
    scrollYProgress,
    [0.48 + delay, 0.62 + delay],
    [0, 1]
  );
  const nodeScale = useTransform(
    scrollYProgress,
    [0.48 + delay, 0.62 + delay],
    [0.5, 1]
  );

  return (
    <motion.div
      className="absolute flex items-center justify-center whitespace-nowrap"
      style={{
        left: `${left}px`,
        top: `${top}px`,
        x: "-50%",
        y: "-50%",
        opacity: nodeOpacity,
        scale: nodeScale,
      }}
    >
      <div
        className={`px-5 py-2.5 rounded-full border text-sm font-medium ${
          isDecision ? "rounded-xl" : ""
        }`}
        style={{
          background: nodeBg(node),
          borderColor: nodeBorder(node),
          color: nodeColor(node),
        }}
      >
        {node.label}
      </div>
    </motion.div>
  );
}

// ── Main component ───────────────────────────────────────────────────

export function HeroConductor() {
  const containerRef = useRef<HTMLDivElement>(null);
  const prefersReducedMotion = useReducedMotion();

  const { scrollYProgress } = useScroll({
    target: containerRef,
    offset: ["start start", "end end"],
  });

  // ── Scroll-mapped transforms ───────────────────────────────────
  //
  // Phase 1: Full Scene (0.00 → 0.25)
  //   Tagline visible, desk scene visible, chat + code on monitors
  //
  // Phase 2: Content Lifts Off (0.30 → 0.52)
  //   Chat messages float up-right, code lines float up-left
  //   (Per-item transforms live in HeroMonitorChat / HeroMonitorCode)
  //
  // Phase 3: Convergence (0.45 → 0.75)
  //   Desk fades, light trails draw, graph materializes
  //
  // Phase 4: Graph Settled (0.68 → 1.00)
  //   Edge labels fade in, graph at full opacity

  // Eyebrow badge — visible on load, fades early
  const badgeOpacity = useTransform(scrollYProgress, [0, 0.12, 0.25], [1, 1, 0]);

  // Tagline — VISIBLE FROM START, fades out + floats up before content lifts
  const taglineOpacity = useTransform(scrollYProgress, [0, 0.25, 0.4], [1, 1, 0]);
  const taglineY = useTransform(scrollYProgress, [0.25, 0.4], [0, -60]);

  // Desk scene — visible from start, fades during convergence
  const sceneOpacity = useTransform(scrollYProgress, [0, 0.5, 0.7], [1, 1, 0]);
  const sceneScale = useTransform(scrollYProgress, [0.45, 0.7], [1, 0.92]);

  // Light trails (monitors → center) — bridging transition
  const trailOpacity = useTransform(
    scrollYProgress,
    [0.35, 0.42, 0.6, 0.68],
    [0, 0.7, 0.7, 0]
  );
  const trailLength = useTransform(scrollYProgress, [0.35, 0.6], [0, 1]);

  // Graph container — appears during convergence
  const graphOpacity = useTransform(scrollYProgress, [0.48, 0.62, 1.0], [0, 1, 1]);
  const graphScale = useTransform(scrollYProgress, [0.48, 0.65], [0.7, 1]);

  // Graph edges — draw in after nodes appear
  const edgeProgress = useTransform(scrollYProgress, [0.55, 0.75], [0, 1]);

  // ── Reduced motion: static fallback ─────────────────────────────
  if (prefersReducedMotion) {
    return (
      <div className="relative bg-background">
        {/* Tagline */}
        <div className="text-center pt-28 pb-8 px-6">
          <div className="inline-flex items-center gap-2 px-4 py-1.5 rounded-full border border-violet-500/20 bg-violet-500/5 text-sm text-violet-300 mb-6">
            <Sparkles className="w-4 h-4" />
            Observable Agent Memory
          </div>
          <h2 className="text-3xl sm:text-4xl md:text-5xl font-bold tracking-tight leading-tight">
            Your agent{" "}
            <span className="gradient-text">learns.</span>
            <br />
            Every decision{" "}
            <span className="gradient-text">traced.</span>
          </h2>
        </div>

        {/* Static desk scene */}
        <div className="max-w-[1000px] mx-auto px-4 pb-16">
          <div className="relative">
            <HeroDeskScene />
          </div>
        </div>

        {/* Static graph */}
        <div className="relative w-[1200px] max-w-full mx-auto px-4 pb-24 h-[720px] overflow-hidden">
          <svg className="absolute inset-0 w-full h-full" aria-hidden="true">
            {GRAPH_EDGES.map((edge, i) => {
              const sNode = GRAPH_NODES[edge.source];
              const tNode = GRAPH_NODES[edge.target];
              const sx = 600 + sNode.x;
              const sy = 360 + sNode.y;
              const tx = 600 + tNode.x;
              const ty = 360 + tNode.y;
              return (
                <g key={`edge-${i}`}>
                  <line
                    x1={sx} y1={sy} x2={tx} y2={ty}
                    stroke={edge.dashed ? "rgba(236,72,153,0.4)" : "rgba(139,92,246,0.3)"}
                    strokeWidth={1.5}
                    strokeDasharray={edge.dashed ? "6 4" : "none"}
                  />
                  <text
                    x={(sx + tx) / 2} y={(sy + ty) / 2 - 8}
                    textAnchor="middle"
                    className="text-foreground"
                    fill="currentColor"
                    fillOpacity={0.5}
                    fontSize="11"
                    fontFamily="'Instrument Sans', sans-serif"
                    opacity={0.5}
                  >
                    {edge.label}
                  </text>
                </g>
              );
            })}
          </svg>
          {GRAPH_NODES.map((node) => {
            const left = 600 + node.x;
            const top = 360 + node.y;
            return (
              <div
                key={`node-${node.id}`}
                className="absolute flex items-center justify-center whitespace-nowrap"
                style={{ left: `${left}px`, top: `${top}px`, transform: "translate(-50%, -50%)" }}
              >
                <div
                  className={`px-5 py-2.5 rounded-full border text-sm font-medium ${node.kind === "decision" ? "rounded-xl" : ""}`}
                  style={{ background: nodeBg(node), borderColor: nodeBorder(node), color: nodeColor(node) }}
                >
                  {node.label}
                </div>
              </div>
            );
          })}
        </div>
      </div>
    );
  }

  return (
    <div
      ref={containerRef}
      className="relative"
      style={{ height: "250vh" }}
    >
      {/* Sticky viewport */}
      <div className="sticky top-0 h-screen w-full overflow-hidden flex items-center justify-center">
        {/* Background */}
        <div className="absolute inset-0 bg-background" />

        {/* Nebula orbs */}
        <div
          className="absolute inset-0 overflow-hidden pointer-events-none"
          aria-hidden="true"
        >
          <div className="absolute top-1/4 left-[16%] w-72 h-72 bg-violet-500/[0.08] rounded-full blur-3xl animate-float" />
          <div className="absolute bottom-1/3 right-1/4 w-96 h-96 bg-fuchsia-500/[0.05] rounded-full blur-3xl animate-float [animation-delay:-1.5s]" />
          <div className="absolute top-1/2 right-[16%] w-56 h-56 bg-orange-500/[0.04] rounded-full blur-3xl animate-float [animation-delay:-3s]" />
        </div>

        {/* ── Eyebrow badge ──────────────────────────────────────── */}
        <motion.div
          className="absolute top-[6%] left-1/2 -translate-x-1/2 text-center z-10"
          style={{ opacity: badgeOpacity }}
        >
          <div className="inline-flex items-center gap-2 px-4 py-1.5 rounded-full border border-violet-500/20 bg-violet-500/5 text-sm text-violet-300">
            <Sparkles className="w-4 h-4" />
            Observable Agent Memory
          </div>
        </motion.div>

        {/* ── Tagline — ABOVE monitors, visible from start ───────── */}
        <motion.div
          className="absolute top-[11%] left-1/2 -translate-x-1/2 text-center z-10"
          style={{ opacity: taglineOpacity, y: taglineY }}
        >
          <h2 className="text-3xl sm:text-4xl md:text-5xl font-bold tracking-tight leading-tight">
            Your agent{" "}
            <span className="gradient-text">learns.</span>
            <br />
            Every decision{" "}
            <span className="gradient-text">traced.</span>
          </h2>
        </motion.div>

        {/* ── Desk scene + monitor overlays ───────────────────────── */}
        <motion.div
          className="absolute inset-x-0 bottom-[2%] flex items-end justify-center"
          style={{
            opacity: sceneOpacity,
            scale: sceneScale,
            willChange: "transform, opacity",
          }}
        >
          {/* Scene wrapper — aspect-ratio matches SVG viewBox so % overlays align */}
          <div className="relative w-full max-w-[1100px] mx-auto" style={{ aspectRatio: "1200 / 700" }}>
            {/* SVG illustration */}
            <HeroDeskScene />

            {/* Chat overlay on left monitor */}
            <HeroMonitorChat scrollYProgress={scrollYProgress} />

            {/* Code overlay on right monitor */}
            <HeroMonitorCode scrollYProgress={scrollYProgress} />
          </div>
        </motion.div>

        {/* ── Light trails (monitors → center) ───────────────────── */}
        <svg
          className="absolute inset-0 w-full h-full pointer-events-none"
          viewBox="0 0 1000 800"
          preserveAspectRatio="xMidYMid meet"
          aria-hidden="true"
        >
          <defs>
            <linearGradient id="hc-trail-ll" x1="0.3" y1="0.7" x2="0.45" y2="0.3">
              <stop offset="0%" stopColor="rgba(139,92,246,0.6)" />
              <stop offset="50%" stopColor="rgba(236,72,153,0.3)" />
              <stop offset="100%" stopColor="rgba(251,146,60,0.1)" />
            </linearGradient>
            <linearGradient id="hc-trail-lr" x1="0.3" y1="0.5" x2="0.5" y2="0.3">
              <stop offset="0%" stopColor="rgba(139,92,246,0.5)" />
              <stop offset="100%" stopColor="rgba(236,72,153,0.15)" />
            </linearGradient>
            <linearGradient id="hc-trail-rl" x1="0.7" y1="0.5" x2="0.5" y2="0.3">
              <stop offset="0%" stopColor="rgba(139,92,246,0.5)" />
              <stop offset="100%" stopColor="rgba(251,146,60,0.15)" />
            </linearGradient>
            <linearGradient id="hc-trail-rr" x1="0.7" y1="0.7" x2="0.55" y2="0.3">
              <stop offset="0%" stopColor="rgba(139,92,246,0.6)" />
              <stop offset="50%" stopColor="rgba(236,72,153,0.3)" />
              <stop offset="100%" stopColor="rgba(251,146,60,0.1)" />
            </linearGradient>
          </defs>

          {/* Left monitor — outer trail */}
          <motion.path
            d="M 280 520 Q 350 400, 460 300"
            fill="none"
            stroke="url(#hc-trail-ll)"
            strokeWidth="2"
            strokeLinecap="round"
            pathLength="1"
            style={{ pathLength: trailLength, opacity: trailOpacity }}
          />
          {/* Left monitor — inner trail */}
          <motion.path
            d="M 320 500 Q 400 380, 480 290"
            fill="none"
            stroke="url(#hc-trail-lr)"
            strokeWidth="1.5"
            strokeLinecap="round"
            pathLength="1"
            style={{ pathLength: trailLength, opacity: trailOpacity }}
          />
          {/* Right monitor — inner trail */}
          <motion.path
            d="M 680 500 Q 600 380, 520 290"
            fill="none"
            stroke="url(#hc-trail-rl)"
            strokeWidth="1.5"
            strokeLinecap="round"
            pathLength="1"
            style={{ pathLength: trailLength, opacity: trailOpacity }}
          />
          {/* Right monitor — outer trail */}
          <motion.path
            d="M 720 520 Q 650 400, 540 300"
            fill="none"
            stroke="url(#hc-trail-rr)"
            strokeWidth="2"
            strokeLinecap="round"
            pathLength="1"
            style={{ pathLength: trailLength, opacity: trailOpacity }}
          />
        </svg>

        {/* ── Knowledge Graph ────────────────────────────────────── */}
        <motion.div
          className="absolute inset-0 flex items-center justify-center"
          style={{
            opacity: graphOpacity,
            scale: graphScale,
            willChange: "transform, opacity",
          }}
        >
          <div className="relative w-[1200px] h-[720px]">
            {/* Edges */}
            <svg className="absolute inset-0 w-full h-full" aria-hidden="true">
              {GRAPH_EDGES.map((edge, i) => {
                const sNode = GRAPH_NODES[edge.source];
                const tNode = GRAPH_NODES[edge.target];
                const sx = 600 + sNode.x;
                const sy = 360 + sNode.y;
                const tx = 600 + tNode.x;
                const ty = 360 + tNode.y;

                return (
                  <g key={`edge-${i}`}>
                    <motion.line
                      x1={sx}
                      y1={sy}
                      x2={tx}
                      y2={ty}
                      stroke={
                        edge.dashed
                          ? "rgba(236,72,153,0.4)"
                          : "rgba(139,92,246,0.3)"
                      }
                      strokeWidth={1.5}
                      strokeDasharray={edge.dashed ? "6 4" : "none"}
                      pathLength="1"
                      style={{ pathLength: edgeProgress }}
                    />
                    <EdgeLabel
                      x={(sx + tx) / 2}
                      y={(sy + ty) / 2 - 8}
                      label={edge.label}
                      scrollYProgress={scrollYProgress}
                    />
                  </g>
                );
              })}
            </svg>

            {/* Nodes */}
            {GRAPH_NODES.map((node, i) => (
              <GraphNodePill
                key={`node-${node.id}`}
                node={node}
                index={i}
                scrollYProgress={scrollYProgress}
              />
            ))}
          </div>
        </motion.div>
      </div>
    </div>
  );
}
