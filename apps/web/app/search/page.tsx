"use client"

import { useState, useEffect, useCallback } from "react"
import { useQuery } from "@tanstack/react-query"
import { useRouter } from "next/navigation"
import {
  Search as SearchIcon,
  Loader2,
  Zap,
  BookOpen,
  SlidersHorizontal,
  ArrowUpDown,
  X,
  Sparkles,
  FileText,
  Brain,
} from "lucide-react"

import { AppShell } from "@/components/layout/app-shell"
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card"
import { Input } from "@/components/ui/input"
import { Button } from "@/components/ui/button"
import { Badge } from "@/components/ui/badge"
import { ScrollArea } from "@/components/ui/scroll-area"
import { Tabs, TabsList, TabsTrigger } from "@/components/ui/tabs"
import { Tooltip, TooltipContent, TooltipProvider, TooltipTrigger } from "@/components/ui/tooltip"
import { Popover, PopoverContent, PopoverTrigger } from "@/components/ui/popover"
import { Slider } from "@/components/ui/slider"
import { Label } from "@/components/ui/label"
import { api, type HybridSearchResult, type SearchMode } from "@/lib/api"
import { getEntityStyle } from "@/lib/constants"

// Score bar visualization
function ScoreBar({ label, score, color }: { label: string; score: number; color: string }) {
  return (
    <div className="flex items-center gap-2">
      <span className="text-[10px] text-slate-500 w-16 shrink-0">{label}</span>
      <div className="flex-1 h-1.5 rounded-full bg-white/[0.05] overflow-hidden">
        <div
          className="h-full rounded-full transition-all duration-500"
          style={{ width: `${Math.max(2, score * 100)}%`, backgroundColor: color }}
        />
      </div>
      <span className="text-[10px] text-slate-400 w-8 text-right">{(score * 100).toFixed(0)}%</span>
    </div>
  )
}

// Highlighted text for matched fields
function HighlightedField({ field, isMatched }: { field: string; isMatched: boolean }) {
  if (!isMatched) return null
  return (
    <Badge variant="outline" className="text-[9px] px-1.5 py-0 bg-violet-500/10 text-violet-400 border-violet-500/20">
      {field}
    </Badge>
  )
}

type SortOption = "relevance" | "date" | "confidence"

