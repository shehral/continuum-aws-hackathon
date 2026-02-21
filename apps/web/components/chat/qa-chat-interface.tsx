"use client"

import { useState, useRef, useEffect, useCallback } from "react"
import { Send, Loader2, Bot, User, Sparkles, BookOpen } from "lucide-react"

import { Button } from "@/components/ui/button"
import { Input } from "@/components/ui/input"
import { ScrollArea } from "@/components/ui/scroll-area"
import { Badge } from "@/components/ui/badge"
import { Avatar, AvatarFallback } from "@/components/ui/avatar"
import type { ChatMessage, SourceDecision, MentionedEntity } from "@/lib/api"
import { cn } from "@/lib/utils"

// ---------------------------------------------------------------------------
// Markdown-lite renderer (handles bold, code, lists, citations)
// ---------------------------------------------------------------------------

function renderContent(text: string, onCitationClick?: (id: string) => void) {
  const lines = text.split("\n")
  const elements: React.ReactNode[] = []

  lines.forEach((line, lineIdx) => {
    if (lineIdx > 0) elements.push(<br key={`br-${lineIdx}`} />)

    // Process inline formatting
    const parts = line.split(/(\*\*.*?\*\*|`[^`]+`|\[DEC-[^\]]+\])/g)

    parts.forEach((part, partIdx) => {
      const key = `${lineIdx}-${partIdx}`

      if (part.startsWith("**") && part.endsWith("**")) {
        // Bold
        elements.push(
          <strong key={key} className="font-semibold text-slate-100">
            {part.slice(2, -2)}
          </strong>
        )
      } else if (part.startsWith("`") && part.endsWith("`")) {
        // Inline code
        elements.push(
          <code
            key={key}
            className="px-1.5 py-0.5 rounded bg-white/[0.08] text-violet-300 text-[11px] font-mono"
          >
            {part.slice(1, -1)}
          </code>
        )
      } else if (part.match(/^\[DEC-([^\]]+)\]$/)) {
        // Citation badge
        const decId = part.match(/^\[DEC-([^\]]+)\]$/)?.[1] ?? ""
        elements.push(
          <button
            key={key}
            onClick={() => onCitationClick?.(decId)}
            className="inline-flex items-center gap-0.5 px-1.5 py-0.5 rounded-full bg-violet-500/15 border border-violet-500/30 text-violet-300 text-[10px] font-medium hover:bg-violet-500/25 transition-colors cursor-pointer mx-0.5"
          >
            <BookOpen className="h-2.5 w-2.5" />
            {decId.slice(0, 7)}
          </button>
        )
      } else {
        elements.push(<span key={key}>{part}</span>)
      }
    })
  })

  return elements
}

// ---------------------------------------------------------------------------
// Message bubble
// ---------------------------------------------------------------------------

function MessageBubble({
  message,
  isNew = false,
  onCitationClick,
}: {
  message: ChatMessage
  isNew?: boolean
  onCitationClick?: (id: string) => void
}) {
  const isUser = message.role === "user"

  return (
    <div
      className={cn(
        "flex gap-3 mb-4",
        isUser ? "flex-row-reverse" : "flex-row",
        isNew && "animate-in fade-in slide-in-from-bottom-2 duration-300"
      )}
    >
      <Avatar
        className={cn(
          "h-9 w-9 shrink-0 ring-2 ring-offset-2 ring-offset-slate-950",
          isUser ? "ring-violet-500/50" : "ring-fuchsia-500/50"
        )}
        aria-hidden="true"
      >
        <AvatarFallback
          className={cn(
            "text-sm font-medium",
            isUser
              ? "bg-gradient-to-br from-violet-500 to-fuchsia-500 text-white"
              : "bg-gradient-to-br from-fuchsia-500/20 to-rose-500/20 text-fuchsia-400"
          )}
        >
          {isUser ? <User className="h-4 w-4" /> : <Bot className="h-4 w-4" />}
        </AvatarFallback>
      </Avatar>

      <div className="relative max-w-[80%]">
        <div
          className={cn(
            "rounded-2xl px-4 py-3 shadow-lg",
            isUser
              ? "bg-gradient-to-r from-violet-500 to-fuchsia-500 text-white rounded-br-md shadow-violet-500/20"
              : "bg-white/[0.05] border border-white/[0.1] text-slate-200 rounded-bl-md"
          )}
        >
          {isUser ? (
            <p className="text-sm whitespace-pre-wrap leading-relaxed">{message.content}</p>
          ) : (
            <div className="text-sm whitespace-pre-wrap leading-relaxed">
              {renderContent(message.content, onCitationClick)}
            </div>
          )}

          {/* Mentioned entities */}
          {message.mentioned_entities && message.mentioned_entities.length > 0 && (
            <div className="mt-3 pt-2 border-t border-white/10 flex flex-wrap gap-1.5">
              {message.mentioned_entities.map((entity) => (
                <Badge
                  key={entity.name}
                  variant="outline"
                  className="text-[10px] bg-violet-500/10 border-violet-500/30 text-violet-300"
                >
                  <Sparkles className="h-2.5 w-2.5 mr-1" />
                  {entity.name}
                  <span className="ml-1 text-violet-400/50">({entity.type})</span>
                </Badge>
              ))}
            </div>
          )}
        </div>

        {/* Message tail */}
        {!isUser && (
          <div className="absolute -left-2 top-3 w-3 h-3 bg-white/[0.05] border-l border-b border-white/[0.1] transform rotate-45" />
        )}
      </div>
    </div>
  )
}

// ---------------------------------------------------------------------------
// Streaming bubble (partial content being received)
// ---------------------------------------------------------------------------

function StreamingBubble({
  content,
  onCitationClick,
}: {
  content: string
  onCitationClick?: (id: string) => void
}) {
  return (
    <div className="flex gap-3 mb-4 animate-in fade-in duration-200">
      <Avatar
        className="h-9 w-9 shrink-0 ring-2 ring-offset-2 ring-offset-slate-950 ring-fuchsia-500/50"
        aria-hidden="true"
      >
        <AvatarFallback className="bg-gradient-to-br from-fuchsia-500/20 to-rose-500/20 text-fuchsia-400">
          <Bot className="h-4 w-4" />
        </AvatarFallback>
      </Avatar>

      <div className="relative max-w-[80%]">
        <div className="bg-white/[0.05] border border-white/[0.1] text-slate-200 rounded-2xl rounded-bl-md px-4 py-3 shadow-lg">
          <div className="text-sm whitespace-pre-wrap leading-relaxed">
            {renderContent(content, onCitationClick)}
            <span className="inline-block w-2 h-4 ml-0.5 bg-violet-400/70 animate-pulse rounded-sm" />
          </div>
        </div>
        <div className="absolute -left-2 top-3 w-3 h-3 bg-white/[0.05] border-l border-b border-white/[0.1] transform rotate-45" />
      </div>
    </div>
  )
}

// ---------------------------------------------------------------------------
// Typing indicator
// ---------------------------------------------------------------------------

function TypingIndicator() {
  return (
    <div
      className="flex gap-3 mb-4 animate-in fade-in duration-300"
      role="status"
      aria-label="AI is thinking"
    >
      <Avatar
        className="h-9 w-9 shrink-0 ring-2 ring-offset-2 ring-offset-slate-950 ring-fuchsia-500/50"
        aria-hidden="true"
      >
        <AvatarFallback className="bg-gradient-to-br from-fuchsia-500/20 to-rose-500/20 text-fuchsia-400">
          <Bot className="h-4 w-4" />
        </AvatarFallback>
      </Avatar>
      <div className="relative">
        <div className="bg-white/[0.05] border border-white/[0.1] rounded-2xl rounded-bl-md px-4 py-3">
          <div className="flex gap-1.5" aria-hidden="true">
            <span
              className="w-2 h-2 bg-gradient-to-r from-violet-400 to-fuchsia-400 rounded-full animate-bounce"
              style={{ animationDelay: "0ms" }}
            />
            <span
              className="w-2 h-2 bg-gradient-to-r from-fuchsia-400 to-rose-400 rounded-full animate-bounce"
              style={{ animationDelay: "150ms" }}
            />
            <span
              className="w-2 h-2 bg-gradient-to-r from-rose-400 to-orange-400 rounded-full animate-bounce"
              style={{ animationDelay: "300ms" }}
            />
          </div>
          <span className="sr-only">AI is thinking about your question</span>
        </div>
        <div className="absolute -left-2 top-3 w-3 h-3 bg-white/[0.05] border-l border-b border-white/[0.1] transform rotate-45" />
      </div>
    </div>
  )
}

// ---------------------------------------------------------------------------
// Main interface
// ---------------------------------------------------------------------------

interface QAChatInterfaceProps {
  messages: ChatMessage[]
  onSendMessage: (content: string) => void
  isStreaming: boolean
  streamingContent: string
  isThinking: boolean
  onCitationClick?: (decisionId: string) => void
}

export function QAChatInterface({
  messages,
  onSendMessage,
  isStreaming,
  streamingContent,
  isThinking,
  onCitationClick,
}: QAChatInterfaceProps) {
  const [input, setInput] = useState("")
  const scrollRef = useRef<HTMLDivElement>(null)
  const inputRef = useRef<HTMLInputElement>(null)

  // Scroll to bottom on new messages or streaming content
  useEffect(() => {
    if (scrollRef.current) {
      scrollRef.current.scrollTop = scrollRef.current.scrollHeight
    }
  }, [messages, streamingContent, isThinking])

  const handleSubmit = useCallback(
    (e: React.FormEvent) => {
      e.preventDefault()
      if (!input.trim() || isStreaming || isThinking) return

      onSendMessage(input.trim())
      setInput("")
      inputRef.current?.focus()
    },
    [input, isStreaming, isThinking, onSendMessage]
  )

  return (
    <div className="flex flex-col h-full">
      {/* Messages */}
      <ScrollArea
        ref={scrollRef}
        className="flex-1 p-6"
        role="log"
        aria-label="Chat messages"
        aria-live="polite"
      >
        {messages.map((message, index) => (
          <MessageBubble
            key={message.id}
            message={message}
            isNew={index === messages.length - 1}
            onCitationClick={onCitationClick}
          />
        ))}

        {isThinking && !streamingContent && <TypingIndicator />}

        {streamingContent && (
          <StreamingBubble content={streamingContent} onCitationClick={onCitationClick} />
        )}
      </ScrollArea>

      {/* Input */}
      <form
        onSubmit={handleSubmit}
        className="p-4 border-t border-white/[0.06] bg-slate-950/80 backdrop-blur-xl"
      >
        <div className="flex gap-3">
          <Input
            ref={inputRef}
            value={input}
            onChange={(e) => setInput(e.target.value)}
            placeholder="Ask about architecture, decisions, or how the codebase evolved..."
            disabled={isStreaming || isThinking}
            aria-label="Type your question"
            className="flex-1 bg-white/[0.03] border-white/[0.1] text-slate-200 placeholder:text-slate-500 focus:border-violet-500/50 focus:ring-2 focus:ring-violet-500/20 rounded-xl"
          />
          <Button
            type="submit"
            disabled={!input.trim() || isStreaming || isThinking}
            variant="gradient"
            aria-label={isStreaming ? "Generating response" : "Send question"}
          >
            {isStreaming || isThinking ? (
              <Loader2 className="h-4 w-4 animate-spin" />
            ) : (
              <Send className="h-4 w-4" />
            )}
          </Button>
        </div>
      </form>
    </div>
  )
}
