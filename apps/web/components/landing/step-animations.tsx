"use client"

import { useId } from "react"

// ─── ChatAnimation (Step 1: Code with AI) ─────────────────────

export function ChatAnimation({ isVisible }: { isVisible: boolean }) {
  const id = useId()
  const prefix = `chat-${id.replace(/:/g, "")}`

  return (
    <svg
      viewBox="0 0 40 40"
      width={40}
      height={40}
      xmlns="http://www.w3.org/2000/svg"
      role="img"
      aria-label="Chat animation showing two alternating message bubbles"
    >
      <style>{`
        @media (prefers-reduced-motion: no-preference) {
          .${prefix}-bubble1 {
            opacity: 0;
            transform: translateX(-10px);
            animation: ${isVisible ? `${prefix}-b1 4s ease-in-out infinite` : "none"};
          }

          @keyframes ${prefix}-b1 {
            0%       { opacity: 0; transform: translateX(-10px); }
            10%      { opacity: 1; transform: translateX(0); }
            35%      { opacity: 1; transform: translateX(0); }
            45%      { opacity: 1; transform: translateX(0); }
            85%      { opacity: 1; transform: translateX(0); }
            95%      { opacity: 0; transform: translateX(0); }
            100%     { opacity: 0; transform: translateX(-10px); }
          }

          .${prefix}-bubble2 {
            opacity: 0;
            transform: translateX(10px);
            animation: ${isVisible ? `${prefix}-b2 4s ease-in-out infinite` : "none"};
          }

          @keyframes ${prefix}-b2 {
            0%       { opacity: 0; transform: translateX(10px); }
            37%      { opacity: 0; transform: translateX(10px); }
            47%      { opacity: 1; transform: translateX(0); }
            85%      { opacity: 1; transform: translateX(0); }
            95%      { opacity: 0; transform: translateX(0); }
            100%     { opacity: 0; transform: translateX(10px); }
          }

          .${prefix}-dot1 {
            animation: ${isVisible ? `${prefix}-dots 4s ease-in-out infinite` : "none"};
          }
          .${prefix}-dot2 {
            animation: ${isVisible ? `${prefix}-dots 4s ease-in-out infinite 0.15s` : "none"};
          }
          .${prefix}-dot3 {
            animation: ${isVisible ? `${prefix}-dots 4s ease-in-out infinite 0.3s` : "none"};
          }

          @keyframes ${prefix}-dots {
            0%       { transform: scale(0.5); opacity: 0; }
            27%      { transform: scale(0.5); opacity: 0; }
            32%      { transform: scale(1); opacity: 0.8; }
            37%      { transform: scale(0.5); opacity: 0; }
            100%     { transform: scale(0.5); opacity: 0; }
          }
        }

        @media (prefers-reduced-motion: reduce) {
          .${prefix}-bubble1 {
            opacity: 1 !important;
            transform: none !important;
            animation: none !important;
          }
          .${prefix}-bubble2 {
            opacity: 1 !important;
            transform: none !important;
            animation: none !important;
          }
          .${prefix}-dot1,
          .${prefix}-dot2,
          .${prefix}-dot3 {
            opacity: 0 !important;
            animation: none !important;
          }
        }
      `}</style>

      {/* Bubble 1 (Human) — left side */}
      <g className={`${prefix}-bubble1`}>
        <rect
          x={4}
          y={8}
          width={18}
          height={10}
          rx={3}
          ry={3}
          fill="rgba(139,92,246,0.6)"
        />
        {/* Small speech tail */}
        <polygon points="6,18 4,21 10,18" fill="rgba(139,92,246,0.6)" />
      </g>

      {/* Typing indicator dots — centered between bubbles */}
      <circle cx={17} cy={20} r={1} fill="rgba(148,163,184,0.6)" className={`${prefix}-dot1`} />
      <circle cx={20} cy={20} r={1} fill="rgba(148,163,184,0.6)" className={`${prefix}-dot2`} />
      <circle cx={23} cy={20} r={1} fill="rgba(148,163,184,0.6)" className={`${prefix}-dot3`} />

      {/* Bubble 2 (AI) — right side */}
      <g className={`${prefix}-bubble2`}>
        <rect
          x={18}
          y={22}
          width={18}
          height={10}
          rx={3}
          ry={3}
          fill="rgba(148,163,184,0.4)"
        />
        {/* Small speech tail */}
        <polygon points="34,32 36,35 30,32" fill="rgba(148,163,184,0.4)" />
      </g>
    </svg>
  )
}

