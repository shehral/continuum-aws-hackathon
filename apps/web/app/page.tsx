"use client"

import React, { useState, useEffect, useRef } from "react"
import Link from "next/link"
import { GitBranch, MessageSquare, Scan, Network, Sun, Moon } from "lucide-react"
import { useTheme } from "next-themes"
import { Button } from "@/components/ui/button"
import { HeroConductor } from "@/components/landing/hero-conductor"
import { PulsingNetwork } from "@/components/landing/pulsing-network"
import { ConversationExtract } from "@/components/landing/conversation-extract"
import { FileScan } from "@/components/landing/file-scan"
import { ChatAnimation, ScanAnimation, MergeAnimation, GraphAnimation } from "@/components/landing/step-animations"
import { AmbientParticles } from "@/components/landing/ambient-particles"

// ─── Hooks ───────────────────────────────────────────────

function useScrollAnimation() {
  const ref = useRef<HTMLDivElement>(null)
  const [isVisible, setIsVisible] = useState(false)

  useEffect(() => {
    const el = ref.current
    if (!el) return

    const observer = new IntersectionObserver(
      ([entry]) => {
        if (entry.isIntersecting) {
          setIsVisible(true)
          observer.unobserve(el)
        }
      },
      { threshold: 0.15 }
    )

    observer.observe(el)
    return () => observer.disconnect()
  }, [])

  return { ref, isVisible }
}

function useCountUp(target: number, isVisible: boolean, duration = 2000) {
  const [count, setCount] = useState(0)

  useEffect(() => {
    if (!isVisible) return

    const start = performance.now()
    function tick(now: number) {
      const elapsed = now - start
      const progress = Math.min(elapsed / duration, 1)
      const eased = 1 - Math.pow(1 - progress, 3)
      setCount(Math.floor(eased * target))
      if (progress < 1) requestAnimationFrame(tick)
    }
    requestAnimationFrame(tick)
  }, [isVisible, target, duration])

  return count
}

// ─── Feature Section Component ───────────────────────────

const glowColors = {
  violet: "from-violet-500/20 to-violet-500/5",
  rose: "from-rose-500/20 to-rose-500/5",
  orange: "from-orange-500/20 to-orange-500/5",
} as const

function FeatureSection({
  title,
  description,
  imageSrc,
  imageAlt,
  glowColor,
  imagePosition,
  animation,
}: {
  title: string
  description: string
  imageSrc: string
  imageAlt: string
  glowColor: keyof typeof glowColors
  imagePosition: "left" | "right"
  animation?: (isVisible: boolean) => React.ReactNode
}) {
  const { ref, isVisible } = useScrollAnimation()

  const textBlock = (
    <div className="flex flex-col justify-center">
      <h2 className="text-3xl sm:text-4xl md:text-5xl font-bold tracking-tight mb-6">
        <span className="gradient-text">{title}</span>
      </h2>
      <p className="text-lg text-slate-400 leading-relaxed">{description}</p>
    </div>
  )

  const imageBlock = (
    <div className="relative">
      <div
        className={`absolute -inset-4 bg-gradient-to-br ${glowColors[glowColor]} rounded-3xl blur-2xl`}
        aria-hidden="true"
      />
      <div className="relative space-y-4">
        {animation && (
          <div className="rounded-2xl border border-border overflow-hidden shadow-lg dark:shadow-[0_16px_48px_rgba(0,0,0,0.4)] bg-card p-4 md:p-6">
            {animation(isVisible)}
          </div>
        )}
        <div className="rounded-2xl border border-border overflow-hidden shadow-lg dark:shadow-[0_16px_48px_rgba(0,0,0,0.4)]">
          <img src={imageSrc} alt={imageAlt} className="w-full h-auto" loading="lazy" />
        </div>
      </div>
    </div>
  )

  return (
    <div
      ref={ref}
      className={`max-w-7xl mx-auto px-6 py-16 md:py-24 grid md:grid-cols-2 gap-12 md:gap-16 items-center transition-all duration-700 ${
        isVisible ? "opacity-100 translate-y-0" : "opacity-0 translate-y-8"
      }`}
    >
      {imagePosition === "left" ? (
        <>
          {imageBlock}
          {textBlock}
        </>
      ) : (
        <>
          {textBlock}
          {imageBlock}
        </>
      )}
    </div>
  )
}

// ─── How It Works Component ──────────────────────────────

