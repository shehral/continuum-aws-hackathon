// Parametric monitor bezel + stand — used twice (left and right)

export interface MonitorProps {
  side: "left" | "right";
  /** Horizontal offset within the root SVG viewBox */
  x: number;
  /** Vertical offset within the root SVG viewBox */
  y: number;
}

// Screen area dimensions (used for HTML overlay coordinate mapping)
export const MONITOR_SCREEN = { w: 340, h: 220 };
const BEZEL = 12;
const OUTER_W = MONITOR_SCREEN.w + BEZEL * 2;
const OUTER_H = MONITOR_SCREEN.h + BEZEL * 2 + 8; // extra for chin
const STAND_W = 60;
const STAND_H = 30;
const BASE_W = 120;

export function Monitor({ side, x, y }: MonitorProps) {
  void side; // both monitors render identically; side kept for future use
  return (
    <g transform={`translate(${x}, ${y})`}>
      {/* Monitor outer shell */}
      <rect
        x={0}
        y={0}
        width={OUTER_W}
        height={OUTER_H}
        rx={10}
        ry={10}
        fill="#12121e"
        stroke="#2a2a40"
        strokeWidth={1.2}
      />

      {/* Metallic frame highlight — top edge */}
      <line
        x1={12}
        y1={1}
        x2={OUTER_W - 12}
        y2={1}
        stroke="rgba(100,100,140,0.35)"
        strokeWidth={0.8}
        strokeLinecap="round"
      />

      {/* Screen background (clip target for HTML overlay) */}
      <rect
        x={BEZEL}
        y={BEZEL}
        width={MONITOR_SCREEN.w}
        height={MONITOR_SCREEN.h}
        rx={4}
        ry={4}
        fill="#0a0a14"
      />

      {/* Faint screen edge highlight */}
      <rect
        x={BEZEL}
        y={BEZEL}
        width={MONITOR_SCREEN.w}
        height={MONITOR_SCREEN.h}
        rx={4}
        ry={4}
        fill="none"
        stroke="rgba(139,92,246,0.12)"
        strokeWidth={0.5}
      />

      {/* Chin logo dot */}
      <circle
        cx={OUTER_W / 2}
        cy={OUTER_H - 8}
        r={2.5}
        fill="#1e1e30"
        stroke="rgba(100,100,140,0.2)"
        strokeWidth={0.5}
      />

      {/* Stand neck */}
      <rect
        x={(OUTER_W - STAND_W) / 2}
        y={OUTER_H}
        width={STAND_W}
        height={STAND_H}
        rx={2}
        fill="#16162a"
        stroke="#2a2a40"
        strokeWidth={0.8}
      />

      {/* Stand base */}
      <ellipse
        cx={OUTER_W / 2}
        cy={OUTER_H + STAND_H + 4}
        rx={BASE_W / 2}
        ry={6}
        fill="#16162a"
        stroke="#2a2a40"
        strokeWidth={0.8}
      />
    </g>
  );
}
