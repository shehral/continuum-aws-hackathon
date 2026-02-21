"use client"

import { useState, useCallback } from "react"
import {
  Plus,
  MessageCircle,
  History,
  PanelRightOpen,
  PanelRightClose,
  X,
  Clock,
} from "lucide-react"

import { AppShell } from "@/components/layout/app-shell"
import { QAChatInterface } from "@/components/chat/qa-chat-interface"
import { SourceCitationsPanel } from "@/components/chat/source-citations-panel"
import { SuggestedQuestions } from "@/components/chat/suggested-questions"
import { Button } from "@/components/ui/button"
import { ScrollArea } from "@/components/ui/scroll-area"
import { Badge } from "@/components/ui/badge"
import type { ChatMessage, ChatSessionListItem, SourceDecision } from "@/lib/api"
import {
  SUGGESTED_QUESTIONS,
  MOCK_SESSION_LIST,
  createMockSession,
  getMockResponse,
  generateMockTitle,
  simulateStream,
} from "@/lib/mock-chat-data"
import { cn } from "@/lib/utils"

export default function ChatPage() {
  // Session state
  const [activeSessionId, setActiveSessionId] = useState<string | null>(null)
  const [sessionTitle, setSessionTitle] = useState<string | null>(null)
  const [messages, setMessages] = useState<ChatMessage[]>([])

  // Streaming state
  const [isThinking, setIsThinking] = useState(false)
  const [isStreaming, setIsStreaming] = useState(false)
  const [streamingContent, setStreamingContent] = useState("")

  // Source citations
  const [sourceDecisions, setSourceDecisions] = useState<SourceDecision[]>([])
  const [showSources, setShowSources] = useState(false)

  // Session history
  const [showHistory, setShowHistory] = useState(false)
  const [sessionList] = useState<ChatSessionListItem[]>(MOCK_SESSION_LIST)

  // Message counter for generating unique IDs
  const [msgCounter, setMsgCounter] = useState(0)

  const handleSendMessage = useCallback(
    async (content: string) => {
      // Create session if needed
      let sessionId = activeSessionId
      if (!sessionId) {
        const session = createMockSession()
        sessionId = session.id
        setActiveSessionId(sessionId)
        setSessionTitle(generateMockTitle(content))
      }

      // Add user message
      const userMsgId = `msg-${msgCounter}`
      setMsgCounter((c) => c + 1)
      const userMessage: ChatMessage = {
        id: userMsgId,
        role: "user",
        content,
        timestamp: new Date().toISOString(),
      }
      setMessages((prev) => [...prev, userMessage])

      // Show thinking state
      setIsThinking(true)
      setStreamingContent("")

      // Get mock response
      const response = getMockResponse(content)

      // Simulate streaming
      setIsThinking(false)
      setIsStreaming(true)

      await simulateStream(response.content, (chunk) => {
        setStreamingContent((prev) => prev + chunk)
      })

      // Streaming complete — finalize
      const assistantMsgId = `msg-${msgCounter + 1}`
      setMsgCounter((c) => c + 2)
      const assistantMessage: ChatMessage = {
        id: assistantMsgId,
        role: "assistant",
        content: response.content,
        timestamp: new Date().toISOString(),
        source_decisions: response.sourceDecisions,
        mentioned_entities: response.mentionedEntities,
      }

      setMessages((prev) => [...prev, assistantMessage])
      setStreamingContent("")
      setIsStreaming(false)

      // Show source citations
      if (response.sourceDecisions.length > 0) {
        setSourceDecisions(response.sourceDecisions)
        setShowSources(true)
      }
    },
    [activeSessionId, msgCounter]
  )

  const handleNewChat = useCallback(() => {
    setActiveSessionId(null)
    setSessionTitle(null)
    setMessages([])
    setStreamingContent("")
    setIsStreaming(false)
    setIsThinking(false)
    setSourceDecisions([])
    setShowSources(false)
  }, [])

  const handleLoadSession = useCallback(
    (session: ChatSessionListItem) => {
      // In mock mode, just create a placeholder
      setActiveSessionId(session.id)
      setSessionTitle(session.title)
      setMessages([])
      setSourceDecisions([])
      setShowSources(false)
      setShowHistory(false)
    },
    []
  )

  const handleCitationClick = useCallback(
    (decisionId: string) => {
      // Scroll to or highlight the cited decision in the sources panel
      if (!showSources) setShowSources(true)
    },
    [showSources]
  )

  const isEmptyState = messages.length === 0 && !isStreaming && !isThinking

  return (
    <AppShell>
      <div className="h-full flex">
        {/* ---------------------------------------------------------------- */}
        {/* Session history sidebar (left) */}
        {/* ---------------------------------------------------------------- */}
        {showHistory && (
          <div className="w-64 border-r border-white/[0.06] bg-card/95 backdrop-blur-xl flex flex-col animate-in slide-in-from-left-4 duration-300">
            <div className="p-4 border-b border-white/[0.06] flex items-center justify-between shrink-0">
              <h3 className="text-sm font-medium text-slate-200 flex items-center gap-2">
                <History className="h-4 w-4 text-violet-400" />
                Chat History
              </h3>
              <Button
                variant="ghost"
                size="sm"
                onClick={() => setShowHistory(false)}
                className="h-7 w-7 p-0 text-slate-400 hover:text-slate-200"
              >
                <X className="h-4 w-4" />
              </Button>
            </div>

            <ScrollArea className="flex-1">
              <div className="p-2">
                {sessionList.map((session) => (
                  <button
                    key={session.id}
                    onClick={() => handleLoadSession(session)}
                    className={cn(
                      "w-full text-left p-3 rounded-xl transition-all duration-200",
                      "hover:bg-white/[0.05] group",
                      activeSessionId === session.id && "bg-violet-500/10 border border-violet-500/20"
                    )}
                  >
                    <p className="text-sm font-medium text-slate-200 truncate group-hover:text-white">
                      {session.title || "Untitled"}
                    </p>
                    <p className="text-xs text-slate-500 truncate mt-1">
                      {session.last_message_preview}
                    </p>
                    <div className="flex items-center gap-2 mt-2">
                      <Clock className="h-3 w-3 text-slate-600" />
                      <span className="text-[10px] text-slate-600">
                        {new Date(session.updated_at).toLocaleDateString()}
                      </span>
                      <Badge
                        variant="outline"
                        className="text-[10px] bg-white/[0.03] border-white/[0.1] text-slate-500 ml-auto"
                      >
                        {session.message_count} msgs
                      </Badge>
                    </div>
                  </button>
                ))}
              </div>
            </ScrollArea>
          </div>
        )}

        {/* ---------------------------------------------------------------- */}
        {/* Main chat area (center) */}
        {/* ---------------------------------------------------------------- */}
        <div className="flex-1 flex flex-col min-w-0">
          {/* Header */}
          <div className="flex items-center justify-between px-6 py-4 border-b border-white/[0.06] bg-card/50 backdrop-blur-xl shrink-0">
            <div>
              <h1 className="text-xl font-bold text-slate-100">
                {sessionTitle || "Ask the Codebase"}
              </h1>
              <p className="text-xs text-slate-500 mt-0.5">
                Understand architecture decisions, technology choices, and code evolution
              </p>
            </div>
            <div className="flex items-center gap-2">
              <Button
                variant="ghost"
                size="sm"
                onClick={() => setShowHistory(!showHistory)}
                className={cn(
                  "text-slate-400 hover:text-slate-200",
                  showHistory && "bg-violet-500/10 text-violet-400"
                )}
              >
                <History className="h-4 w-4 mr-2" />
                History
              </Button>
              <Button
                variant="ghost"
                size="sm"
                onClick={() => setShowSources(!showSources)}
                className={cn(
                  "text-slate-400 hover:text-slate-200",
                  showSources && "bg-violet-500/10 text-violet-400"
                )}
                disabled={sourceDecisions.length === 0}
              >
                {showSources ? (
                  <PanelRightClose className="h-4 w-4 mr-2" />
                ) : (
                  <PanelRightOpen className="h-4 w-4 mr-2" />
                )}
                Sources
                {sourceDecisions.length > 0 && (
                  <Badge
                    variant="outline"
                    className="ml-1.5 text-[10px] bg-violet-500/10 border-violet-500/30 text-violet-400"
                  >
                    {sourceDecisions.length}
                  </Badge>
                )}
              </Button>
              <Button
                variant="gradient"
                size="sm"
                onClick={handleNewChat}
              >
                <Plus className="h-4 w-4 mr-2" />
                New Chat
              </Button>
            </div>
          </div>

          {/* Chat or empty state */}
          {isEmptyState ? (
            <div className="flex-1 flex items-center justify-center p-6">
              <div className="text-center max-w-2xl animate-in fade-in duration-500">
                <div className="mx-auto mb-6 h-20 w-20 rounded-2xl bg-gradient-to-br from-violet-500/20 to-fuchsia-500/10 border border-violet-500/20 flex items-center justify-center">
                  <MessageCircle className="h-10 w-10 text-violet-400" />
                </div>
                <h2 className="text-2xl font-bold text-slate-100 mb-2">
                  What would you like to know?
                </h2>
                <p className="text-sm text-slate-500 mb-8 max-w-md mx-auto">
                  Ask about architectural decisions, technology choices, or how systems
                  have evolved. Answers are grounded in the team&apos;s knowledge graph.
                </p>
                <SuggestedQuestions
                  questions={SUGGESTED_QUESTIONS}
                  onSelect={handleSendMessage}
                />
              </div>
            </div>
          ) : (
            <QAChatInterface
              messages={messages}
              onSendMessage={handleSendMessage}
              isStreaming={isStreaming}
              streamingContent={streamingContent}
              isThinking={isThinking}
              onCitationClick={handleCitationClick}
            />
          )}
        </div>

        {/* ---------------------------------------------------------------- */}
        {/* Source citations sidebar (right) */}
        {/* ---------------------------------------------------------------- */}
        {showSources && sourceDecisions.length > 0 && (
          <SourceCitationsPanel
            decisions={sourceDecisions}
            onClose={() => setShowSources(false)}
          />
        )}
      </div>
    </AppShell>
  )
}
