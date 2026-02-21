"use client"

import { useEffect, useRef, useState, useCallback } from "react"

// ── Types ──────────────────────────────────────────────────────────

interface DecisionCard {
  label: string
  borderColor: string
}

// ── Constants ──────────────────────────────────────────────────────

const FILES = [
  "continuum_check.py",
  "continuum_remember.py",
  "continuum_search.py",
]

const FILE_SCAN_TIMES = [1.0, 2.0, 3.0] // seconds after isVisible

const DECISION_CARDS: DecisionCard[] = [
  { label: "Query prior art", borderColor: "border-violet-500" },
  { label: "Store decision", borderColor: "border-orange-500" },
  { label: "Recall context", borderColor: "border-violet-500" },
]

const COUNTER_STEPS = [
  { time: 4.5, value: 3, suffix: "tool calls" },
  { time: 5.5, value: 7, suffix: "tool calls" },
  { time: 6.5, value: 12, suffix: "tool calls traced" },
]

// ── CSS Keyframes (injected once) ──────────────────────────────────

const KEYFRAMES_ID = "file-scan-keyframes"

const KEYFRAMES_CSS = `
@keyframes fileScanLine {
  0% { transform: translateX(-100%); }
  100% { transform: translateX(100%); }
}

@keyframes decisionCardFloat {
  0% {
    opacity: 0;
    transform: translateY(0px);
  }
  30% {
    opacity: 1;
    transform: translateY(-20px);
  }
  100% {
    opacity: 0.7;
    transform: translateY(-50px);
  }
}
`

function injectKeyframes() {
  if (typeof document === "undefined") return
  if (document.getElementById(KEYFRAMES_ID)) return
  const style = document.createElement("style")
  style.id = KEYFRAMES_ID
  style.textContent = KEYFRAMES_CSS
  document.head.appendChild(style)
}

// ── Component ──────────────────────────────────────────────────────

