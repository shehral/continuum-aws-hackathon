"use client"

import { useState, useRef, useEffect } from "react"
import { Send, Loader2, MessageCircle, Bot, User, Sparkles } from "lucide-react"

import { Button } from "@/components/ui/button"
import { Input } from "@/components/ui/input"
import { ScrollArea } from "@/components/ui/scroll-area"
import { Badge } from "@/components/ui/badge"
import { Avatar, AvatarFallback } from "@/components/ui/avatar"
import { type CaptureMessage, type Entity } from "@/lib/api"
import { cn } from "@/lib/utils"

interface ChatInterfaceProps {
  messages: CaptureMessage[]
  onSendMessage: (content: string) => Promise<void>
  isLoading: boolean
  suggestedEntities?: Entity[]
  onLinkEntity?: (entity: Entity) => void
}

function MessageBubble({ message, isNew = false }: { message: CaptureMessage; isNew?: boolean }) {
  const isUser = message.role === "user"

  return (
    <div
      className={cn(
        "flex gap-3 mb-4",
        isUser ? "flex-row-reverse" : "flex-row",
        isNew && "animate-in fade-in slide-in-from-bottom-2 duration-300"
      )}
    >
      <Avatar className={cn(
        "h-9 w-9 shrink-0 ring-2 ring-offset-2 ring-offset-slate-950",
        isUser ? "ring-violet-500/50" : "ring-fuchsia-500/50"
      )} aria-hidden="true">
        <AvatarFallback className={cn(
          "text-sm font-medium",
          isUser
            ? "bg-gradient-to-br from-violet-500 to-fuchsia-500 text-white"
            : "bg-gradient-to-br from-fuchsia-500/20 to-rose-500/20 text-fuchsia-400"
        )}>
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
          <p className="text-sm whitespace-pre-wrap leading-relaxed">{message.content}</p>
          {message.extracted_entities && message.extracted_entities.length > 0 && (
            <div className="mt-3 pt-2 border-t border-white/10 flex flex-wrap gap-1.5">
              {message.extracted_entities.map((entity) => (
                <Badge
                  key={entity.id}
                  variant="outline"
                  className={cn(
                    "text-xs transition-all hover:scale-105",
                    isUser
                      ? "bg-white/20 border-white/30 text-white"
                      : "bg-violet-500/10 border-violet-500/30 text-violet-300"
                  )}
                >
                  <Sparkles className="h-3 w-3 mr-1" />
                  {entity.name}
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

// Typing indicator with animated dots
function TypingIndicator() {
  return (
    <div className="flex gap-3 mb-4 animate-in fade-in duration-300" role="status" aria-label="AI is typing">
      <Avatar className="h-9 w-9 shrink-0 ring-2 ring-offset-2 ring-offset-slate-950 ring-fuchsia-500/50" aria-hidden="true">
        <AvatarFallback className="bg-gradient-to-br from-fuchsia-500/20 to-rose-500/20 text-fuchsia-400">
          <Bot className="h-4 w-4" />
        </AvatarFallback>
      </Avatar>
      <div className="relative">
        <div className="bg-white/[0.05] border border-white/[0.1] rounded-2xl rounded-bl-md px-4 py-3">
          <div className="flex gap-1.5" aria-hidden="true">
            <span className="w-2 h-2 bg-gradient-to-r from-violet-400 to-fuchsia-400 rounded-full animate-bounce" style={{ animationDelay: '0ms' }} />
            <span className="w-2 h-2 bg-gradient-to-r from-fuchsia-400 to-rose-400 rounded-full animate-bounce" style={{ animationDelay: '150ms' }} />
            <span className="w-2 h-2 bg-gradient-to-r from-rose-400 to-orange-400 rounded-full animate-bounce" style={{ animationDelay: '300ms' }} />
          </div>
          <span className="sr-only">AI is typing a response</span>
        </div>
        <div className="absolute -left-2 top-3 w-3 h-3 bg-white/[0.05] border-l border-b border-white/[0.1] transform rotate-45" />
      </div>
    </div>
  )
}

export function ChatInterface({
  messages,
  onSendMessage,
  isLoading,
  suggestedEntities,
  onLinkEntity,
}: ChatInterfaceProps) {
  const [input, setInput] = useState("")
  const scrollRef = useRef<HTMLDivElement>(null)
  const inputRef = useRef<HTMLInputElement>(null)

  // Scroll to bottom on new messages
  useEffect(() => {
    if (scrollRef.current) {
      scrollRef.current.scrollTop = scrollRef.current.scrollHeight
    }
  }, [messages])

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault()
    if (!input.trim() || isLoading) return

    const message = input.trim()
    setInput("")
    await onSendMessage(message)
    inputRef.current?.focus()
  }

  return (
    <div className="flex flex-col h-full bg-slate-950/50">
      {/* Messages */}
      <ScrollArea ref={scrollRef} className="flex-1 p-6" role="log" aria-label="Chat messages" aria-live="polite">
        {messages.length === 0 ? (
          <div className="h-full flex items-center justify-center text-center">
            <div className="animate-in fade-in duration-500">
              <div className="mx-auto mb-4 h-20 w-20 rounded-2xl bg-gradient-to-br from-violet-500/20 to-fuchsia-500/10 border border-violet-500/20 flex items-center justify-center">
                <MessageCircle className="h-10 w-10 text-violet-400" />
              </div>
              <p className="text-slate-200 mb-2 font-medium text-lg">
                Start a conversation
              </p>
              <p className="text-sm text-slate-500 max-w-xs mx-auto">
                I&apos;ll help you capture decisions, document context, and record rationale for your knowledge graph.
              </p>
            </div>
          </div>
        ) : (
          messages.map((message, index) => (
            <MessageBubble
              key={message.id}
              message={message}
              isNew={index === messages.length - 1}
            />
          ))
        )}
        {isLoading && <TypingIndicator />}
      </ScrollArea>

      {/* Entity suggestions */}
      {suggestedEntities && suggestedEntities.length > 0 && (
        <div className="px-6 py-3 border-t border-white/[0.06] bg-gradient-to-r from-violet-500/5 to-fuchsia-500/5">
          <p className="text-xs text-slate-400 mb-2 flex items-center gap-1.5">
            <Sparkles className="h-3 w-3 text-violet-400" />
            Extracted entities:
          </p>
          <div className="flex flex-wrap gap-2">
            {suggestedEntities.map((entity) => (
              <Badge
                key={entity.id}
                variant="outline"
                className="cursor-pointer bg-violet-500/10 border-violet-500/30 text-violet-300 hover:bg-violet-500/20 hover:scale-105 hover:shadow-glow-violet/20 transition-all"
                onClick={() => onLinkEntity?.(entity)}
              >
                {entity.name}
                <span className="ml-1.5 text-violet-400/60 text-[10px]">({entity.type})</span>
              </Badge>
            ))}
          </div>
        </div>
      )}

      {/* Input */}
      <form onSubmit={handleSubmit} className="p-4 border-t border-white/[0.06] bg-slate-950/80 backdrop-blur-xl">
        <div className="flex gap-3">
          <Input
            ref={inputRef}
            value={input}
            onChange={(e) => setInput(e.target.value)}
            placeholder="Type your message..."
            disabled={isLoading}
            aria-label="Type your message"
            className="flex-1 bg-white/[0.03] border-white/[0.1] text-slate-200 placeholder:text-slate-500 focus:border-violet-500/50 focus:ring-2 focus:ring-violet-500/20 rounded-xl"
          />
          <Button
            type="submit"
            disabled={!input.trim() || isLoading}
            variant="gradient"
            aria-label={isLoading ? "Sending message" : "Send message"}
          >
            {isLoading ? (
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
