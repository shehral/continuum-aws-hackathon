"use client"

import { Check, Circle, Loader2 } from "lucide-react"
import { cn } from "@/lib/utils"

export type TraceStage = "trigger" | "context" | "options" | "decision" | "rationale"

interface DecisionTraceIndicatorProps {
  currentStage: TraceStage
  completedStages: TraceStage[]
}

const stages: { id: TraceStage; label: string }[] = [
  { id: "trigger", label: "Trigger" },
  { id: "context", label: "Context" },
  { id: "options", label: "Options" },
  { id: "decision", label: "Decision" },
  { id: "rationale", label: "Rationale" },
]

export function DecisionTraceIndicator({
  currentStage,
  completedStages,
}: DecisionTraceIndicatorProps) {
  return (
    <div className="flex items-center justify-between px-4 py-3 bg-muted/50 border-b">
      {stages.map((stage, index) => {
        const isCompleted = completedStages.includes(stage.id)
        const isCurrent = currentStage === stage.id
        const isUpcoming = !isCompleted && !isCurrent

        return (
          <div key={stage.id} className="flex items-center">
            <div className="flex flex-col items-center">
              <div
                className={cn(
                  "flex h-8 w-8 items-center justify-center rounded-full border-2 transition-colors",
                  isCompleted &&
                    "border-primary bg-primary text-primary-foreground",
                  isCurrent && "border-primary text-primary",
                  isUpcoming && "border-muted-foreground/30 text-muted-foreground/50"
                )}
              >
                {isCompleted ? (
                  <Check className="h-4 w-4" />
                ) : isCurrent ? (
                  <Loader2 className="h-4 w-4 animate-spin" />
                ) : (
                  <Circle className="h-3 w-3" />
                )}
              </div>
              <span
                className={cn(
                  "mt-1 text-xs font-medium",
                  isCompleted && "text-primary",
                  isCurrent && "text-primary",
                  isUpcoming && "text-muted-foreground/50"
                )}
              >
                {stage.label}
              </span>
            </div>
            {index < stages.length - 1 && (
              <div
                className={cn(
                  "mx-2 h-0.5 w-12 transition-colors",
                  isCompleted ? "bg-primary" : "bg-muted-foreground/30"
                )}
              />
            )}
          </div>
        )
      })}
    </div>
  )
}