export function FileScan({ isVisible }: { isVisible: boolean }) {
  const [fileVisible, setFileVisible] = useState<boolean[]>([false, false, false])
  const [scanning, setScanning] = useState<number | null>(null)
  const [scanned, setScanned] = useState<boolean[]>([false, false, false])
  const [activeCards, setActiveCards] = useState<number[]>([])
  const [counterValue, setCounterValue] = useState<{ value: number; suffix: string } | null>(null)
  const [prefersReducedMotion, setPrefersReducedMotion] = useState(false)
  const timersRef = useRef<ReturnType<typeof setTimeout>[]>([])

  // Check reduced motion preference
  useEffect(() => {
    if (typeof window === "undefined") return
    const mq = window.matchMedia("(prefers-reduced-motion: reduce)")
    setPrefersReducedMotion(mq.matches)
    const handler = (e: MediaQueryListEvent) => setPrefersReducedMotion(e.matches)
    mq.addEventListener("change", handler)
    return () => mq.removeEventListener("change", handler)
  }, [])

  // Inject keyframes on mount
  useEffect(() => {
    injectKeyframes()
  }, [])

  // Clear all timers on unmount
  const clearAllTimers = useCallback(() => {
    timersRef.current.forEach(clearTimeout)
    timersRef.current = []
  }, [])

  useEffect(() => {
    return clearAllTimers
  }, [clearAllTimers])

  // Reset state when not visible
  useEffect(() => {
    if (!isVisible) {
      clearAllTimers()
      setFileVisible([false, false, false])
      setScanning(null)
      setScanned([false, false, false])
      setActiveCards([])
      setCounterValue(null)
    }
  }, [isVisible, clearAllTimers])

  // Run animation sequence when visible
  useEffect(() => {
    if (!isVisible || prefersReducedMotion) return

    clearAllTimers()
    const timers: ReturnType<typeof setTimeout>[] = []

    // Phase 1: File tree fade-in (staggered 0.3s)
    FILES.forEach((_, i) => {
      const t = setTimeout(() => {
        setFileVisible((prev) => {
          const next = [...prev]
          next[i] = true
          return next
        })
      }, i * 300)
      timers.push(t)
    })

    // Phase 1: Scan lines sweep across files
    FILE_SCAN_TIMES.forEach((time, i) => {
      // Start scanning
      const scanStart = setTimeout(() => {
        setScanning(i)
      }, time * 1000)
      timers.push(scanStart)

      // End scanning, mark as scanned
      const scanEnd = setTimeout(() => {
        setScanning((current) => (current === i ? null : current))
        setScanned((prev) => {
          const next = [...prev]
          next[i] = true
          return next
        })
      }, time * 1000 + 800)
      timers.push(scanEnd)
    })

    // Phase 2: Decision cards emerge (4.0s, 4.6s, 5.2s)
    DECISION_CARDS.forEach((_, i) => {
      const t = setTimeout(() => {
        setActiveCards((prev) => [...prev, i])
      }, 4000 + i * 600)
      timers.push(t)
    })

    // Counter ticks
    COUNTER_STEPS.forEach(({ time, value, suffix }) => {
      const t = setTimeout(() => {
        setCounterValue({ value, suffix })
      }, time * 1000)
      timers.push(t)
    })

    timersRef.current = timers
  }, [isVisible, prefersReducedMotion, clearAllTimers])

  // ── Reduced motion: static view ──────────────────────────────────

  if (prefersReducedMotion) {
    return (
      <div
        aria-hidden="true"
        className="relative overflow-hidden min-h-[250px] max-w-[450px] mx-auto"
      >
        <div className="font-mono text-xs leading-relaxed p-4">
          <span className="text-slate-400">strands-agent/tools/</span>
          <br />
          <span className="text-slate-400">
            {"├── "}mcp-servers/
          </span>
          <br />
          {FILES.map((file, i) => (
            <div key={file}>
              <span className="text-slate-400">
                {"│   "}
                {i < FILES.length - 1 ? "├── " : "└── "}
              </span>
              <span className="text-slate-200">{file}</span>
            </div>
          ))}
        </div>
        <div className="absolute bottom-3 right-3 text-xs text-slate-500">
          12 tool calls traced
        </div>
      </div>
    )
  }

  // ── Full animation view ──────────────────────────────────────────

  return (
    <div
      aria-hidden="true"
      className="relative overflow-hidden min-h-[250px] max-w-[450px] mx-auto"
    >
      {/* File tree */}
      <div className="font-mono text-xs leading-relaxed p-4 select-none">
        <span className="text-slate-400">strands-agent/tools/</span>
        <br />
        <span className="text-slate-400">
          {"├── "}mcp-servers/
        </span>
        <br />
        {FILES.map((file, i) => {
          const isScanned = scanned[i]
          const isScanning = scanning === i
          const isFileVisible = fileVisible[i]
          const isLast = i === FILES.length - 1

          return (
            <div
              key={file}
              className="relative overflow-hidden"
              style={{
                opacity: isFileVisible ? 1 : 0,
                transition: "opacity 0.4s ease-out",
              }}
            >
              <span className="text-slate-400">
                {"│   "}
                {isLast ? "└── " : "├── "}
              </span>
              <span
                className={isScanned ? "text-slate-200" : "text-slate-500"}
                style={{ transition: "color 0.5s ease-out" }}
              >
                {file}
              </span>

              {/* Scan line — 2px tall, sweeps left-to-right */}
              {isScanning && (
                <div
                  className="absolute inset-x-0 top-1/2 -translate-y-1/2 h-[2px] pointer-events-none"
                  style={{
                    animation: "fileScanLine 0.8s ease-in-out forwards",
                  }}
                >
                  <div className="h-full w-full bg-gradient-to-r from-transparent via-violet-500 to-transparent" />
                </div>
              )}
            </div>
          )
        })}
      </div>

      {/* Decision cards — floating upward */}
      <div className="relative mt-2 flex flex-col items-center gap-2 min-h-[80px]">
        {DECISION_CARDS.map((card, i) => {
          const isActive = activeCards.includes(i)
          if (!isActive) return null

          return (
            <span
              key={card.label}
              className={`
                inline-block text-xs px-3 py-1 rounded-full
                bg-white/[0.03] border ${card.borderColor}
                text-slate-300
              `}
              style={{
                animation: "decisionCardFloat 2s ease-out forwards",
              }}
            >
              {card.label}
            </span>
          )
        })}
      </div>

      {/* Counter */}
      {counterValue && (
        <div
          className="absolute bottom-3 right-3 text-xs text-slate-500"
          style={{
            opacity: 1,
            transition: "opacity 0.3s ease-out",
          }}
        >
          {counterValue.value} {counterValue.suffix}
        </div>
      )}
    </div>
  )
}