const steps = [
  {
    number: "01",
    icon: MessageSquare,
    title: "Agent Decides",
    description:
      "Your Strands agent on Bedrock processes a task, checking the Neo4j knowledge graph for prior decisions.",
  },
  {
    number: "02",
    icon: Scan,
    title: "Extract",
    description:
      "Continuum captures the decision context — what the agent chose, why, and which entities were involved.",
  },
  {
    number: "03",
    icon: GitBranch,
    title: "Resolve",
    description:
      "A 7-stage entity resolution pipeline canonicalizes every technology, pattern, and concept into Neo4j.",
  },
  {
    number: "04",
    icon: Network,
    title: "Observe",
    description:
      "Datadog traces every Bedrock call end-to-end. Dashboards show cost, latency, and confidence in real time.",
  },
]

const stepAnimationComponents = [ChatAnimation, ScanAnimation, MergeAnimation, GraphAnimation]

function HowItWorks() {
  const { ref, isVisible } = useScrollAnimation()

  return (
    <section ref={ref} className="relative py-32 overflow-hidden">
      <div className="max-w-7xl mx-auto px-6">
        <div
          className={`text-center mb-16 transition-all duration-700 ${
            isVisible ? "opacity-100 translate-y-0" : "opacity-0 translate-y-8"
          }`}
        >
          <h2 className="text-3xl sm:text-4xl md:text-5xl font-bold tracking-tight mb-4">
            How It <span className="gradient-text">Works</span>
          </h2>
          <p className="text-lg text-slate-400 max-w-2xl mx-auto">
            From conversation to knowledge graph in four steps.
          </p>
        </div>

        <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-6">
          {steps.map((step, i) => (
            <div
              key={step.number}
              className={`relative p-6 rounded-2xl bg-white/[0.02] border border-white/[0.06] backdrop-blur-sm transition-all duration-700 hover:border-violet-500/30 hover:-translate-y-1 ${
                isVisible ? "opacity-100 translate-y-0" : "opacity-0 translate-y-8"
              }`}
              style={{ transitionDelay: isVisible ? `${i * 150}ms` : "0ms" }}
            >
              <span className="text-5xl font-bold text-foreground/[0.06] absolute top-4 right-4 select-none">
                {step.number}
              </span>

              <div className="w-10 h-10 rounded-xl bg-gradient-to-br from-violet-500/20 to-fuchsia-500/10 border border-violet-500/20 flex items-center justify-center mb-4">
                {(() => {
                  const StepAnim = stepAnimationComponents[i]
                  return StepAnim ? <StepAnim isVisible={isVisible} /> : <step.icon className="w-5 h-5 text-violet-400" />
                })()}
              </div>

              <h3 className="text-lg font-semibold mb-2">{step.title}</h3>
              <p className="text-sm text-slate-400 leading-relaxed">{step.description}</p>

              {i < steps.length - 1 && (
                <div
                  className="hidden lg:block absolute top-1/2 -right-3 w-6 h-px bg-gradient-to-r from-violet-500/40 to-transparent"
                  aria-hidden="true"
                />
              )}
            </div>
          ))}
        </div>
      </div>
    </section>
  )
}

// ─── Tech Credibility Component ──────────────────────────

const stats = [
  { value: 838, suffix: "+", label: "Automated Tests" },
  { value: 5, suffix: "", label: "MCP Tools" },
  { value: 3, suffix: "", label: "Sponsor Technologies" },
  { value: 7, suffix: "-Stage", label: "Entity Resolution" },
]

const techStack = [
  "AWS Bedrock",
  "Strands Agents",
  "Datadog",
  "Neo4j",
  "FastAPI",
  "Next.js",
  "Docker",
  "Kubernetes",
  "Claude Sonnet",
]

function StatCard({ stat, isVisible }: { stat: (typeof stats)[number]; isVisible: boolean }) {
  const count = useCountUp(stat.value, isVisible)

  return (
    <div className="p-6 rounded-2xl bg-white/[0.02] border border-white/[0.06] text-center hover:border-violet-500/30 transition-all">
      <div className="stat-number text-3xl md:text-4xl mb-1">
        {count.toLocaleString()}
        {stat.suffix}
      </div>
      <div className="text-sm text-slate-400">{stat.label}</div>
    </div>
  )
}

