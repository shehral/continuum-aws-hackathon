"use client"

import { useTheme } from "next-themes"
import { useEffect, useState } from "react"
import { Sun, Moon, Monitor, Palette, Info, ExternalLink } from "lucide-react"

import { AppShell } from "@/components/layout/app-shell"
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from "@/components/ui/card"
import { Button } from "@/components/ui/button"
import { Badge } from "@/components/ui/badge"

const THEME_OPTIONS = [
  { value: "system", label: "System", icon: Monitor, description: "Follow your OS preference" },
  { value: "dark", label: "Dark", icon: Moon, description: "Nebula dark theme" },
  { value: "light", label: "Light", icon: Sun, description: "Light theme" },
] as const

export default function SettingsPage() {
  const { theme, setTheme } = useTheme()
  const [mounted, setMounted] = useState(false)

  useEffect(() => {
    setMounted(true)
  }, [])

  return (
    <AppShell>
      <div className="max-w-2xl mx-auto p-6 space-y-6">
        <div>
          <h1 className="text-2xl font-bold tracking-tight text-slate-100">Settings</h1>
          <p className="text-sm text-slate-400 mt-1">Customize your Continuum experience</p>
        </div>

        {/* Appearance */}
        <Card variant="glass">
          <CardHeader>
            <div className="flex items-center gap-2">
              <Palette className="h-5 w-5 text-violet-400" />
              <CardTitle className="text-lg">Appearance</CardTitle>
            </div>
            <CardDescription>Choose your preferred color theme</CardDescription>
          </CardHeader>
          <CardContent>
            <div className="grid grid-cols-3 gap-3">
              {mounted && THEME_OPTIONS.map((option) => {
                const isActive = theme === option.value
                return (
                  <button
                    key={option.value}
                    onClick={() => setTheme(option.value)}
                    className={`p-4 rounded-xl border transition-all text-left ${
                      isActive
                        ? "border-violet-500/50 bg-violet-500/10 shadow-[0_0_15px_rgba(139,92,246,0.15)]"
                        : "border-white/[0.06] bg-white/[0.02] hover:border-white/[0.12] hover:bg-white/[0.04]"
                    }`}
                    aria-pressed={isActive}
                  >
                    <option.icon className={`h-5 w-5 mb-2 ${isActive ? "text-violet-400" : "text-slate-400"}`} />
                    <p className={`text-sm font-medium ${isActive ? "text-violet-300" : "text-slate-200"}`}>
                      {option.label}
                    </p>
                    <p className="text-xs text-slate-500 mt-0.5">{option.description}</p>
                  </button>
                )
              })}
            </div>
          </CardContent>
        </Card>

        {/* About */}
        <Card variant="glass">
          <CardHeader>
            <div className="flex items-center gap-2">
              <Info className="h-5 w-5 text-fuchsia-400" />
              <CardTitle className="text-lg">About</CardTitle>
            </div>
            <CardDescription>Continuum Knowledge Graph</CardDescription>
          </CardHeader>
          <CardContent className="space-y-4">
            <div className="flex items-center justify-between">
              <span className="text-sm text-slate-400">Version</span>
              <Badge className="bg-white/[0.04] text-slate-300 border-white/[0.08]">0.1.0</Badge>
            </div>
            <div className="flex items-center justify-between">
              <span className="text-sm text-slate-400">Stack</span>
              <span className="text-sm text-slate-300">Next.js + FastAPI + Neo4j</span>
            </div>
            <div className="flex items-center justify-between">
              <span className="text-sm text-slate-400">AI Model</span>
              <span className="text-sm text-slate-300">Llama 3.3 Nemotron</span>
            </div>
            <div className="pt-2 border-t border-white/[0.06]">
              <Button
                variant="ghost"
                size="sm"
                className="text-violet-400 hover:text-violet-300 hover:bg-violet-500/10 px-0"
                asChild
              >
                <a
                  href="https://github.com/anthropics/claude-code"
                  target="_blank"
                  rel="noopener noreferrer"
                  className="flex items-center gap-1"
                >
                  Built with Claude Code
                  <ExternalLink className="h-3.5 w-3.5" />
                </a>
              </Button>
            </div>
          </CardContent>
        </Card>

        {/* Keyboard Shortcuts */}
        <Card variant="glass">
          <CardHeader>
            <CardTitle className="text-lg">Keyboard Shortcuts</CardTitle>
          </CardHeader>
          <CardContent>
            <div className="space-y-3">
              {[
                { keys: ["⌘", "K"], description: "Open command palette" },
                { keys: ["Esc"], description: "Close dialogs" },
                { keys: ["↑", "↓"], description: "Navigate graph nodes" },
                { keys: ["Enter"], description: "Select / confirm" },
              ].map((shortcut) => (
                <div key={shortcut.description} className="flex items-center justify-between">
                  <span className="text-sm text-slate-400">{shortcut.description}</span>
                  <div className="flex gap-1">
                    {shortcut.keys.map((key) => (
                      <kbd
                        key={key}
                        className="px-2 py-0.5 text-xs bg-white/[0.04] border border-white/[0.08] rounded-md text-slate-300 font-mono"
                      >
                        {key}
                      </kbd>
                    ))}
                  </div>
                </div>
              ))}
            </div>
          </CardContent>
        </Card>
      </div>
    </AppShell>
  )
}
