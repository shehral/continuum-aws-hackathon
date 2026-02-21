"use client"

import Link from "next/link"
import { usePathname, useRouter } from "next/navigation"
import { useTheme } from "next-themes"
import { signOut, useSession } from "next-auth/react"
import { useState, useEffect } from "react"

import { cn } from "@/lib/utils"
import { Button } from "@/components/ui/button"
import { Avatar, AvatarFallback } from "@/components/ui/avatar"
import { Separator } from "@/components/ui/separator"
import { Tooltip, TooltipContent, TooltipProvider, TooltipTrigger } from "@/components/ui/tooltip"
import {
  LayoutDashboard,
  Brain,
  Network,
  ClipboardList,
  Search,
  Folder,
  MessageCircle,
  Sun,
  Moon,
  Settings,
  LogOut,
  ChevronLeft,
  ChevronRight,
  Sparkles,
  Zap,
  GitBranch,
  Map,
} from "lucide-react"

const navigation = [
  { name: "Dashboard", href: "/dashboard", icon: LayoutDashboard },
  { name: "Ask Codebase", href: "/chat", icon: MessageCircle },
  { name: "Add Knowledge", href: "/add", icon: Brain },
  { name: "Knowledge Graph", href: "/graph", icon: Network },
  { name: "Decisions", href: "/decisions", icon: ClipboardList },
  { name: "Branch Explorer", href: "/branches", icon: GitBranch },
  { name: "Coverage Map", href: "/coverage", icon: Map },
  { name: "Projects", href: "/projects", icon: Folder },
  { name: "Search", href: "/search", icon: Search },
]

interface SidebarProps {
  collapsed?: boolean
  onCollapsedChange?: (collapsed: boolean) => void
}