function TechCredibility() {
  const { ref, isVisible } = useScrollAnimation()

  return (
    <section ref={ref} className="relative py-32">
      <div className="max-w-5xl mx-auto px-6">
        <div
          className={`text-center mb-16 transition-all duration-700 ${
            isVisible ? "opacity-100 translate-y-0" : "opacity-0 translate-y-8"
          }`}
        >
          <h2 className="text-3xl sm:text-4xl md:text-5xl font-bold tracking-tight mb-4">
            Built for <span className="gradient-text">Production</span>
          </h2>
          <p className="text-lg text-slate-400 max-w-2xl mx-auto">
            Enterprise-grade infrastructure behind a research-first product.
          </p>
        </div>

        <div
          className={`grid grid-cols-2 md:grid-cols-4 gap-4 mb-16 transition-all duration-700 ${
            isVisible ? "opacity-100 translate-y-0" : "opacity-0 translate-y-8"
          }`}
          style={{ transitionDelay: isVisible ? "200ms" : "0ms" }}
        >
          {stats.map((stat) => (
            <StatCard key={stat.label} stat={stat} isVisible={isVisible} />
          ))}
        </div>

        <div
          className={`flex flex-wrap justify-center gap-4 transition-all duration-700 ${
            isVisible ? "opacity-100 translate-y-0" : "opacity-0 translate-y-8"
          }`}
          style={{ transitionDelay: isVisible ? "400ms" : "0ms" }}
        >
          {techStack.map((tech) => (
            <div
              key={tech}
              className="px-4 py-2 rounded-xl bg-white/[0.02] border border-white/[0.06] text-sm text-slate-400 hover:text-foreground hover:border-violet-500/30 transition-all"
            >
              {tech}
            </div>
          ))}
        </div>
      </div>
    </section>
  )
}

// ─── Sponsor Showcase Component ──────────────────────────

const sponsors = [
  {
    name: "AWS Bedrock",
    role: "Agent Runtime",
    description: "Strands Agents SDK on Amazon Bedrock",
    glowColor: "from-orange-500/20 to-orange-500/5",
  },
  {
    name: "Anthropic",
    role: "Foundation Model",
    description: "Claude Sonnet powers every agent decision",
    glowColor: "from-amber-500/20 to-amber-500/5",
  },
  {
    name: "Datadog",
    role: "LLM Observability",
    description: "End-to-end tracing for every LLM call",
    glowColor: "from-violet-500/20 to-fuchsia-500/5",
  },
  {
    name: "Neo4j",
    role: "Knowledge Graph",
    description: "Persistent agent memory and entity resolution",
    glowColor: "from-cyan-500/20 to-cyan-500/5",
  },
]

