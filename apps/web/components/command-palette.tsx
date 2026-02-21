"use client"

import { useCallback, useEffect, useState } from "react"
import { useRouter } from "next/navigation"
import { useTheme } from "next-themes"
import { useQuery } from "@tanstack/react-query"
import {
  LayoutDashboard,
  Brain,
  Network,
  ClipboardList,
  Search,
  Folder,
  Settings,
  Plus,
  MessageSquare,
  Sun,
  Moon,
  FileText,
  Sparkles,
} from "lucide-react"

import {
  CommandDialog,
  CommandEmpty,
  CommandGroup,
  CommandInput,
  CommandItem,
  CommandList,
  CommandSeparator,
} from "@/components/ui/command"
import { api } from "@/lib/api"

const PAGES = [
  { name: "Dashboard", href: "/", icon: LayoutDashboard },
  { name: "Add Knowledge", href: "/add", icon: Brain },
  { name: "Knowledge Graph", href: "/graph", icon: Network },
  { name: "Decisions", href: "/decisions", icon: ClipboardList },
  { name: "Projects", href: "/projects", icon: Folder },
  { name: "Search", href: "/search", icon: Search },
  { name: "Settings", href: "/settings", icon: Settings },
]

const ACTIONS = [
  { name: "New Decision", href: "/decisions?add=true", icon: Plus },
  { name: "Start Capture Session", href: "/capture", icon: MessageSquare },
  { name: "Import Claude Logs", href: "/add", icon: FileText },
]

export function CommandPalette() {
  const [open, setOpen] = useState(false)
  const [search, setSearch] = useState("")
  const router = useRouter()
  const { theme, setTheme } = useTheme()

  // Search results from API (only when user types a query)
  const { data: searchResults } = useQuery({
    queryKey: ["cmd-search", search],
    queryFn: () => api.search(search),
    enabled: search.length >= 2,
    staleTime: 30 * 1000,
  })

  // Register global keyboard shortcut
  useEffect(() => {
    const handleKeyDown = (e: KeyboardEvent) => {
      if ((e.metaKey || e.ctrlKey) && e.key === "k") {
        e.preventDefault()
        setOpen((prev) => !prev)
      }
    }

    document.addEventListener("keydown", handleKeyDown)
    return () => document.removeEventListener("keydown", handleKeyDown)
  }, [])

  const runAction = useCallback(
    (href: string) => {
      setOpen(false)
      setSearch("")
      router.push(href)
    },
    [router]
  )

  const toggleTheme = useCallback(() => {
    setTheme(theme === "dark" ? "light" : "dark")
    setOpen(false)
    setSearch("")
  }, [theme, setTheme])

  return (
    <CommandDialog open={open} onOpenChange={setOpen}>
      <CommandInput
        placeholder="Search pages, decisions, entities..."
        value={search}
        onValueChange={setSearch}
      />
      <CommandList>
        <CommandEmpty>No results found.</CommandEmpty>

        {/* Live search results */}
        {searchResults && searchResults.length > 0 && (
          <>
            <CommandGroup heading="Results">
              {searchResults.slice(0, 5).map((result) => (
                <CommandItem
                  key={result.id}
                  onSelect={() => {
                    const href = result.type === "decision"
                      ? `/decisions?id=${result.id}`
                      : `/graph?focus=${result.id}`
                    runAction(href)
                  }}
                >
                  {result.type === "decision" ? (
                    <ClipboardList className="mr-2 h-4 w-4 text-violet-400" />
                  ) : (
                    <Sparkles className="mr-2 h-4 w-4 text-fuchsia-400" />
                  )}
                  <span>{result.label}</span>
                  <span className="ml-auto text-xs text-slate-500">{result.type}</span>
                </CommandItem>
              ))}
            </CommandGroup>
            <CommandSeparator />
          </>
        )}

        <CommandGroup heading="Pages">
          {PAGES.map((page) => (
            <CommandItem key={page.href} onSelect={() => runAction(page.href)}>
              <page.icon className="mr-2 h-4 w-4 text-slate-400" />
              <span>{page.name}</span>
            </CommandItem>
          ))}
        </CommandGroup>

        <CommandSeparator />

        <CommandGroup heading="Actions">
          {ACTIONS.map((action) => (
            <CommandItem key={action.href} onSelect={() => runAction(action.href)}>
              <action.icon className="mr-2 h-4 w-4 text-violet-400" />
              <span>{action.name}</span>
            </CommandItem>
          ))}
          <CommandItem onSelect={toggleTheme}>
            {theme === "dark" ? (
              <Sun className="mr-2 h-4 w-4 text-amber-400" />
            ) : (
              <Moon className="mr-2 h-4 w-4 text-violet-400" />
            )}
            <span>Toggle {theme === "dark" ? "Light" : "Dark"} Mode</span>
          </CommandItem>
        </CommandGroup>
      </CommandList>
    </CommandDialog>
  )
}