// ─── ScanAnimation (Step 2: Extract) ──────────────────────────

export function ScanAnimation({ isVisible }: { isVisible: boolean }) {
  const id = useId()
  const prefix = `scan-${id.replace(/:/g, "")}`

  return (
    <svg
      viewBox="0 0 40 40"
      width={40}
      height={40}
      xmlns="http://www.w3.org/2000/svg"
      role="img"
      aria-label="Scanning animation showing a document being analyzed"
    >
      <defs>
        <linearGradient id={`${prefix}-grad`} x1="0%" y1="0%" x2="100%" y2="0%">
          <stop offset="0%" stopColor="rgba(139,92,246,0)" />
          <stop offset="30%" stopColor="rgba(139,92,246,0.6)" />
          <stop offset="70%" stopColor="rgba(167,139,250,0.6)" />
          <stop offset="100%" stopColor="rgba(139,92,246,0)" />
        </linearGradient>
      </defs>

      <style>{`
        @media (prefers-reduced-motion: no-preference) {
          .${prefix}-bar {
            animation: ${isVisible ? `${prefix}-sweep 3s ease-in-out infinite` : "none"};
          }

          @keyframes ${prefix}-sweep {
            0%   { transform: translateY(0); }
            60%  { transform: translateY(18px); }
            70%  { transform: translateY(18px); }
            100% { transform: translateY(0); }
          }

          .${prefix}-line1 {
            animation: ${isVisible ? `${prefix}-flash1 3s ease-in-out infinite` : "none"};
          }
          .${prefix}-line2 {
            animation: ${isVisible ? `${prefix}-flash2 3s ease-in-out infinite` : "none"};
          }
          .${prefix}-line3 {
            animation: ${isVisible ? `${prefix}-flash3 3s ease-in-out infinite` : "none"};
          }
          .${prefix}-line4 {
            animation: ${isVisible ? `${prefix}-flash4 3s ease-in-out infinite` : "none"};
          }

          @keyframes ${prefix}-flash1 {
            0%, 8%   { stroke: rgba(148,163,184,0.3); }
            12%      { stroke: rgba(139,92,246,0.5); }
            20%      { stroke: rgba(148,163,184,0.3); }
            100%     { stroke: rgba(148,163,184,0.3); }
          }
          @keyframes ${prefix}-flash2 {
            0%, 18%  { stroke: rgba(148,163,184,0.3); }
            22%      { stroke: rgba(139,92,246,0.5); }
            30%      { stroke: rgba(148,163,184,0.3); }
            100%     { stroke: rgba(148,163,184,0.3); }
          }
          @keyframes ${prefix}-flash3 {
            0%, 30%  { stroke: rgba(148,163,184,0.3); }
            34%      { stroke: rgba(139,92,246,0.5); }
            42%      { stroke: rgba(148,163,184,0.3); }
            100%     { stroke: rgba(148,163,184,0.3); }
          }
          @keyframes ${prefix}-flash4 {
            0%, 42%  { stroke: rgba(148,163,184,0.3); }
            46%      { stroke: rgba(139,92,246,0.5); }
            54%      { stroke: rgba(148,163,184,0.3); }
            100%     { stroke: rgba(148,163,184,0.3); }
          }
        }

        @media (prefers-reduced-motion: reduce) {
          .${prefix}-bar {
            animation: none !important;
          }
          .${prefix}-line1,
          .${prefix}-line2,
          .${prefix}-line3,
          .${prefix}-line4 {
            animation: none !important;
            stroke: rgba(148,163,184,0.3) !important;
          }
        }
      `}</style>

      {/* Document body */}
      <rect
        x={6}
        y={5}
        width={28}
        height={30}
        rx={3}
        ry={3}
        fill="rgba(255,255,255,0.03)"
        stroke="rgba(255,255,255,0.1)"
        strokeWidth={1}
      />

      {/* Text lines */}
      <line x1={10} y1={12} x2={30} y2={12} strokeWidth={1.5} strokeLinecap="round" className={`${prefix}-line1`} stroke="rgba(148,163,184,0.3)" />
      <line x1={10} y1={17} x2={30} y2={17} strokeWidth={1.5} strokeLinecap="round" className={`${prefix}-line2`} stroke="rgba(148,163,184,0.3)" />
      <line x1={10} y1={22} x2={30} y2={22} strokeWidth={1.5} strokeLinecap="round" className={`${prefix}-line3`} stroke="rgba(148,163,184,0.3)" />
      <line x1={10} y1={27} x2={26} y2={27} strokeWidth={1.5} strokeLinecap="round" className={`${prefix}-line4`} stroke="rgba(148,163,184,0.3)" />

      {/* Scan bar */}
      <rect
        x={8}
        y={10}
        width={24}
        height={2}
        rx={1}
        fill={`url(#${prefix}-grad)`}
        className={`${prefix}-bar`}
      />
    </svg>
  )
}

