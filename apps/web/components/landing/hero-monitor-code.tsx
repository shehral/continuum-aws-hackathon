"use client";

import { motion, useTransform, type MotionValue } from "framer-motion";
import { CODE_LINES, TOKEN_COLORS, type CodeLine } from "./hero-data";

// ── Per-line sub-component (hooks outside .map) ──────────────────────

function CodeLineRow({
  line,
  index,
  scrollYProgress,
}: {
  line: CodeLine;
  index: number;
  scrollYProgress: MotionValue<number>;
}) {
  const delay = index * 0.01;
  const y = useTransform(scrollYProgress, [0.32 + delay, 0.52 + delay], [0, -200]);
  const x = useTransform(scrollYProgress, [0.32 + delay, 0.52 + delay], [0, -150]);
  const scale = useTransform(scrollYProgress, [0.32 + delay, 0.52 + delay], [1, 0.6]);
  const opacity = useTransform(
    scrollYProgress,
    [0.32 + delay, 0.50 + delay, 0.54 + delay],
    [1, 1, 0]
  );

  const isEmpty = line.tokens.length === 0;

  return (
    <motion.div
      className="flex items-start"
      style={{ y, x, scale, opacity, height: isEmpty ? "10px" : "auto" }}
    >
      {/* Line number gutter */}
      <span className="w-[22px] text-right pr-[6px] text-slate-600 select-none shrink-0">
        {line.lineNo}
      </span>
      {/* Tokens */}
      <span className="whitespace-pre">
        {line.tokens.map((token, ti) => (
          <span key={ti} style={{ color: TOKEN_COLORS[token.color] }}>
            {token.text}
          </span>
        ))}
      </span>
    </motion.div>
  );
}

// ── Overlay container ────────────────────────────────────────────────

export function HeroMonitorCode({
  scrollYProgress,
}: {
  scrollYProgress: MotionValue<number>;
}) {
  // Positions from SVG viewBox coordinates (right monitor screen area):
  // Monitor at x=690, bezel=12 → screen starts at x=702, y=182, w=340, h=220
  // Wrapper has aspect-ratio: 1200/700, so viewBox % maps 1:1.
  return (
    <div
      className="absolute overflow-hidden pointer-events-none"
      style={{
        left: `${(702 / 1200) * 100}%`,
        top: `${(182 / 700) * 100}%`,
        width: `${(340 / 1200) * 100}%`,
        height: `${(220 / 700) * 100}%`,
        textRendering: "optimizeSpeed",
      }}
    >
      <div className="w-full h-full bg-[hsl(250,20%,5%)] rounded-[3px] flex flex-col">
        {/* Title bar */}
        <div className="flex items-center gap-1.5 px-2 py-1 border-b border-white/[0.06] shrink-0">
          {/* Traffic light dots */}
          <span className="w-[5px] h-[5px] rounded-full bg-red-500/40" />
          <span className="w-[5px] h-[5px] rounded-full bg-yellow-500/40" />
          <span className="w-[5px] h-[5px] rounded-full bg-green-500/40" />
          <span className="ml-2 text-[6px] text-slate-500 font-mono">
            agent.py
          </span>
        </div>

        {/* Code content */}
        <div className="flex-1 p-1.5 text-[7px] leading-[1.4] font-mono overflow-hidden">
          {CODE_LINES.map((line, i) => (
            <CodeLineRow
              key={line.lineNo}
              line={line}
              index={i}
              scrollYProgress={scrollYProgress}
            />
          ))}
        </div>
      </div>
    </div>
  );
}
