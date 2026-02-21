"use client"

import { useEffect, useState } from "react"
import { useRouter } from "next/navigation"
import { Brain, Plus, Network, Search, ArrowRight, X } from "lucide-react"

import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
  DialogDescription,
  DialogFooter,
} from "@/components/ui/dialog"
import { Button } from "@/components/ui/button"

const ONBOARDING_KEY = "continuum-onboarding-seen"

const STEPS = [
  {
    icon: Plus,
    title: "Add Knowledge",
    description: "Import Claude conversation logs or use AI-guided interviews to capture decisions.",
    color: "text-violet-400",
    bg: "bg-violet-500/10",
  },
  {
    icon: Network,
    title: "Explore the Graph",
    description: "Visualize connections between decisions, entities, and concepts in your knowledge graph.",
    color: "text-fuchsia-400",
    bg: "bg-fuchsia-500/10",
  },
  {
    icon: Search,
    title: "Search & Discover",
    description: "Use hybrid search to find decisions by meaning, not just keywords. Press Cmd+K for quick access.",
    color: "text-orange-400",
    bg: "bg-orange-500/10",
  },
]

export function Onboarding() {
  const [open, setOpen] = useState(false)
  const router = useRouter()

  useEffect(() => {
    const seen = localStorage.getItem(ONBOARDING_KEY)
    if (!seen) {
      // Small delay to avoid flash during page load
      const timer = setTimeout(() => setOpen(true), 500)
      return () => clearTimeout(timer)
    }
  }, [])

  const handleDismiss = () => {
    localStorage.setItem(ONBOARDING_KEY, "true")
    setOpen(false)
  }

  const handleGetStarted = () => {
    localStorage.setItem(ONBOARDING_KEY, "true")
    setOpen(false)
    router.push("/add")
  }

  return (
    <Dialog open={open} onOpenChange={(isOpen) => { if (!isOpen) handleDismiss() }}>
      <DialogContent className="sm:max-w-lg">
        <DialogHeader>
          <div className="flex items-center gap-3 mb-2">
            <div className="h-10 w-10 rounded-xl bg-gradient-to-br from-violet-500/20 to-fuchsia-500/10 border border-violet-500/20 flex items-center justify-center">
              <Brain className="h-5 w-5 text-violet-400" />
            </div>
            <div>
              <DialogTitle className="text-xl">Welcome to Continuum</DialogTitle>
              <DialogDescription>Your decision knowledge graph</DialogDescription>
            </div>
          </div>
        </DialogHeader>

        <div className="space-y-4 py-2">
          {STEPS.map((step) => (
            <div key={step.title} className="flex items-start gap-3 p-3 rounded-xl bg-white/[0.02] border border-white/[0.06]">
              <div className={`h-9 w-9 rounded-lg ${step.bg} flex items-center justify-center shrink-0`}>
                <step.icon className={`h-4 w-4 ${step.color}`} />
              </div>
              <div>
                <p className="text-sm font-medium text-slate-200">{step.title}</p>
                <p className="text-xs text-slate-400 mt-0.5">{step.description}</p>
              </div>
            </div>
          ))}
        </div>

        <DialogFooter className="flex-row gap-2 sm:justify-between">
          <Button variant="ghost" size="sm" onClick={handleDismiss} className="text-slate-400">
            Skip
          </Button>
          <Button onClick={handleGetStarted} className="bg-gradient-to-r from-violet-500 via-fuchsia-500 to-orange-400 text-white">
            Get Started
            <ArrowRight className="h-4 w-4 ml-1" />
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}