export default function SearchPage() {
  const router = useRouter()
  const [query, setQuery] = useState("")
  const [debouncedQuery, setDebouncedQuery] = useState("")
  const [searchMode, setSearchMode] = useState<SearchMode>("hybrid")
  const [searchType, setSearchType] = useState<"all" | "decision" | "entity">("all")
  const [sortBy, setSortBy] = useState<SortOption>("relevance")
  const [alpha, setAlpha] = useState(0.3)
  const [showOptions, setShowOptions] = useState(false)

  // Debounce search input
  useEffect(() => {
    const timer = setTimeout(() => {
      if (query.length >= 2) {
        setDebouncedQuery(query)
      } else {
        setDebouncedQuery("")
      }
    }, 300)
    return () => clearTimeout(timer)
  }, [query])

  const { data: results, isLoading } = useQuery({
    queryKey: ["hybrid-search", debouncedQuery, searchMode, searchType, alpha],
    queryFn: () =>
      api.hybridSearch(debouncedQuery, {
        topK: 20,
        threshold: 0.1,
        alpha: searchMode === "lexical" ? 1.0 : searchMode === "semantic" ? 0.0 : alpha,
        searchDecisions: searchType !== "entity",
        searchEntities: searchType !== "decision",
      }),
    enabled: debouncedQuery.length >= 2,
    staleTime: 30 * 1000,
  })

  // Sort results
  const sortedResults = results ? [...results].sort((a, b) => {
    switch (sortBy) {
      case "date":
        return new Date(b.data.created_at || 0).getTime() - new Date(a.data.created_at || 0).getTime()
      case "confidence":
        return (b.combined_score) - (a.combined_score)
      default:
        return b.combined_score - a.combined_score
    }
  }) : []

  const handleResultClick = useCallback((result: HybridSearchResult) => {
    if (result.type === "decision") {
      router.push(`/decisions?id=${result.id}`)
    } else {
      router.push(`/graph?focus=${result.id}`)
    }
  }, [router])

  return (
    <AppShell>
      <div className="h-full flex flex-col">
        {/* Header */}
        <div className="px-6 py-4 border-b border-white/[0.06] bg-slate-900/80 backdrop-blur-xl animate-in fade-in slide-in-from-top-4 duration-500">
          <h1 className="text-2xl font-bold tracking-tight gradient-text">Search</h1>
          <p className="text-sm text-slate-400">
            Find decisions, entities, and knowledge across your graph
          </p>
        </div>

        {/* Search Bar */}
        <div className="px-6 py-4 border-b border-white/[0.06] bg-slate-900/50 space-y-3">
          <div className="flex gap-3">
            <div className="relative flex-1">
              <SearchIcon className="absolute left-3 top-1/2 -translate-y-1/2 h-4 w-4 text-slate-500" />
              <Input
                placeholder="Search decisions, concepts, technologies..."
                value={query}
                onChange={(e) => setQuery(e.target.value)}
                className="pl-10 bg-white/[0.05] border-white/[0.1] text-slate-200 placeholder:text-slate-500 focus:border-violet-500/50 focus:ring-violet-500/20"
                autoFocus
              />
              {query && (
                <button
                  onClick={() => { setQuery(""); setDebouncedQuery("") }}
                  className="absolute right-3 top-1/2 -translate-y-1/2 text-slate-500 hover:text-slate-300"
                  aria-label="Clear search"
                >
                  <X className="h-4 w-4" />
                </button>
              )}
            </div>
            <Popover open={showOptions} onOpenChange={setShowOptions}>
              <PopoverTrigger asChild>
                <Button
                  variant="outline"
                  className="border-white/10 text-slate-300 hover:bg-white/[0.08]"
                  aria-label="Search options"
                >
                  <SlidersHorizontal className="h-4 w-4" />
                </Button>
              </PopoverTrigger>
              <PopoverContent className="w-72 bg-slate-900/95 border-white/10 backdrop-blur-xl" align="end">
                <div className="space-y-4">
                  <h4 className="font-medium text-sm text-slate-200">Search Options</h4>
                  <div className="space-y-3">
                    <div className="flex items-center justify-between">
                      <Label className="text-xs text-slate-400">Lexical / Semantic Balance</Label>
                      <span className="text-xs font-medium text-violet-400">
                        {Math.round(alpha * 100)}% lexical
                      </span>
                    </div>
                    <Slider
                      value={[alpha]}
                      onValueChange={(v) => setAlpha(v[0])}
                      min={0}
                      max={1}
                      step={0.1}
                      className="py-2"
                    />
                    <div className="flex justify-between text-[10px] text-slate-500">
                      <span>Semantic</span>
                      <span>Balanced</span>
                      <span>Exact match</span>
                    </div>
                  </div>
                </div>
              </PopoverContent>
            </Popover>
          </div>

          <div className="flex items-center gap-3">
            {/* Search mode toggle */}
            <Tabs value={searchMode} onValueChange={(v) => setSearchMode(v as SearchMode)} className="flex-shrink-0">
              <TabsList className="bg-white/[0.05] border border-white/[0.1] h-8">
                <TabsTrigger value="hybrid" className="data-[state=active]:bg-violet-500/20 data-[state=active]:text-violet-400 text-xs h-6 px-3">
                  <Sparkles className="h-3 w-3 mr-1" />
                  Smart
                </TabsTrigger>
                <TabsTrigger value="lexical" className="data-[state=active]:bg-violet-500/20 data-[state=active]:text-violet-400 text-xs h-6 px-3">
                  <BookOpen className="h-3 w-3 mr-1" />
                  Exact
                </TabsTrigger>
                <TabsTrigger value="semantic" className="data-[state=active]:bg-violet-500/20 data-[state=active]:text-violet-400 text-xs h-6 px-3">
                  <Brain className="h-3 w-3 mr-1" />
                  Semantic
                </TabsTrigger>
              </TabsList>
            </Tabs>

            {/* Type filter */}
            <Tabs value={searchType} onValueChange={(v) => setSearchType(v as typeof searchType)}>
              <TabsList className="bg-white/[0.05] border border-white/[0.1] h-8">
                <TabsTrigger value="all" className="data-[state=active]:bg-violet-500/20 data-[state=active]:text-violet-400 text-xs h-6 px-3">All</TabsTrigger>
                <TabsTrigger value="decision" className="data-[state=active]:bg-violet-500/20 data-[state=active]:text-violet-400 text-xs h-6 px-3">Decisions</TabsTrigger>
                <TabsTrigger value="entity" className="data-[state=active]:bg-violet-500/20 data-[state=active]:text-violet-400 text-xs h-6 px-3">Entities</TabsTrigger>
              </TabsList>
            </Tabs>

            <div className="flex-1" />

            {/* Sort */}
            {sortedResults.length > 0 && (
              <Popover>
                <PopoverTrigger asChild>
                  <Button variant="ghost" size="sm" className="text-xs text-slate-400 hover:text-slate-200 h-8">
                    <ArrowUpDown className="h-3 w-3 mr-1.5" />
                    {sortBy === "relevance" ? "Relevance" : sortBy === "date" ? "Date" : "Score"}
                  </Button>
                </PopoverTrigger>
                <PopoverContent className="w-40 bg-slate-900/95 border-white/10 p-1" align="end">
                  {(["relevance", "date", "confidence"] as SortOption[]).map((option) => (
                    <button
                      key={option}
                      onClick={() => setSortBy(option)}
                      className={`w-full text-left px-3 py-1.5 rounded text-sm transition-colors ${
                        sortBy === option ? "bg-violet-500/20 text-violet-300" : "text-slate-400 hover:text-slate-200 hover:bg-white/[0.05]"
                      }`}
                    >
                      {option.charAt(0).toUpperCase() + option.slice(1)}
                    </button>
                  ))}
                </PopoverContent>
              </Popover>
            )}
          </div>
        </div>

        {/* Results */}
        <ScrollArea className="flex-1 bg-slate-900/30">
          <div className="p-6 space-y-3">
            {/* Empty state */}
            {!debouncedQuery && (
              <div className="text-center py-16 animate-in fade-in duration-500">
                <div className="mx-auto mb-4 h-20 w-20 rounded-2xl bg-violet-500/10 flex items-center justify-center">
                  <SearchIcon className="h-10 w-10 text-violet-400/50" />
                </div>
                <p className="text-slate-400 text-lg">
                  Enter a search term to find decisions and entities
                </p>
                <p className="text-slate-500 text-sm mt-2 mb-6">
                  Try searching for technologies, concepts, or decision triggers
                </p>
                <div className="flex flex-wrap gap-2 justify-center max-w-md mx-auto">
                  {["authentication", "database", "React", "API design", "caching"].map((suggestion) => (
                    <button
                      key={suggestion}
                      onClick={() => setQuery(suggestion)}
                      className="px-3 py-1.5 rounded-full text-xs bg-white/[0.05] border border-white/[0.1] text-slate-400 hover:text-violet-400 hover:border-violet-500/30 transition-colors"
                    >
                      {suggestion}
                    </button>
                  ))}
                </div>
              </div>
            )}

            {/* Loading */}
            {debouncedQuery && isLoading && (
              <div className="text-center py-12 animate-in fade-in duration-300">
                <Loader2 className="h-8 w-8 animate-spin mx-auto mb-4 text-violet-400" />
                <p className="text-slate-400">Searching for &quot;{debouncedQuery}&quot;...</p>
              </div>
            )}

            {/* No results */}
            {debouncedQuery && !isLoading && sortedResults.length === 0 && (
              <div className="text-center py-12 animate-in fade-in duration-300">
                <div className="mx-auto mb-4 h-16 w-16 rounded-2xl bg-slate-500/10 flex items-center justify-center">
                  <SearchIcon className="h-8 w-8 text-slate-500" />
                </div>
                <p className="text-slate-400">No results found for &quot;{debouncedQuery}&quot;</p>
                <p className="text-slate-500 text-sm mt-2">Try a different search term or search mode</p>
              </div>
            )}

            {/* Result count */}
            {sortedResults.length > 0 && (
              <div className="flex items-center gap-2 text-xs text-slate-500 pb-1">
                <span>{sortedResults.length} results</span>
                <span className="text-slate-700">|</span>
                <span>{searchMode === "hybrid" ? "Smart search" : searchMode === "lexical" ? "Exact match" : "Semantic search"}</span>
              </div>
            )}

            {/* Results */}
            {sortedResults.map((result, index) => {
              const isDecision = result.type === "decision"
              const entityType = result.data.type || "concept"

              return (
                <Card
                  key={result.id}
                  className="bg-white/[0.03] border-white/[0.06] hover:bg-white/[0.06] hover:border-violet-500/30 hover:shadow-[0_0_20px_rgba(139,92,246,0.1)] transition-all duration-300 cursor-pointer group animate-in fade-in slide-in-from-bottom-4"
                  style={{ animationDelay: `${index * 30}ms`, animationFillMode: "backwards" }}
                  onClick={() => handleResultClick(result)}
                >
                  <CardHeader className="pb-2">
                    <div className="flex items-start justify-between gap-2">
                      <div className="flex items-center gap-2 flex-1 min-w-0">
                        {isDecision ? (
                          <Badge className="bg-violet-500/20 text-violet-300 border-violet-500/30 shrink-0">
                            <FileText className="h-3 w-3 mr-1" />
                            Decision
                          </Badge>
                        ) : (
                          <Badge className={`${getEntityStyle(entityType).bg} ${getEntityStyle(entityType).text} ${getEntityStyle(entityType).border} shrink-0`}>
                            {entityType}
                          </Badge>
                        )}
                        <CardTitle className="text-sm text-slate-200 group-hover:text-violet-300 transition-colors truncate">
                          {result.label}
                        </CardTitle>
                      </div>
                      {result.data.source && (
                        <Badge variant="outline" className="text-[9px] px-1.5 py-0 text-slate-500 border-slate-700 shrink-0">
                          {result.data.source.replace("_", " ")}
                        </Badge>
                      )}
                    </div>
                  </CardHeader>
                  <CardContent className="space-y-2">
                    {isDecision && (result.data.agent_decision || result.data.decision) && (
                      <TooltipProvider>
                        <Tooltip>
                          <TooltipTrigger asChild>
                            <p className="text-xs text-slate-400 line-clamp-2 cursor-help">
                              {result.data.agent_decision || result.data.decision}
                            </p>
                          </TooltipTrigger>
                          <TooltipContent side="bottom" className="max-w-lg bg-slate-800 border-white/10">
                            <p>{result.data.agent_decision || result.data.decision}</p>
                          </TooltipContent>
                        </Tooltip>
                      </TooltipProvider>
                    )}

                    {/* Score bars */}
                    <div className="space-y-1 pt-1">
                      {searchMode === "hybrid" && (
                        <>
                          <ScoreBar label="Combined" score={result.combined_score} color="#a78bfa" />
                          <ScoreBar label="Lexical" score={result.lexical_score} color="#22d3ee" />
                          <ScoreBar label="Semantic" score={result.semantic_score} color="#ec4899" />
                        </>
                      )}
                      {searchMode === "lexical" && (
                        <ScoreBar label="Match" score={result.lexical_score} color="#22d3ee" />
                      )}
                      {searchMode === "semantic" && (
                        <ScoreBar label="Similarity" score={result.semantic_score} color="#ec4899" />
                      )}
                    </div>

                    {/* Matched fields */}
                    {result.matched_fields.length > 0 && (
                      <div className="flex flex-wrap gap-1 pt-1">
                        <span className="text-[10px] text-slate-600 mr-1">Matched:</span>
                        {result.matched_fields.map((field) => (
                          <HighlightedField key={field} field={field} isMatched={true} />
                        ))}
                      </div>
                    )}
                  </CardContent>
                </Card>
              )
            })}
          </div>
        </ScrollArea>
      </div>
    </AppShell>
  )
}
