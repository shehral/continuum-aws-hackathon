"use client";

import { motion, useTransform, type MotionValue } from "framer-motion";
import { CHAT_MESSAGES } from "./hero-data";

// ── Per-message sub-component (hooks must live outside .map) ─────────

function ChatMessage({
  msg,
  index,
  scrollYProgress,
}: {
  msg: (typeof CHAT_MESSAGES)[number];
  index: number;
  scrollYProgress: MotionValue<number>;
}) {
  const delay = index * 0.02;
  const y = useTransform(scrollYProgress, [0.3 + delay, 0.5 + delay], [0, -200]);
  const x = useTransform(scrollYProgress, [0.3 + delay, 0.5 + delay], [0, 150]);
  const scale = useTransform(scrollYProgress, [0.3 + delay, 0.5 + delay], [1, 0.6]);
  const opacity = useTransform(
    scrollYProgress,
    [0.3 + delay, 0.48 + delay, 0.52 + delay],
    [1, 1, 0]
  );

  return (
    <motion.div
      className={`rounded-md px-2 py-1.5 max-w-[90%] ${
        msg.role === "human"
          ? "self-end bg-violet-500/15 text-violet-200/90 border border-violet-500/25"
          : "self-start bg-white/[0.06] text-slate-300/80 border border-white/[0.08]"
      }`}
      style={{ y, x, scale, opacity }}
    >
      <span className="block text-[6px] font-semibold mb-0.5 opacity-60 uppercase tracking-wider">
        {msg.role === "human" ? "You" : "Claude"}
      </span>
      {msg.text}
    </motion.div>
  );
}

// ── Overlay container ────────────────────────────────────────────────

export function HeroMonitorChat({
  scrollYProgress,
}: {
  scrollYProgress: MotionValue<number>;
}) {
  // Positions from SVG viewBox coordinates (left monitor screen area):
  // Monitor at x=145, bezel=12 → screen starts at x=157, y=182, w=340, h=220
  // Wrapper has aspect-ratio: 1200/700, so viewBox % maps 1:1.
  return (
    <div
      className="absolute overflow-hidden pointer-events-none"
      style={{
        left: `${(157 / 1200) * 100}%`,
        top: `${(182 / 700) * 100}%`,
        width: `${(340 / 1200) * 100}%`,
        height: `${(220 / 700) * 100}%`,
        textRendering: "optimizeSpeed",
      }}
    >
      <div className="w-full h-full bg-[hsl(250,20%,5%)] rounded-[3px] p-2 flex flex-col gap-1.5 text-[8px] leading-snug font-['Instrument_Sans',sans-serif]">
        {CHAT_MESSAGES.map((msg, i) => (
          <ChatMessage
            key={i}
            msg={msg}
            index={i}
            scrollYProgress={scrollYProgress}
          />
        ))}
      </div>
    </div>
  );
}
