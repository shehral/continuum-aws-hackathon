"use client"

import { BookOpen, X, CheckCircle2, ArrowRightLeft } from "lucide-react"
import { Badge } from "@/components/ui/badge"
import { Button } from "@/components/ui/button"
import { Card, CardContent, CardHeader } from "@/components/ui/card"
import { ScrollArea } from "@/components/ui/scroll-area"
import type { SourceDecision } from "@/lib/api"
import { cn } from "@/lib/utils"

interface SourceCitationsPanelProps {
  decisions: SourceDecision[]
  onClose: () => void
}

export function SourceCitationsPanel({ decisions, onClose }: SourceCitationsPanelProps) {
  if (decisions.length === 0) return null

  return (
    <div className="w-80 border-l border-white/[0.06] bg-card/95 backdrop-blur-xl flex flex-col animate-in slide-in-from-right-4 duration-300">
      {/* Header */}
      <div className="p-4 border-b border-white/[0.06] flex items-center justify-between shrink-0">
        <h3 className="font-medium text-sm flex items-center gap-2 text-slate-200">
          <BookOpen className="h-4 w-4 text-violet-400" />
          Sources ({decisions.length})
        </h3>
        <Button
          variant="ghost"
          size="sm"
          onClick={onClose}
          className="h-7 w-7 p-0 text-slate-400 hover:text-slate-200"
        >
          <X className="h-4 w-4" />
        </Button>
      </div>

      {/* Decision cards */}
      <ScrollArea className="flex-1">
        <div className="p-3 space-y-3">
          {decisions.map((decision) => (
            <Card
              key={decision.id}
              variant="glass"
              className="overflow-hidden"
            >
              <CardHeader className="p-3 pb-2 space-y-2">
                <div className="flex items-center gap-2">
                  <Badge
                    variant="outline"
                    className={cn(
                      "text-[10px] font-medium",
                      decision.is_current
                        ? "bg-emerald-500/10 border-emerald-500/30 text-emerald-400"
                        : "bg-amber-500/10 border-amber-500/30 text-amber-400"
                    )}
                  >
                    {decision.is_current ? (
                      <><CheckCircle2 className="h-3 w-3 mr-1" /> Current</>
                    ) : (
                      <><ArrowRightLeft className="h-3 w-3 mr-1" /> Superseded</>
                    )}
                  </Badge>
                  <span className="text-[10px] text-slate-500">
                    {Math.round(decision.confidence * 100)}% confidence
                  </span>
                </div>
                <p className="text-xs font-medium text-slate-300 leading-snug">
                  {decision.trigger}
                </p>
              </CardHeader>

              <CardContent className="p-3 pt-0 space-y-2">
                <div>
                  <p className="text-[10px] font-medium text-violet-400 uppercase tracking-wider mb-0.5">
                    Decision
                  </p>
                  <p className="text-xs text-slate-300 leading-relaxed">
                    {decision.decision}
                  </p>
                </div>

                <div>
                  <p className="text-[10px] font-medium text-fuchsia-400 uppercase tracking-wider mb-0.5">
                    Rationale
                  </p>
                  <p className="text-xs text-slate-400 leading-relaxed line-clamp-3">
                    {decision.rationale}
                  </p>
                </div>

                {decision.entities.length > 0 && (
                  <div className="flex gap-1 flex-wrap pt-1">
                    {decision.entities.map((entity) => (
                      <Badge
                        key={entity}
                        variant="outline"
                        className="text-[10px] bg-white/[0.03] border-white/[0.1] text-slate-400"
                      >
                        {entity}
                      </Badge>
                    ))}
                  </div>
                )}
              </CardContent>
            </Card>
          ))}
        </div>
      </ScrollArea>
    </div>
  )
}
