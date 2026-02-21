"use client"

import { useEffect, useState } from "react"

/* ------------------------------------------------------------------ */
/*  Types                                                              */
/* ------------------------------------------------------------------ */

interface ChatMessage {
  role: "human" | "ai"
  text: string
  delay: number // ms before typing indicator starts
}

interface TraceField {
  label: string
  value: string
  delay: number // ms before fade-in
  highlight?: boolean
}

/* ------------------------------------------------------------------ */
/*  Static data                                                        */
/* ------------------------------------------------------------------ */

const MESSAGES: ChatMessage[] = [
  {
    role: "human",
    text: "The agent needs to check prior decisions before acting",
    delay: 0,
  },
  {
    role: "ai",
    text: "I'll add continuum_check as a Strands tool — Neo4j queries traced through Datadog.",
    delay: 1500,
  },
  {
    role: "human",
    text: "Ship it. Every LLM call should be observable.",
    delay: 3000,
  },
]

const TRACE_FIELDS: TraceField[] = [
  { label: "Model", value: "Claude Sonnet via Bedrock", delay: 4000 },
  { label: "Latency", value: "1.2s (p50)", delay: 4800 },
  { label: "Tokens", value: "847 in / 234 out", delay: 5600 },
  { label: "Confidence", value: "0.94", delay: 6400, highlight: true },
  { label: "Cost", value: "$0.0043 per decision", delay: 7200 },
]

const CARD_COMPLETE_DELAY = 8000

/* ------------------------------------------------------------------ */
/*  Typing indicator                                                   */
/* ------------------------------------------------------------------ */

function TypingIndicator({ align }: { align: "left" | "right" }) {
  return (
    <div
      className={`flex items-center gap-1 ${align === "right" ? "justify-end" : "justify-start"}`}
    >
      <div
        className={`flex items-center gap-1 rounded-2xl px-4 py-3 ${
          align === "right"
            ? "bg-gradient-to-r from-violet-600 to-fuchsia-600"
            : "bg-white/[0.05] border border-white/[0.08]"
        }`}
      >
        {[0, 1, 2].map((i) => (
          <span
            key={i}
            className="block h-1 w-1 rounded-full bg-slate-400"
            style={{
              animation: "typing-dot 1s ease-in-out infinite",
              animationDelay: `${i * 150}ms`,
            }}
          />
        ))}
      </div>
    </div>
  )
}

/* ------------------------------------------------------------------ */
/*  Chat bubble                                                        */
/* ------------------------------------------------------------------ */

function ChatBubble({
  message,
  visible,
}: {
  message: ChatMessage
  visible: boolean
}) {
  const isHuman = message.role === "human"

  return (
    <div
      className={`flex ${isHuman ? "justify-end" : "justify-start"} transition-opacity duration-500 ${
        visible ? "opacity-100" : "opacity-0"
      }`}
    >
      <div
        className={`max-w-[85%] px-4 py-3 text-sm ${
          isHuman
            ? "rounded-2xl rounded-br-sm bg-gradient-to-r from-violet-600 to-fuchsia-600 text-white"
            : "rounded-2xl rounded-bl-sm border border-white/[0.08] bg-white/[0.05] text-slate-200"
        }`}
      >
        {message.text}
      </div>
    </div>
  )
}

/* ------------------------------------------------------------------ */
/*  Decision trace field row                                           */
/* ------------------------------------------------------------------ */

function TraceFieldRow({
  field,
  visible,
  isLast,
}: {
  field: TraceField
  visible: boolean
  isLast: boolean
}) {
  return (
    <div
      className={`transition-opacity duration-500 ${visible ? "opacity-100" : "opacity-0"} ${
        !isLast ? "border-b border-white/[0.06] pb-3 mb-3" : ""
      }`}
    >
      <div
        className={`text-xs uppercase tracking-wide text-slate-500 mb-1 ${
          visible ? "animate-[label-glow_0.6s_ease-out]" : ""
        }`}
      >
        {field.label}
      </div>
      <div
        className={`text-sm ${
          field.highlight
            ? "font-semibold text-violet-400"
            : "text-slate-200"
        }`}
      >
        {field.value}
      </div>
    </div>
  )
}

/* ------------------------------------------------------------------ */
/*  Main component                                                     */
/* ------------------------------------------------------------------ */

