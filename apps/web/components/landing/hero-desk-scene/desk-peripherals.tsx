// Desk surface, PC tower, speakers, mouse, headphones, coffee mug, cable tray.
// All items use natural dark colors with violet/blue tint from monitor light cast.

export function DeskPeripherals() {
  return (
    <g>
      {/* ── Desk surface ───────────────────────────────────────── */}
      <rect x={50} y={460} width={1100} height={18} rx={3} fill="#1c1a2a" />
      {/* Top edge highlight */}
      <line
        x1={55} y1={460} x2={1145} y2={460}
        stroke="rgba(139,92,246,0.12)" strokeWidth={0.8}
      />
      {/* Wood grain lines */}
      <line x1={100} y1={464} x2={1100} y2={464} stroke="rgba(255,255,255,0.02)" strokeWidth={0.5} />
      <line x1={80} y1={470} x2={1120} y2={470} stroke="rgba(255,255,255,0.015)" strokeWidth={0.5} />

      {/* Desk front edge */}
      <rect x={50} y={478} width={1100} height={6} rx={1} fill="#15132a" />

      {/* ── PC tower (right side) ──────────────────────────────── */}
      <g transform="translate(1000, 318)">
        {/* Case body */}
        <rect x={0} y={0} width={70} height={140} rx={4} fill="#131320" stroke="#2a2a40" strokeWidth={0.8} />
        {/* Side panel (tempered glass effect) */}
        <rect x={4} y={8} width={62} height={90} rx={2} fill="rgba(139,92,246,0.03)" stroke="rgba(139,92,246,0.08)" strokeWidth={0.5} />
        {/* LED strip */}
        <rect x={6} y={10} width={2} height={86} rx={1} fill="rgba(139,92,246,0.5)" />
        {/* Vent grills */}
        {[110, 116, 122, 128].map(vy => (
          <line key={vy} x1={10} y1={vy} x2={60} y2={vy} stroke="rgba(100,100,140,0.15)" strokeWidth={0.6} />
        ))}
        {/* Power LED */}
        <circle cx={35} cy={134} r={1.5} fill="rgba(139,92,246,0.7)" />
      </g>

      {/* ── Left speaker ───────────────────────────────────────── */}
      <g transform="translate(105, 396)">
        <rect x={0} y={0} width={28} height={60} rx={3} fill="#17152a" stroke="#2a2a40" strokeWidth={0.6} />
        {/* Driver cone */}
        <circle cx={14} cy={20} r={8} fill="#0e0e1c" stroke="rgba(100,100,140,0.2)" strokeWidth={0.5} />
        <circle cx={14} cy={20} r={3} fill="#17152a" />
        {/* Tweeter */}
        <circle cx={14} cy={42} r={4} fill="#0e0e1c" stroke="rgba(100,100,140,0.2)" strokeWidth={0.5} />
        {/* Indicator LED */}
        <circle cx={14} cy={55} r={1} fill="rgba(139,92,246,0.5)" />
      </g>

      {/* ── Right speaker ──────────────────────────────────────── */}
      <g transform="translate(950, 396)">
        <rect x={0} y={0} width={28} height={60} rx={3} fill="#17152a" stroke="#2a2a40" strokeWidth={0.6} />
        <circle cx={14} cy={20} r={8} fill="#0e0e1c" stroke="rgba(100,100,140,0.2)" strokeWidth={0.5} />
        <circle cx={14} cy={20} r={3} fill="#17152a" />
        <circle cx={14} cy={42} r={4} fill="#0e0e1c" stroke="rgba(100,100,140,0.2)" strokeWidth={0.5} />
        <circle cx={14} cy={55} r={1} fill="rgba(139,92,246,0.5)" />
      </g>

      {/* ── Mouse + mousepad (right of center) ─────────────────── */}
      <g transform="translate(760, 438)">
        {/* Mousepad */}
        <rect x={-10} y={-4} width={70} height={30} rx={3} fill="#141226" stroke="rgba(100,100,140,0.08)" strokeWidth={0.4} />
        {/* Mouse body */}
        <ellipse cx={25} cy={10} rx={12} ry={8} fill="#1a1830" stroke="#2a2a40" strokeWidth={0.6} />
        {/* Mouse wheel */}
        <rect x={23} y={4} width={4} height={6} rx={2} fill="#2a2a40" />
        {/* RGB strip */}
        <ellipse cx={25} cy={10} rx={12} ry={8} fill="none" stroke="rgba(139,92,246,0.2)" strokeWidth={0.4} />
      </g>

      {/* ── Headphones (on desk to the left) ───────────────────── */}
      <g transform="translate(155, 420)">
        {/* Headband */}
        <path
          d="M 0 30 Q 20 -5, 45 30"
          fill="none" stroke="#2a2a40" strokeWidth={4} strokeLinecap="round"
        />
        {/* Headband inner */}
        <path
          d="M 2 30 Q 20 0, 43 30"
          fill="none" stroke="#1a1a30" strokeWidth={2} strokeLinecap="round"
        />
        {/* Left earcup */}
        <ellipse cx={2} cy={32} rx={10} ry={12} fill="#1a1a2e" stroke="#3d3d5c" strokeWidth={0.8} />
        <ellipse cx={2} cy={32} rx={6} ry={8} fill="#12121e" />
        {/* Right earcup */}
        <ellipse cx={43} cy={32} rx={10} ry={12} fill="#1a1a2e" stroke="#3d3d5c" strokeWidth={0.8} />
        <ellipse cx={43} cy={32} rx={6} ry={8} fill="#12121e" />
      </g>

      {/* ── Coffee mug ─────────────────────────────────────────── */}
      <g transform="translate(870, 432)">
        {/* Mug body */}
        <rect x={0} y={0} width={20} height={24} rx={3} fill="#1e1c30" stroke="#2a2a40" strokeWidth={0.6} />
        {/* Handle */}
        <path
          d="M 20 6 Q 30 6, 30 14 Q 30 22, 20 22"
          fill="none" stroke="#2a2a40" strokeWidth={1.2}
        />
        {/* Liquid surface */}
        <ellipse cx={10} cy={4} rx={8} ry={2} fill="rgba(139,92,246,0.08)" />
        {/* Steam wisps */}
        <path d="M 7 -2 Q 5 -8, 8 -12" fill="none" stroke="rgba(255,255,255,0.06)" strokeWidth={0.5} />
        <path d="M 13 -1 Q 15 -7, 12 -11" fill="none" stroke="rgba(255,255,255,0.04)" strokeWidth={0.5} />
      </g>

      {/* ── Cable tray (under desk) ────────────────────────────── */}
      <rect x={350} y={484} width={300} height={6} rx={2} fill="#0f0e1e" stroke="rgba(100,100,140,0.06)" strokeWidth={0.4} />
    </g>
  );
}