function SponsorLogo({ name }: { name: string }) {
  switch (name) {
    case "AWS Bedrock":
      return (
        <svg viewBox="0 0 256 153" className="h-16 w-auto text-foreground" aria-label="AWS">
          <path
            d="M72.392053,55.4384106 C72.392053,58.5748344 72.7311258,61.1178808 73.3245033,62.9827815 C74.002649,64.8476821 74.8503311,66.8821192 76.0370861,69.0860927 C76.4609272,69.7642384 76.6304636,70.4423841 76.6304636,71.0357616 C76.6304636,71.8834437 76.1218543,72.7311258 75.0198675,73.5788079 L69.6794702,77.1390728 C68.9165563,77.6476821 68.1536424,77.9019868 67.4754967,77.9019868 C66.6278146,77.9019868 65.7801325,77.4781457 64.9324503,76.7152318 C63.7456954,75.4437086 62.7284768,74.0874172 61.8807947,72.7311258 C61.0331126,71.2900662 60.1854305,69.6794702 59.2529801,67.7298013 C52.6410596,75.5284768 44.3337748,79.4278146 34.3311258,79.4278146 C27.210596,79.4278146 21.5311258,77.3933775 17.3774834,73.3245033 C13.2238411,69.2556291 11.1046358,63.8304636 11.1046358,57.0490066 C11.1046358,49.8437086 13.6476821,43.994702 18.818543,39.586755 C23.989404,35.1788079 30.8556291,32.9748344 39.586755,32.9748344 C42.4688742,32.9748344 45.4357616,33.2291391 48.5721854,33.6529801 C51.7086093,34.0768212 54.9298013,34.7549669 58.3205298,35.5178808 L58.3205298,29.3298013 C58.3205298,22.8874172 56.9642384,18.394702 54.3364238,15.7668874 C51.6238411,13.1390728 47.0463576,11.8675497 40.5192053,11.8675497 C37.5523179,11.8675497 34.5006623,12.2066225 31.3642384,12.9695364 C28.2278146,13.7324503 25.1761589,14.6649007 22.2092715,15.8516556 C20.8529801,16.4450331 19.8357616,16.784106 19.2423841,16.9536424 C18.6490066,17.1231788 18.2251656,17.207947 17.8860927,17.207947 C16.6993377,17.207947 16.1059603,16.3602649 16.1059603,14.5801325 L16.1059603,10.4264901 C16.1059603,9.07019868 16.2754967,8.05298013 16.6993377,7.45960265 C17.1231788,6.86622517 17.8860927,6.27284768 19.0728477,5.6794702 C22.0397351,4.15364238 25.6,2.88211921 29.7536424,1.86490066 C33.9072848,0.762913907 38.3152318,0.254304636 42.9774834,0.254304636 C53.0649007,0.254304636 60.4397351,2.54304636 65.186755,7.1205298 C69.8490066,11.6980132 72.2225166,18.6490066 72.2225166,27.9735099 L72.2225166,55.4384106 L72.392053,55.4384106 Z M37.9761589,68.3231788 C40.7735099,68.3231788 43.6556291,67.8145695 46.7072848,66.797351 C49.7589404,65.7801325 52.4715232,63.9152318 54.7602649,61.3721854 C56.1165563,59.7615894 57.1337748,57.981457 57.6423841,55.9470199 C58.1509934,53.9125828 58.4900662,51.4543046 58.4900662,48.5721854 L58.4900662,45.0119205 C56.0317881,44.418543 53.4039735,43.9099338 50.6913907,43.5708609 C47.9788079,43.2317881 45.3509934,43.0622517 42.7231788,43.0622517 C37.0437086,43.0622517 32.8900662,44.1642384 30.0927152,46.4529801 C27.2953642,48.7417219 25.9390728,51.9629139 25.9390728,56.2013245 C25.9390728,60.1854305 26.9562914,63.1523179 29.0754967,65.186755 C31.1099338,67.3059603 34.0768212,68.3231788 37.9761589,68.3231788 Z M106.045033,77.4781457 C104.519205,77.4781457 103.501987,77.2238411 102.823841,76.6304636 C102.145695,76.1218543 101.552318,74.9350993 101.043709,73.3245033 L81.1231788,7.7986755 C80.6145695,6.10331126 80.3602649,5.0013245 80.3602649,4.40794702 C80.3602649,3.05165563 81.0384106,2.28874172 82.394702,2.28874172 L90.7019868,2.28874172 C92.3125828,2.28874172 93.4145695,2.54304636 94.007947,3.13642384 C94.6860927,3.64503311 95.194702,4.83178808 95.7033113,6.44238411 L109.944371,62.5589404 L123.168212,6.44238411 C123.592053,4.74701987 124.100662,3.64503311 124.778808,3.13642384 C125.456954,2.62781457 126.643709,2.28874172 128.169536,2.28874172 L134.950993,2.28874172 C136.561589,2.28874172 137.663576,2.54304636 138.341722,3.13642384 C139.019868,3.64503311 139.613245,4.83178808 139.952318,6.44238411 L153.345695,63.2370861 L168.010596,6.44238411 C168.519205,4.74701987 169.112583,3.64503311 169.70596,3.13642384 C170.384106,2.62781457 171.486093,2.28874172 173.011921,2.28874172 L180.895364,2.28874172 C182.251656,2.28874172 183.01457,2.96688742 183.01457,4.40794702 C183.01457,4.83178808 182.929801,5.25562914 182.845033,5.76423841 C182.760265,6.27284768 182.590728,6.95099338 182.251656,7.88344371 L161.822517,73.4092715 C161.313907,75.1046358 160.72053,76.2066225 160.042384,76.7152318 C159.364238,77.2238411 158.262252,77.5629139 156.821192,77.5629139 L149.531126,77.5629139 C147.92053,77.5629139 146.818543,77.3086093 146.140397,76.7152318 C145.462252,76.1218543 144.868874,75.0198675 144.529801,73.3245033 L131.390728,18.6490066 L118.336424,73.2397351 C117.912583,74.9350993 117.403974,76.0370861 116.725828,76.6304636 C116.047682,77.2238411 114.860927,77.4781457 113.335099,77.4781457 L106.045033,77.4781457 Z M214.972185,79.7668874 C210.564238,79.7668874 206.156291,79.2582781 201.917881,78.2410596 C197.67947,77.2238411 194.37351,76.1218543 192.169536,74.8503311 C190.813245,74.0874172 189.880795,73.2397351 189.541722,72.4768212 C189.202649,71.7139073 189.033113,70.8662252 189.033113,70.1033113 L189.033113,65.7801325 C189.033113,64 189.711258,63.1523179 190.982781,63.1523179 C191.491391,63.1523179 192,63.2370861 192.508609,63.4066225 C193.017219,63.5761589 193.780132,63.9152318 194.627815,64.2543046 C197.509934,65.5258278 200.646358,66.5430464 203.952318,67.2211921 C207.343046,67.8993377 210.649007,68.2384106 214.039735,68.2384106 C219.380132,68.2384106 223.533775,67.3059603 226.415894,65.4410596 C229.298013,63.5761589 230.823841,60.8635762 230.823841,57.3880795 C230.823841,55.0145695 230.060927,53.0649007 228.535099,51.4543046 C227.009272,49.8437086 224.127152,48.402649 219.97351,47.0463576 L207.682119,43.2317881 C201.49404,41.2821192 196.916556,38.4 194.119205,34.5854305 C191.321854,30.8556291 189.880795,26.7019868 189.880795,22.2940397 C189.880795,18.7337748 190.643709,15.597351 192.169536,12.8847682 C193.695364,10.1721854 195.729801,7.7986755 198.272848,5.93377483 C200.815894,3.98410596 203.698013,2.54304636 207.088742,1.52582781 C210.47947,0.508609272 214.039735,0.0847682119 217.769536,0.0847682119 C219.634437,0.0847682119 221.584106,0.169536424 223.449007,0.42384106 C225.398675,0.678145695 227.178808,1.01721854 228.95894,1.35629139 C230.654305,1.78013245 232.264901,2.20397351 233.790728,2.71258278 C235.316556,3.22119205 236.503311,3.72980132 237.350993,4.2384106 C238.537748,4.91655629 239.38543,5.59470199 239.89404,6.35761589 C240.402649,7.03576159 240.656954,7.96821192 240.656954,9.15496689 L240.656954,13.1390728 C240.656954,14.9192053 239.978808,15.8516556 238.707285,15.8516556 C238.029139,15.8516556 236.927152,15.5125828 235.486093,14.8344371 C230.654305,12.6304636 225.229139,11.5284768 219.210596,11.5284768 C214.378808,11.5284768 210.564238,12.2913907 207.936424,13.9019868 C205.308609,15.5125828 203.952318,17.9708609 203.952318,21.4463576 C203.952318,23.8198675 204.8,25.8543046 206.495364,27.4649007 C208.190728,29.0754967 211.327152,30.6860927 215.819868,32.1271523 L227.856954,35.9417219 C233.960265,37.8913907 238.368212,40.6039735 240.996026,44.0794702 C243.623841,47.5549669 244.895364,51.5390728 244.895364,55.9470199 C244.895364,59.592053 244.13245,62.8980132 242.691391,65.7801325 C241.165563,68.6622517 239.131126,71.205298 236.503311,73.2397351 C233.875497,75.3589404 230.739073,76.8847682 227.09404,77.986755 C223.27947,79.1735099 219.295364,79.7668874 214.972185,79.7668874 Z"
            fill="currentColor"
          />
          <path
            d="M230.993377,120.964238 C203.104636,141.562914 162.58543,152.498013 127.745695,152.498013 C78.9192053,152.498013 34.9245033,134.442384 1.69536424,104.434437 C-0.932450331,102.060927 1.4410596,98.8397351 4.57748344,100.704636 C40.5192053,121.557616 84.8529801,134.188079 130.712583,134.188079 C161.65298,134.188079 195.645033,127.745695 226.924503,114.521854 C231.586755,112.402649 235.570861,117.57351 230.993377,120.964238 Z"
            fill="#FF9900"
          />
          <path
            d="M242.606623,107.740397 C239.046358,103.162914 219.04106,105.536424 209.970861,106.638411 C207.258278,106.977483 206.834437,104.603974 209.292715,102.823841 C225.229139,91.6344371 251.422517,94.8556291 254.474172,98.5854305 C257.525828,102.4 253.62649,128.593377 238.707285,141.139073 C236.418543,143.088742 234.21457,142.071523 235.231788,139.528477 C238.622517,131.136424 246.166887,112.233113 242.606623,107.740397 Z"
            fill="#FF9900"
          />
        </svg>
      )
    case "Anthropic":
      return (
        <svg viewBox="0 0 24 24" className="h-16 w-auto text-foreground" fill="currentColor" aria-label="Anthropic">
          <path d="M17.3041 3.541h-3.6718l6.696 16.918H24Zm-10.6082 0L0 20.459h3.7442l1.3693-3.5527h7.0052l1.3693 3.5528h3.7442L10.5363 3.5409Zm-.3712 10.2232 2.2914-5.9456 2.2914 5.9456Z" />
        </svg>
      )
    case "Datadog":
      return (
        <svg viewBox="0 0 24 24" className="h-16 w-auto text-foreground" fill="currentColor" aria-label="Datadog">
          <path d="M19.57 17.04l-1.997-1.316-1.665 2.782-1.937-.567-1.706 2.604.087.82 9.274-1.71-.538-5.794zm-8.649-2.498l1.488-.204c.241.108.409.15.697.223.45.117.97.23 1.741-.16.18-.088.553-.43.704-.625l6.096-1.106.622 7.527-10.444 1.882zm11.325-2.712l-.602.115L20.488 0 .789 2.285l2.427 19.693 2.306-.334c-.184-.263-.471-.581-.96-.989-.68-.564-.44-1.522-.039-2.127.53-1.022 3.26-2.322 3.106-3.956-.056-.594-.15-1.368-.702-1.898-.02.22.017.432.017.432s-.227-.289-.34-.683c-.112-.15-.2-.199-.319-.4-.085.233-.073.503-.073.503s-.186-.437-.216-.807c-.11.166-.137.48-.137.48s-.241-.69-.186-1.062c-.11-.323-.436-.965-.343-2.424.6.421 1.924.321 2.44-.439.171-.251.288-.939-.086-2.293-.24-.868-.835-2.16-1.066-2.651l-.028.02c.122.395.374 1.223.47 1.625.293 1.218.372 1.642.234 2.204-.116.488-.397.808-1.107 1.165-.71.358-1.653-.514-1.713-.562-.69-.55-1.224-1.447-1.284-1.883-.062-.477.275-.763.445-1.153-.243.07-.514.192-.514.192s.323-.334.722-.624c.165-.109.262-.178.436-.323a9.762 9.762 0 0 0-.456.003s.42-.227.855-.392c-.318-.014-.623-.003-.623-.003s.937-.419 1.678-.727c.509-.208 1.006-.147 1.286.257.367.53.752.817 1.569.996.501-.223.653-.337 1.284-.509.554-.61.99-.688.99-.688s-.216.198-.274.51c.314-.249.66-.455.66-.455s-.134.164-.259.426l.03.043c.366-.22.797-.394.797-.394s-.123.156-.268.358c.277-.002.838.012 1.056.037 1.285.028 1.552-1.374 2.045-1.55.618-.22.894-.353 1.947.68.903.888 1.609 2.477 1.259 2.833-.294.295-.874-.115-1.516-.916a3.466 3.466 0 0 1-.716-1.562 1.533 1.533 0 0 0-.497-.85s.23.51.23.96c0 .246.03 1.165.424 1.68-.039.076-.057.374-.1.43-.458-.554-1.443-.95-1.604-1.067.544.445 1.793 1.468 2.273 2.449.453.927.186 1.777.416 1.997.065.063.976 1.197 1.15 1.767.306.994.019 2.038-.381 2.685l-1.117.174c-.163-.045-.273-.068-.42-.153.08-.143.241-.5.243-.572l-.063-.111c-.348.492-.93.97-1.414 1.245-.633.359-1.363.304-1.838.156-1.348-.415-2.623-1.327-2.93-1.566 0 0-.01.191.048.234.34.383 1.119 1.077 1.872 1.56l-1.605.177.759 5.908c-.337.048-.39.071-.757.124-.325-1.147-.946-1.895-1.624-2.332-.599-.384-1.424-.47-2.214-.314l-.05.059a2.851 2.851 0 0 1 1.863.444c.654.413 1.181 1.481 1.375 2.124.248.822.42 1.7-.248 2.632-.476.662-1.864 1.028-2.986.237.3.481.705.876 1.25.95.809.11 1.577-.03 2.106-.574.452-.464.69-1.434.628-2.456l.714-.104.258 1.834 11.827-1.424zM15.05 6.848c-.034.075-.085.125-.007.37l.004.014.013.032.032.073c.14.287.295.558.552.696.067-.011.136-.019.207-.023.242-.01.395.028.492.08.009-.048.01-.119.005-.222-.018-.364.072-.982-.626-1.308-.264-.122-.634-.084-.757.068a.302.302 0 0 1 .058.013c.186.066.06.13.027.207m1.958 3.392c-.092-.05-.52-.03-.821.005-.574.068-1.193.267-1.328.372-.247.191-.135.523.047.66.511.382.96.638 1.432.575.29-.038.546-.497.728-.914.124-.288.124-.598-.058-.698m-5.077-2.942c.162-.154-.805-.355-1.556.156-.554.378-.571 1.187-.041 1.646.053.046.096.078.137.104a4.77 4.77 0 0 1 1.396-.412c.113-.125.243-.345.21-.745-.044-.542-.455-.456-.146-.749" />
        </svg>
      )
    case "Neo4j":
      return (
        <svg viewBox="0 0 24 24" className="h-16 w-auto text-foreground" fill="currentColor" aria-label="Neo4j">
          <path d="M9.629 13.227c-.593 0-1.139.2-1.58.533l-2.892-1.976a2.61 2.61 0 0 0 .101-.711 2.633 2.633 0 0 0-2.629-2.629A2.632 2.632 0 0 0 0 11.073a2.632 2.632 0 0 0 2.629 2.629c.593 0 1.139-.2 1.579-.533L7.1 15.145c-.063.226-.1.465-.1.711 0 .247.037.484.1.711l-2.892 1.976a2.608 2.608 0 0 0-1.579-.533A2.632 2.632 0 0 0 0 20.639a2.632 2.632 0 0 0 2.629 2.629 2.632 2.632 0 0 0 2.629-2.629c0-.247-.037-.485-.101-.711l2.892-1.976c.441.333.987.533 1.58.533a2.633 2.633 0 0 0 2.629-2.629c0-1.45-1.18-2.629-2.629-2.629ZM16.112.732c-4.72 0-7.888 2.748-7.888 8.082v3.802a3.525 3.525 0 0 1 3.071.008v-3.81c0-3.459 1.907-5.237 4.817-5.237s4.817 1.778 4.817 5.237v8.309H24V8.814C24 3.448 20.832.732 16.112.732Z" />
        </svg>
      )
    default:
      return null
  }
}

