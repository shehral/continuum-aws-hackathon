// Root SVG for the home office developer scene.
// Composes: desk → monitors → developer → ambient lighting.
// Purely static — animation is driven by the parent (hero-conductor) via wrapper motion.div.

import { Monitor } from "./hero-desk-scene/monitor";
import { DeskPeripherals } from "./hero-desk-scene/desk-peripherals";
import { DeveloperFigure } from "./hero-desk-scene/developer-figure";

export function HeroDeskScene() {
  return (
    <svg
      viewBox="0 0 1200 700"
      width="100%"
      fill="none"
      className="block"
      aria-hidden="true"
    >
      <defs>
        {/* Monitor screen glow — violet/blue cast */}
        <radialGradient id="monitor-glow-l" cx="30%" cy="50%" r="55%">
          <stop offset="0%" stopColor="rgba(139,92,246,0.18)" />
          <stop offset="60%" stopColor="rgba(100,80,200,0.06)" />
          <stop offset="100%" stopColor="rgba(139,92,246,0)" />
        </radialGradient>
        <radialGradient id="monitor-glow-r" cx="70%" cy="50%" r="55%">
          <stop offset="0%" stopColor="rgba(139,92,246,0.18)" />
          <stop offset="60%" stopColor="rgba(100,80,200,0.06)" />
          <stop offset="100%" stopColor="rgba(139,92,246,0)" />
        </radialGradient>

        {/* Desk surface subtle gradient */}
        <linearGradient id="desk-surface" x1="0" y1="0" x2="0" y2="1">
          <stop offset="0%" stopColor="#1e1c30" />
          <stop offset="100%" stopColor="#141226" />
        </linearGradient>

        {/* PC tower LED glow */}
        <radialGradient id="pc-led-glow" cx="50%" cy="50%" r="50%">
          <stop offset="0%" stopColor="rgba(139,92,246,0.3)" />
          <stop offset="100%" stopColor="rgba(139,92,246,0)" />
        </radialGradient>
      </defs>

      {/* ── Ambient room glow (behind everything) ──────────────── */}
      <ellipse
        cx={600} cy={400} rx={500} ry={300}
        fill="url(#monitor-glow-l)"
        opacity={0.4}
      />

      {/* ── Desk & peripherals ─────────────────────────────────── */}
      <DeskPeripherals />

      {/* ── Left monitor (chat) ────────────────────────────────── */}
      <Monitor side="left" x={145} y={170} />

      {/* ── Right monitor (code) ───────────────────────────────── */}
      <Monitor side="right" x={690} y={170} />

      {/* ── Keyboard between monitors (on desk) ────────────────── */}
      <g transform="translate(480, 435)">
        {/* Keyboard body */}
        <rect x={0} y={0} width={240} height={28} rx={4} fill="#141226" stroke="#2a2a40" strokeWidth={0.6} />
        {/* Key rows (simplified) */}
        {[4, 10, 16].map(ky => (
          <g key={ky}>
            {Array.from({ length: 14 }, (_, ki) => (
              <rect
                key={ki}
                x={8 + ki * 16}
                y={ky}
                width={12}
                height={5}
                rx={1}
                fill="#1a1830"
                stroke="rgba(100,100,140,0.08)"
                strokeWidth={0.3}
              />
            ))}
          </g>
        ))}
        {/* Spacebar */}
        <rect x={60} y={22} width={120} height={4} rx={1.5} fill="#1a1830" stroke="rgba(100,100,140,0.08)" strokeWidth={0.3} />
      </g>

      {/* ── Developer figure (back to viewer) ──────────────────── */}
      <DeveloperFigure />

      {/* ── Ambient light overlay (monitors casting on scene) ──── */}
      <rect
        x={100} y={200} width={1000} height={300}
        fill="url(#monitor-glow-l)"
        opacity={0.15}
        style={{ mixBlendMode: "screen" }}
      />
    </svg>
  );
}