// ─── MergeAnimation (Step 3: Resolve) ─────────────────────────

export function MergeAnimation({ isVisible }: { isVisible: boolean }) {
  const id = useId()
  const prefix = `merge-${id.replace(/:/g, "")}`

  return (
    <svg
      viewBox="0 0 40 40"
      width={40}
      height={40}
      xmlns="http://www.w3.org/2000/svg"
      role="img"
      aria-label="Merge animation showing two nodes combining into one"
    >
      <style>{`
        @media (prefers-reduced-motion: no-preference) {
          .${prefix}-left {
            animation: ${isVisible ? `${prefix}-moveL 3.5s ease-in-out infinite` : "none"};
          }

          @keyframes ${prefix}-moveL {
            0%       { transform: translate(0, 0); opacity: 1; }
            17%      { transform: translate(8px, 0); opacity: 1; }
            23%      { transform: translate(8px, 0); opacity: 0; }
            80%      { transform: translate(8px, 0); opacity: 0; }
            88%      { transform: translate(0, 0); opacity: 1; }
            100%     { transform: translate(0, 0); opacity: 1; }
          }

          .${prefix}-right {
            animation: ${isVisible ? `${prefix}-moveR 3.5s ease-in-out infinite` : "none"};
          }

          @keyframes ${prefix}-moveR {
            0%       { transform: translate(0, 0); opacity: 1; }
            17%      { transform: translate(-8px, 0); opacity: 1; }
            23%      { transform: translate(-8px, 0); opacity: 0; }
            80%      { transform: translate(-8px, 0); opacity: 0; }
            88%      { transform: translate(0, 0); opacity: 1; }
            100%     { transform: translate(0, 0); opacity: 1; }
          }

          .${prefix}-merged {
            opacity: 0;
            transform-origin: 20px 20px;
            animation: ${isVisible ? `${prefix}-grow 3.5s ease-in-out infinite` : "none"};
          }

          @keyframes ${prefix}-grow {
            0%       { opacity: 0; transform: scale(0.5); }
            17%      { opacity: 0; transform: scale(0.5); }
            23%      { opacity: 1; transform: scale(1.15); }
            29%      { opacity: 1; transform: scale(1); }
            80%      { opacity: 1; transform: scale(1); }
            86%      { opacity: 0; transform: scale(0.5); }
            100%     { opacity: 0; transform: scale(0.5); }
          }

          .${prefix}-check {
            opacity: 0;
            animation: ${isVisible ? `${prefix}-tick 3.5s ease-in-out infinite` : "none"};
          }

          @keyframes ${prefix}-tick {
            0%       { opacity: 0; }
            26%      { opacity: 0; }
            31%      { opacity: 1; }
            74%      { opacity: 1; }
            80%      { opacity: 0; }
            100%     { opacity: 0; }
          }
        }

        @media (prefers-reduced-motion: reduce) {
          .${prefix}-left,
          .${prefix}-right {
            opacity: 1 !important;
            transform: none !important;
            animation: none !important;
          }
          .${prefix}-merged,
          .${prefix}-check {
            opacity: 0 !important;
            animation: none !important;
          }
        }
      `}</style>

      {/* Left circle */}
      <circle
        cx={12}
        cy={20}
        r={6}
        fill="rgba(251,146,60,0.3)"
        stroke="rgba(251,146,60,0.5)"
        strokeWidth={1}
        className={`${prefix}-left`}
      />

      {/* Right circle */}
      <circle
        cx={28}
        cy={20}
        r={6}
        fill="rgba(251,146,60,0.3)"
        stroke="rgba(251,146,60,0.5)"
        strokeWidth={1}
        className={`${prefix}-right`}
      />

      {/* Merged circle (appears at center) */}
      <circle
        cx={20}
        cy={20}
        r={7}
        fill="rgba(251,146,60,0.3)"
        stroke="rgba(251,146,60,0.5)"
        strokeWidth={1.5}
        className={`${prefix}-merged`}
      />

      {/* Checkmark */}
      <path
        d="M16.5 20 L19 22.5 L24 17.5"
        fill="none"
        stroke="rgba(74,222,128,0.8)"
        strokeWidth={1.5}
        strokeLinecap="round"
        strokeLinejoin="round"
        className={`${prefix}-check`}
      />
    </svg>
  )
}