function SponsorShowcase() {
  const { ref, isVisible } = useScrollAnimation()

  return (
    <section ref={ref} className="relative py-24 overflow-hidden">
      <div className="max-w-7xl mx-auto px-6">
        <div
          className={`text-center mb-16 transition-all duration-700 ${
            isVisible ? "opacity-100 translate-y-0" : "opacity-0 translate-y-8"
          }`}
        >
          <h2 className="text-3xl sm:text-4xl md:text-5xl font-bold tracking-tight mb-4">
            <span className="gradient-text">Powered By</span>
          </h2>
          <p className="text-lg text-slate-400 max-w-2xl mx-auto">
            Built for the AWS × Anthropic × Datadog GenAI Hackathon
          </p>
        </div>

        <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-6">
          {sponsors.map((sponsor, i) => (
            <div
              key={sponsor.name}
              className={`group relative p-6 rounded-2xl bg-white/[0.02] border border-white/[0.06] backdrop-blur-sm transition-all duration-700 hover:border-violet-500/30 hover:-translate-y-1 ${
                isVisible ? "opacity-100 translate-y-0" : "opacity-0 translate-y-8"
              }`}
              style={{ transitionDelay: isVisible ? `${i * 150}ms` : "0ms" }}
            >
              {/* Glow on hover */}
              <div
                className={`absolute -inset-2 bg-gradient-to-br ${sponsor.glowColor} rounded-3xl blur-2xl opacity-0 group-hover:opacity-100 transition-opacity duration-500`}
                aria-hidden="true"
              />

              <div className="relative flex flex-col items-center text-center">
                <div className="mb-4">
                  <SponsorLogo name={sponsor.name} />
                </div>
                <h3 className="text-lg font-semibold mb-1">{sponsor.name}</h3>
                <p className="text-sm font-medium text-violet-400 mb-2">{sponsor.role}</p>
                <p className="text-sm text-slate-400 leading-relaxed">{sponsor.description}</p>
              </div>
            </div>
          ))}
        </div>
      </div>
    </section>
  )
}