export function ConversationExtract({
  isVisible,
}: {
  isVisible: boolean
}) {
  // Track which messages are in "typing" state and which are "shown"
  const [typingIndex, setTypingIndex] = useState<number | null>(null)
  const [shownMessages, setShownMessages] = useState<boolean[]>(
    () => MESSAGES.map(() => false),
  )

  // Track which trace fields are visible
  const [shownFields, setShownFields] = useState<boolean[]>(
    () => TRACE_FIELDS.map(() => false),
  )

  // Card complete state (checkmark + border glow)
  const [cardComplete, setCardComplete] = useState(false)

  // Reduced motion preference
  const [prefersReducedMotion, setPrefersReducedMotion] = useState(false)

  useEffect(() => {
    const mq = window.matchMedia("(prefers-reduced-motion: reduce)")
    setPrefersReducedMotion(mq.matches)
    const handler = (e: MediaQueryListEvent) => setPrefersReducedMotion(e.matches)
    mq.addEventListener("change", handler)
    return () => mq.removeEventListener("change", handler)
  }, [])

  // Reset when visibility changes
  useEffect(() => {
    if (!isVisible) {
      setTypingIndex(null)
      setShownMessages(MESSAGES.map(() => false))
      setShownFields(TRACE_FIELDS.map(() => false))
      setCardComplete(false)
      return
    }

    // If reduced motion, show everything immediately
    if (prefersReducedMotion) {
      setShownMessages(MESSAGES.map(() => true))
      setShownFields(TRACE_FIELDS.map(() => true))
      setCardComplete(true)
      return
    }

    const timers: ReturnType<typeof setTimeout>[] = []

    // Schedule chat messages with typing indicators
    MESSAGES.forEach((msg, i) => {
      // Show typing indicator 0.5s before the message
      const typingTimer = setTimeout(() => {
        setTypingIndex(i)
      }, msg.delay)
      timers.push(typingTimer)

      // Show the actual message after 500ms typing
      const messageTimer = setTimeout(() => {
        setTypingIndex((prev) => (prev === i ? null : prev))
        setShownMessages((prev) => {
          const next = [...prev]
          next[i] = true
          return next
        })
      }, msg.delay + 500)
      timers.push(messageTimer)
    })

    // Schedule trace fields
    TRACE_FIELDS.forEach((field, i) => {
      const timer = setTimeout(() => {
        setShownFields((prev) => {
          const next = [...prev]
          next[i] = true
          return next
        })
      }, field.delay)
      timers.push(timer)
    })

    // Schedule card completion
    const completeTimer = setTimeout(() => {
      setCardComplete(true)
    }, CARD_COMPLETE_DELAY)
    timers.push(completeTimer)

    return () => {
      timers.forEach(clearTimeout)
    }
  }, [isVisible, prefersReducedMotion])

  // Determine overall visibility for the wrapper
  const wrapperOpacity = isVisible ? "opacity-100" : "opacity-0"

  return (
    <>
      {/* Keyframe animations injected via style tag */}
      <style>{`
        @keyframes typing-dot {
          0%, 100% { transform: scale(1); opacity: 0.4; }
          50% { transform: scale(1.5); opacity: 1; }
        }
        @keyframes label-glow {
          0% { text-shadow: 0 0 8px rgba(139, 92, 246, 0.8); }
          100% { text-shadow: 0 0 0px rgba(139, 92, 246, 0); }
        }
      `}</style>

      <div
        aria-hidden="true"
        className={`mx-auto max-w-[650px] transition-opacity duration-500 ${wrapperOpacity}`}
      >
        <div className="grid grid-cols-1 gap-6 md:grid-cols-2">
          {/* ---- Left column: Chat messages ---- */}
          <div className="flex flex-col gap-3">
            {MESSAGES.map((msg, i) => {
              const isTyping = typingIndex === i
              const isShown = shownMessages[i]

              return (
                <div key={i}>
                  {isTyping && !isShown && (
                    <TypingIndicator
                      align={msg.role === "human" ? "right" : "left"}
                    />
                  )}
                  {isShown && (
                    <ChatBubble message={msg} visible={isShown} />
                  )}
                </div>
              )
            })}
          </div>

          {/* ---- Right column: Decision trace card ---- */}
          <div className="relative">
            <div
              className={`rounded-2xl border bg-white/[0.02] p-5 transition-colors duration-700 ${
                cardComplete
                  ? "border-violet-500/30"
                  : "border-white/[0.08]"
              }`}
            >
              {/* Checkmark indicator */}
              {cardComplete && (
                <div className="absolute right-3 top-3 flex h-6 w-6 items-center justify-center rounded-full text-emerald-400 transition-opacity duration-500">
                  <svg
                    width="16"
                    height="16"
                    viewBox="0 0 16 16"
                    fill="none"
                    xmlns="http://www.w3.org/2000/svg"
                    aria-hidden="true"
                  >
                    <path
                      d="M3 8.5L6.5 12L13 4"
                      stroke="currentColor"
                      strokeWidth="2"
                      strokeLinecap="round"
                      strokeLinejoin="round"
                    />
                  </svg>
                </div>
              )}

              {/* Trace fields */}
              {TRACE_FIELDS.map((field, i) => (
                <TraceFieldRow
                  key={field.label}
                  field={field}
                  visible={shownFields[i]}
                  isLast={i === TRACE_FIELDS.length - 1}
                />
              ))}
            </div>
          </div>
        </div>
      </div>
    </>
  )
}