// ─── GraphAnimation (Step 4: Visualize) ───────────────────────

export function GraphAnimation({ isVisible }: { isVisible: boolean }) {
  const id = useId()
  const prefix = `graph-${id.replace(/:/g, "")}`

  // Edge lengths for strokeDasharray/offset
  const horizontal = 20 // (30-10)
  const vertical = 20 // (30-10)
  const diagonal = Math.sqrt(20 * 20 + 20 * 20) // ~28.28

  return (
    <svg
      viewBox="0 0 40 40"
      width={40}
      height={40}
      xmlns="http://www.w3.org/2000/svg"
      role="img"
      aria-label="Graph animation showing nodes connecting with edges"
    >
      <style>{`
        @media (prefers-reduced-motion: no-preference) {
          .${prefix}-edge1 {
            stroke-dasharray: ${horizontal};
            stroke-dashoffset: ${horizontal};
            animation: ${isVisible ? `${prefix}-draw1 4s ease-in-out infinite` : "none"};
          }
          .${prefix}-edge2 {
            stroke-dasharray: ${vertical};
            stroke-dashoffset: ${vertical};
            animation: ${isVisible ? `${prefix}-draw2 4s ease-in-out infinite` : "none"};
          }
          .${prefix}-edge3 {
            stroke-dasharray: ${vertical};
            stroke-dashoffset: ${vertical};
            animation: ${isVisible ? `${prefix}-draw3 4s ease-in-out infinite` : "none"};
          }
          .${prefix}-edge4 {
            stroke-dasharray: ${horizontal};
            stroke-dashoffset: ${horizontal};
            animation: ${isVisible ? `${prefix}-draw4 4s ease-in-out infinite` : "none"};
          }
          .${prefix}-edge5 {
            stroke-dasharray: ${diagonal.toFixed(2)};
            stroke-dashoffset: ${diagonal.toFixed(2)};
            animation: ${isVisible ? `${prefix}-draw5 4s ease-in-out infinite` : "none"};
          }

          @keyframes ${prefix}-draw1 {
            0%       { stroke-dashoffset: ${horizontal}; opacity: 1; }
            7.5%     { stroke-dashoffset: 0; opacity: 1; }
            62.5%    { stroke-dashoffset: 0; opacity: 1; }
            75%      { stroke-dashoffset: 0; opacity: 0; }
            100%     { stroke-dashoffset: ${horizontal}; opacity: 0; }
          }
          @keyframes ${prefix}-draw2 {
            0%, 10%  { stroke-dashoffset: ${vertical}; opacity: 0; }
            10.1%    { opacity: 1; stroke-dashoffset: ${vertical}; }
            17.5%    { stroke-dashoffset: 0; opacity: 1; }
            62.5%    { stroke-dashoffset: 0; opacity: 1; }
            75%      { stroke-dashoffset: 0; opacity: 0; }
            100%     { stroke-dashoffset: ${vertical}; opacity: 0; }
          }
          @keyframes ${prefix}-draw3 {
            0%, 20%  { stroke-dashoffset: ${vertical}; opacity: 0; }
            20.1%    { opacity: 1; stroke-dashoffset: ${vertical}; }
            27.5%    { stroke-dashoffset: 0; opacity: 1; }
            62.5%    { stroke-dashoffset: 0; opacity: 1; }
            75%      { stroke-dashoffset: 0; opacity: 0; }
            100%     { stroke-dashoffset: ${vertical}; opacity: 0; }
          }
          @keyframes ${prefix}-draw4 {
            0%, 30%  { stroke-dashoffset: ${horizontal}; opacity: 0; }
            30.1%    { opacity: 1; stroke-dashoffset: ${horizontal}; }
            37.5%    { stroke-dashoffset: 0; opacity: 1; }
            62.5%    { stroke-dashoffset: 0; opacity: 1; }
            75%      { stroke-dashoffset: 0; opacity: 0; }
            100%     { stroke-dashoffset: ${horizontal}; opacity: 0; }
          }
          @keyframes ${prefix}-draw5 {
            0%, 40%  { stroke-dashoffset: ${diagonal.toFixed(2)}; opacity: 0; }
            40.1%    { opacity: 1; stroke-dashoffset: ${diagonal.toFixed(2)}; }
            47.5%    { stroke-dashoffset: 0; opacity: 1; }
            62.5%    { stroke-dashoffset: 0; opacity: 1; }
            75%      { stroke-dashoffset: 0; opacity: 0; }
            100%     { stroke-dashoffset: ${diagonal.toFixed(2)}; opacity: 0; }
          }
        }

        @media (prefers-reduced-motion: reduce) {
          .${prefix}-edge1,
          .${prefix}-edge2,
          .${prefix}-edge3,
          .${prefix}-edge4,
          .${prefix}-edge5 {
            stroke-dashoffset: 0 !important;
            stroke-dasharray: none !important;
            opacity: 1 !important;
            animation: none !important;
          }
        }
      `}</style>

      {/* Edges (drawn behind dots) */}
      <line x1={10} y1={10} x2={30} y2={10} stroke="rgba(139,92,246,0.3)" strokeWidth={1} className={`${prefix}-edge1`} />
      <line x1={30} y1={10} x2={30} y2={30} stroke="rgba(139,92,246,0.3)" strokeWidth={1} className={`${prefix}-edge2`} />
      <line x1={10} y1={10} x2={10} y2={30} stroke="rgba(139,92,246,0.3)" strokeWidth={1} className={`${prefix}-edge3`} />
      <line x1={10} y1={30} x2={30} y2={30} stroke="rgba(139,92,246,0.3)" strokeWidth={1} className={`${prefix}-edge4`} />
      <line x1={10} y1={10} x2={30} y2={30} stroke="rgba(139,92,246,0.3)" strokeWidth={1} className={`${prefix}-edge5`} />

      {/* Dots (always visible) */}
      <circle cx={10} cy={10} r={3} fill="rgba(139,92,246,0.5)" />
      <circle cx={30} cy={10} r={3} fill="rgba(139,92,246,0.5)" />
      <circle cx={10} cy={30} r={3} fill="rgba(139,92,246,0.5)" />
      <circle cx={30} cy={30} r={3} fill="rgba(139,92,246,0.5)" />
    </svg>
  )
}