export function Sidebar({ collapsed: controlledCollapsed, onCollapsedChange }: SidebarProps) {
  const pathname = usePathname()
  const router = useRouter()
  const { theme, setTheme } = useTheme()
  const { data: session } = useSession()
  const [mounted, setMounted] = useState(false)

  // Use internal state if not controlled
  const [internalCollapsed, setInternalCollapsed] = useState(false)
  const collapsed = controlledCollapsed ?? internalCollapsed
  const setCollapsed = onCollapsedChange ?? setInternalCollapsed

  // Prevent hydration mismatch
  useEffect(() => {
    setMounted(true)
  }, [])

  // Load collapsed state from localStorage
  useEffect(() => {
    const saved = localStorage.getItem('sidebar-collapsed')
    if (saved !== null) {
      setCollapsed(saved === 'true')
    }
  }, [setCollapsed])

  // Save collapsed state to localStorage
  const toggleCollapsed = () => {
    const newValue = !collapsed
    setCollapsed(newValue)
    localStorage.setItem('sidebar-collapsed', String(newValue))
  }

  return (
    <div
      className={cn(
        "flex h-full flex-col border-r border-border bg-card/95 backdrop-blur-xl transition-all duration-300 ease-in-out",
        collapsed ? "w-[72px]" : "w-64"
      )}
    >
      {/* Logo */}
      <div className={cn(
        "flex h-16 items-center gap-3 px-4 transition-all duration-300",
        collapsed && "justify-center px-2"
      )}>
        <div className="relative flex h-10 w-10 items-center justify-center rounded-xl bg-gradient-to-br from-violet-500 via-fuchsia-500 to-orange-400 shadow-glow-violet shrink-0">
          <Zap className="h-5 w-5 text-white" />
          <div className="absolute inset-0 rounded-xl bg-gradient-to-br from-violet-500 via-fuchsia-500 to-orange-400 blur-lg opacity-50 -z-10" />
        </div>
        {!collapsed && (
          <div className="animate-fade-in">
            <span className="text-lg font-bold gradient-text">Continuum</span>
            <div className="text-[11px] text-muted-foreground flex items-center gap-1">
              <Sparkles className="h-3 w-3 text-violet-400" />
              Knowledge Graph
            </div>
          </div>
        )}
      </div>

      <Separator className="bg-border" />

      {/* Collapse Toggle */}
      <div className={cn("px-3 py-2", collapsed && "px-2")}>
        <Button
          variant="ghost"
          size="sm"
          onClick={toggleCollapsed}
          className={cn(
            "w-full justify-center text-muted-foreground hover:text-foreground hover:bg-muted transition-all duration-200",
            !collapsed && "justify-end"
          )}
          aria-label={collapsed ? "Expand sidebar" : "Collapse sidebar"}
        >
          {collapsed ? (
            <ChevronRight className="h-4 w-4" />
          ) : (
            <ChevronLeft className="h-4 w-4" />
          )}
        </Button>
      </div>

      {/* Navigation */}
      <nav className={cn("flex-1 space-y-1 py-2", collapsed ? "px-2" : "px-3")} aria-label="Main navigation">
        <TooltipProvider delayDuration={0}>
          {navigation.map((item) => {
            const isActive = pathname === item.href
            const Icon = item.icon

            const linkContent = (
              <Link
                key={item.name}
                href={item.href}
                aria-current={isActive ? "page" : undefined}
                className={cn(
                  "group flex items-center gap-3 rounded-xl px-3 py-2.5 text-sm font-medium transition-all duration-200",
                  collapsed && "justify-center px-2",
                  isActive
                    ? "bg-gradient-to-r from-violet-500/20 via-fuchsia-500/10 to-transparent border-l-2 border-violet-500 text-foreground"
                    : "text-muted-foreground hover:bg-muted hover:text-foreground border-l-2 border-transparent"
                )}
              >
                <Icon
                  className={cn(
                    "h-5 w-5 shrink-0 transition-all duration-200",
                    isActive ? "text-violet-400" : "text-muted-foreground group-hover:text-violet-400 group-hover:scale-110"
                  )}
                />
                {!collapsed && (
                  <span className="animate-fade-in">{item.name}</span>
                )}
              </Link>
            )

            if (collapsed) {
              return (
                <Tooltip key={item.name}>
                  <TooltipTrigger asChild>
                    {linkContent}
                  </TooltipTrigger>
                  <TooltipContent side="right" className="bg-popover border-border">
                    {item.name}
                  </TooltipContent>
                </Tooltip>
              )
            }

            return linkContent
          })}
        </TooltipProvider>
      </nav>

      <Separator className="bg-border" />

      {/* User section */}
      <div className={cn("p-3", collapsed && "p-2")}>
        {!collapsed ? (
          <>
            <div className="flex items-center gap-3 rounded-xl bg-muted/50 px-3 py-3 border border-border hover:border-violet-500/30 transition-all duration-200">
              <Avatar className="h-10 w-10 bg-gradient-to-br from-violet-500 to-fuchsia-500 shadow-glow-violet/50">
                <AvatarFallback className="bg-transparent text-white font-semibold">
                  {session?.user?.name?.charAt(0).toUpperCase() || "U"}
                </AvatarFallback>
              </Avatar>
              <div className="flex-1 min-w-0">
                <p className="text-sm font-medium text-foreground truncate">
                  {session?.user?.name || "User"}
                </p>
                <p className="text-xs text-muted-foreground truncate">
                  {session?.user?.email || ""}
                </p>
              </div>
            </div>

            <div className="mt-3 flex gap-2">
              <Button
                variant="ghost"
                size="sm"
                onClick={() => setTheme(theme === "dark" ? "light" : "dark")}
                className="flex-1 text-muted-foreground hover:text-foreground hover:bg-muted group"
                aria-label={mounted ? (theme === "dark" ? "Switch to light mode" : "Switch to dark mode") : "Toggle theme"}
              >
                {mounted ? (
                  theme === "dark" ? (
                    <Sun className="h-4 w-4 group-hover:text-amber-400 transition-colors" />
                  ) : (
                    <Moon className="h-4 w-4 group-hover:text-violet-400 transition-colors" />
                  )
                ) : (
                  <Sun className="h-4 w-4 opacity-0" />
                )}
              </Button>
              <Button
                variant="ghost"
                size="sm"
                onClick={() => router.push("/settings")}
                className="flex-1 text-muted-foreground hover:text-foreground hover:bg-muted group"
                aria-label="Open settings"
              >
                <Settings className="h-4 w-4 group-hover:rotate-90 transition-transform duration-300" />
              </Button>
              <Button
                variant="ghost"
                size="sm"
                onClick={() => signOut({ callbackUrl: '/' })}
                className="flex-1 text-muted-foreground hover:text-rose-400 hover:bg-rose-500/10 group"
                aria-label="Sign out"
              >
                <LogOut className="h-4 w-4 group-hover:translate-x-1 transition-transform" />
              </Button>
            </div>
          </>
        ) : (
          <TooltipProvider delayDuration={0}>
            <div className="space-y-2">
              <Tooltip>
                <TooltipTrigger asChild>
                  <div className="flex justify-center">
                    <Avatar className="h-10 w-10 bg-gradient-to-br from-violet-500 to-fuchsia-500 shadow-glow-violet/50 cursor-pointer hover:scale-105 transition-transform">
                      <AvatarFallback className="bg-transparent text-white font-semibold">
                        {session?.user?.name?.charAt(0).toUpperCase() || "U"}
                      </AvatarFallback>
                    </Avatar>
                  </div>
                </TooltipTrigger>
                <TooltipContent side="right" className="bg-popover border-border">
                  <p className="font-medium">{session?.user?.name || "User"}</p>
                  <p className="text-xs text-muted-foreground">{session?.user?.email || ""}</p>
                </TooltipContent>
              </Tooltip>

              <Tooltip>
                <TooltipTrigger asChild>
                  <Button
                    variant="ghost"
                    size="sm"
                    onClick={() => setTheme(theme === "dark" ? "light" : "dark")}
                    className="w-full text-muted-foreground hover:text-foreground hover:bg-muted"
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
                </TooltipTrigger>
                <TooltipContent side="right" className="bg-popover border-border">
                  {mounted ? (theme === "dark" ? "Light mode" : "Dark mode") : "Toggle theme"}
                </TooltipContent>
              </Tooltip>

              <Tooltip>
                <TooltipTrigger asChild>
                  <Button
                    variant="ghost"
                    size="sm"
                    onClick={() => router.push("/settings")}
                    className="w-full text-muted-foreground hover:text-foreground hover:bg-muted"
                    aria-label="Open settings"
                  >
                    <Settings className="h-4 w-4" />
                  </Button>
                </TooltipTrigger>
                <TooltipContent side="right" className="bg-popover border-border">
                  Settings
                </TooltipContent>
              </Tooltip>

              <Tooltip>
                <TooltipTrigger asChild>
                  <Button
                    variant="ghost"
                    size="sm"
                    onClick={() => signOut({ callbackUrl: '/' })}
                    className="w-full text-muted-foreground hover:text-rose-400 hover:bg-rose-500/10"
                    aria-label="Sign out"
                  >
                    <LogOut className="h-4 w-4" />
                  </Button>
                </TooltipTrigger>
                <TooltipContent side="right" className="bg-popover border-border">
                  Sign out
                </TooltipContent>
              </Tooltip>
            </div>
          </TooltipProvider>
        )}
      </div>
    </div>
  )
}
