"use client"

import { HelpCircle, GitBranch, Scale, LayoutDashboard } from "lucide-react"
import { Card, CardContent } from "@/components/ui/card"
import type { SuggestedQuestion } from "@/lib/api"

const categoryConfig: Record<string, { icon: typeof HelpCircle; color: string }> = {
  why: { icon: HelpCircle, color: "text-violet-400" },
  evolution: { icon: GitBranch, color: "text-fuchsia-400" },
  comparison: { icon: Scale, color: "text-orange-400" },
  overview: { icon: LayoutDashboard, color: "text-sky-400" },
}

interface SuggestedQuestionsProps {
  questions: SuggestedQuestion[]
  onSelect: (question: string) => void
}

export function SuggestedQuestions({ questions, onSelect }: SuggestedQuestionsProps) {
  return (
    <div className="grid grid-cols-1 md:grid-cols-2 gap-3 max-w-2xl mx-auto">
      {questions.map((q) => {
        const config = categoryConfig[q.category] ?? categoryConfig.overview
        const Icon = config.icon

        return (
          <Card
            key={q.question}
            variant="glass"
            className="cursor-pointer group"
            onClick={() => onSelect(q.question)}
          >
            <CardContent className="p-4 flex gap-3 items-start">
              <div className="shrink-0 mt-0.5 h-8 w-8 rounded-lg bg-white/[0.05] flex items-center justify-center group-hover:bg-white/[0.1] transition-colors">
                <Icon className={`h-4 w-4 ${config.color}`} />
              </div>
              <p className="text-sm text-slate-300 group-hover:text-slate-100 transition-colors leading-relaxed">
                {q.question}
              </p>
            </CardContent>
          </Card>
        )
      })}
    </div>
  )
}