// ─── Main Landing Page ───────────────────────────────────

export default function LandingPage() {
  const [mounted, setMounted] = useState(false)
  const [scrolled, setScrolled] = useState(false)
  const { theme, setTheme } = useTheme()

  useEffect(() => {
    setMounted(true)
    const handleScroll = () => setScrolled(window.scrollY > 50)
    window.addEventListener("scroll", handleScroll, { passive: true })
    return () => window.removeEventListener("scroll", handleScroll)
  }, [])

  return (
    <div className="min-h-screen bg-background text-foreground overflow-x-clip">
      {/* Nebula background */}
      <div className="nebula-bg" aria-hidden="true" />
      {mounted && <AmbientParticles />}

      {/* Navigation */}
      <nav
        className={`fixed top-0 left-0 right-0 z-50 transition-all duration-300 ${
          scrolled
            ? "bg-background/80 backdrop-blur-xl border-b border-border"
            : "bg-transparent"
        }`}
      >
        <div className="max-w-7xl mx-auto px-6 h-16 flex items-center justify-between">
          <Link href="/" className="flex items-center gap-2.5 group">
            <div className="relative w-8 h-8 rounded-lg bg-gradient-to-br from-violet-500/20 to-fuchsia-500/10 border border-violet-500/30 flex items-center justify-center">
              <GitBranch className="w-4 h-4 text-violet-400" />
            </div>
            <span className="text-lg font-bold gradient-text">Continuum</span>
          </Link>
          <div className="flex items-center gap-2">
            <Button
              variant="ghost"
              size="icon"
              onClick={() => setTheme(theme === "dark" ? "light" : "dark")}
              className="text-muted-foreground hover:text-foreground"
              aria-label={mounted ? (theme === "dark" ? "Switch to light mode" : "Switch to dark mode") : "Toggle theme"}
            >
              {mounted ? (
                theme === "dark" ? (
                  <Sun className="h-4 w-4" />
                ) : (
                  <Moon className="h-4 w-4" />
                )
              ) : (
                <Sun className="h-4 w-4 opacity-0" />
              )}
            </Button>
            <Link href="/login">
              <Button variant="ghost" className="text-muted-foreground hover:text-foreground">
                Sign In
              </Button>
            </Link>
          </div>
        </div>
      </nav>

      {/* Hero — scroll-driven conductor scene */}
      {mounted && <HeroConductor />}

      {/* Sponsor Showcase */}
      <SponsorShowcase />

      {/* Features */}
      <section className="relative py-32">
        <FeatureSection
          title="See Every Connection"
          description="Every agent decision creates a ripple. Continuum maps how Bedrock calls, Neo4j queries, and Datadog traces interconnect — revealing the full picture of your agent's reasoning."
          imageSrc="/media/knowledge-graph.gif"
          imageAlt="Interactive knowledge graph visualization showing decision and entity nodes"
          glowColor="violet"
          imagePosition="right"
          animation={(visible) => <PulsingNetwork isVisible={visible} />}
        />

        <FeatureSection
          title="Observe What Matters"
          description="Datadog LLM Observability traces every Bedrock call — prompt, completion, tokens, latency, cost. Combined with Continuum's knowledge graph, you see not just what your agent did, but why."
          imageSrc="/media/capture-session.gif"
          imageAlt="AI-guided interview session capturing engineering decisions"
          glowColor="rose"
          imagePosition="left"
          animation={(visible) => <ConversationExtract isVisible={visible} />}
        />

        <FeatureSection
          title="Zero-Effort Extraction"
          description="Point Continuum at your Strands agent's MCP tools and watch as decisions are automatically extracted, entities resolved in Neo4j, and every step traced in Datadog — all without lifting a finger."
          imageSrc="/media/import-logs.gif"
          imageAlt="Automated decision extraction from Claude Code conversation logs"
          glowColor="orange"
          imagePosition="right"
          animation={(visible) => <FileScan isVisible={visible} />}
        />
      </section>

      {/* How It Works */}
      <HowItWorks />

      {/* Tech & Credibility */}
      <TechCredibility />

      {/* Footer */}
      <footer className="border-t border-border py-12">
        <div className="max-w-7xl mx-auto px-6 flex flex-col items-center gap-4 text-center">
          <div className="flex items-center gap-2">
            <div className="w-6 h-6 rounded-md bg-gradient-to-br from-violet-500/20 to-fuchsia-500/10 border border-violet-500/30 flex items-center justify-center">
              <GitBranch className="w-3 h-3 text-violet-400" />
            </div>
            <span className="font-semibold gradient-text">Continuum</span>
          </div>
          <p className="text-sm text-slate-500 max-w-md">
            Observable agent memory — powered by AWS Bedrock, traced by Datadog, stored in Neo4j.
          </p>
          <div className="flex items-center gap-6 text-sm text-slate-500">
            <a
              href="mailto:shehral.m@northeastern.edu"
              className="hover:text-violet-400 transition-colors"
            >
              Contact
            </a>
            <Link href="/login" className="hover:text-violet-400 transition-colors">
              Sign In
            </Link>
          </div>
          <p className="text-xs text-slate-600 mt-4">&copy; 2026 Ali Shehral</p>
        </div>
      </footer>
    </div>
  )
}
