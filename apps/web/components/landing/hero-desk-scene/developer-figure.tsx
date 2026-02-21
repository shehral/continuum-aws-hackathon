// Back-facing developer figure — detailed SVG illustration viewed from behind,
// sitting in front of dual monitors. Monitor light casts violet/blue-white glow
// on shoulders and upper back.

export function DeveloperFigure() {
  return (
    <g transform="translate(480, 250)">
      {/* ── Office chair ───────────────────────────────────────── */}
      {/* Chair back */}
      <path
        d="M 60 110 Q 60 80, 80 65 L 160 65 Q 180 80, 180 110 L 180 195 Q 178 205, 170 210 L 70 210 Q 62 205, 60 195 Z"
        fill="#1a1d2e"
        stroke="rgba(100,100,140,0.15)"
        strokeWidth={0.8}
      />
      {/* Chair stitching accent */}
      <line x1={120} y1={72} x2={120} y2={205} stroke="rgba(139,92,246,0.1)" strokeWidth={0.5} strokeDasharray="4 3" />
      {/* Chair armrest (left) */}
      <path
        d="M 55 155 L 38 155 Q 32 155, 32 160 L 32 168 Q 32 172, 38 172 L 58 172"
        fill="#1a1d2e" stroke="rgba(100,100,140,0.12)" strokeWidth={0.6}
      />
      {/* Chair armrest (right) */}
      <path
        d="M 185 155 L 202 155 Q 208 155, 208 160 L 208 168 Q 208 172, 202 172 L 182 172"
        fill="#1a1d2e" stroke="rgba(100,100,140,0.12)" strokeWidth={0.6}
      />

      {/* ── Torso (hoodie) ─────────────────────────────────────── */}
      <path
        d="M 75 45 Q 95 32, 120 30 Q 145 32, 165 45 L 175 60 L 180 110 L 180 180 Q 178 190, 170 195 L 70 195 Q 62 190, 60 180 L 60 110 L 65 60 Z"
        fill="#2D3748"
        stroke="rgba(100,100,140,0.12)"
        strokeWidth={0.8}
      />

      {/* Hoodie seam lines */}
      <line x1={120} y1={32} x2={120} y2={190} stroke="rgba(255,255,255,0.04)" strokeWidth={0.5} />
      {/* Shoulder seam left */}
      <path d="M 78 48 Q 90 40, 105 38" fill="none" stroke="rgba(255,255,255,0.05)" strokeWidth={0.5} />
      {/* Shoulder seam right */}
      <path d="M 162 48 Q 150 40, 135 38" fill="none" stroke="rgba(255,255,255,0.05)" strokeWidth={0.5} />

      {/* Hood hanging down the back */}
      <path
        d="M 90 30 Q 100 22, 120 20 Q 140 22, 150 30 L 152 50 Q 145 55, 120 56 Q 95 55, 88 50 Z"
        fill="#343E52"
        stroke="rgba(255,255,255,0.04)"
        strokeWidth={0.5}
      />

      {/* ── Neck ───────────────────────────────────────────────── */}
      <rect x={108} y={10} width={24} height={22} rx={4} fill="#D4A574" />
      {/* Neck shadow */}
      <rect x={108} y={22} width={24} height={10} rx={2} fill="#B8886C" opacity={0.4} />

      {/* ── Head ───────────────────────────────────────────────── */}
      <ellipse cx={120} cy={-8} rx={30} ry={26} fill="#2C1810" />

      {/* Hair texture — top strands */}
      <path d="M 92 -20 Q 100 -35, 120 -36 Q 140 -35, 148 -20" fill="none" stroke="#4A2C1C" strokeWidth={1.5} strokeLinecap="round" />
      <path d="M 95 -16 Q 108 -30, 120 -32 Q 132 -30, 145 -16" fill="none" stroke="#3D2418" strokeWidth={1} strokeLinecap="round" />
      <path d="M 98 -12 Q 110 -26, 120 -28 Q 130 -26, 142 -12" fill="none" stroke="#4A2C1C" strokeWidth={0.8} strokeLinecap="round" opacity={0.6} />

      {/* Hair sides — covering ears */}
      <path d="M 91 -8 Q 88 0, 90 10" fill="none" stroke="#2C1810" strokeWidth={6} strokeLinecap="round" />
      <path d="M 149 -8 Q 152 0, 150 10" fill="none" stroke="#2C1810" strokeWidth={6} strokeLinecap="round" />

      {/* Ears (peaking through) */}
      <ellipse cx={89} cy={-2} rx={5} ry={7} fill="#C49A6C" stroke="#B8886C" strokeWidth={0.5} />
      <ellipse cx={151} cy={-2} rx={5} ry={7} fill="#C49A6C" stroke="#B8886C" strokeWidth={0.5} />

      {/* ── Left arm reaching to keyboard ──────────────────────── */}
      <path
        d="M 65 60 Q 40 80, 25 115 Q 15 145, 20 175"
        fill="none" stroke="#2D3748" strokeWidth={20} strokeLinecap="round"
      />
      {/* Arm edge highlight */}
      <path
        d="M 65 60 Q 40 80, 25 115 Q 15 145, 20 175"
        fill="none" stroke="rgba(100,100,140,0.1)" strokeWidth={1} strokeLinecap="round"
      />
      {/* Left hand */}
      <ellipse cx={22} cy={178} rx={10} ry={6} fill="#D4A574" />
      {/* Fingers */}
      <path d="M 14 176 L 10 174" stroke="#C49A6C" strokeWidth={1.5} strokeLinecap="round" />
      <path d="M 16 179 L 12 178" stroke="#C49A6C" strokeWidth={1.5} strokeLinecap="round" />
      <path d="M 18 181 L 14 181" stroke="#C49A6C" strokeWidth={1.5} strokeLinecap="round" />

      {/* ── Right arm reaching to keyboard ─────────────────────── */}
      <path
        d="M 175 60 Q 200 80, 215 115 Q 225 145, 220 175"
        fill="none" stroke="#2D3748" strokeWidth={20} strokeLinecap="round"
      />
      <path
        d="M 175 60 Q 200 80, 215 115 Q 225 145, 220 175"
        fill="none" stroke="rgba(100,100,140,0.1)" strokeWidth={1} strokeLinecap="round"
      />
      {/* Right hand */}
      <ellipse cx={218} cy={178} rx={10} ry={6} fill="#D4A574" />
      {/* Fingers */}
      <path d="M 226 176 L 230 174" stroke="#C49A6C" strokeWidth={1.5} strokeLinecap="round" />
      <path d="M 224 179 L 228 178" stroke="#C49A6C" strokeWidth={1.5} strokeLinecap="round" />
      <path d="M 222 181 L 226 181" stroke="#C49A6C" strokeWidth={1.5} strokeLinecap="round" />

      {/* ── Monitor light cast on back ─────────────────────────── */}
      {/* Violet/blue-white gradient overlay on shoulders & upper back */}
      <rect
        x={60} y={30} width={120} height={100} rx={8}
        fill="rgba(139,92,246,0.12)"
        style={{ mixBlendMode: "screen" }}
      />
      {/* Stronger center highlight */}
      <ellipse
        cx={120} cy={65} rx={40} ry={35}
        fill="rgba(180,170,255,0.06)"
        style={{ mixBlendMode: "screen" }}
      />
    </g>
  );
}
