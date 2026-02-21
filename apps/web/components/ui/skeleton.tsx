import { cn } from "@/lib/utils"

function Skeleton({
  className,
  ...props
}: React.HTMLAttributes<HTMLDivElement>) {
  return (
    <div
      className={cn(
        "relative rounded-md bg-gradient-to-r from-slate-800/60 via-slate-700/40 to-slate-800/60 overflow-hidden",
        "before:absolute before:inset-0 before:bg-gradient-to-r before:from-transparent before:via-white/5 before:to-transparent",
        "before:animate-[shimmer_2s_infinite] before:-translate-x-full",
        className
      )}
      {...props}
    />
  )
}

/**
 * Skeleton for decision card lists
 */
function DecisionCardSkeleton({ className }: { className?: string }) {
  return (
    <div
      className={cn(
        "relative rounded-xl border border-white/[0.08] bg-white/[0.02] p-5 space-y-4 overflow-hidden",
        "before:absolute before:inset-0 before:bg-gradient-to-br before:from-violet-500/[0.02] before:to-transparent",
        className
      )}
    >
      {/* Title and badge row */}
      <div className="flex items-start justify-between gap-3">
        <Skeleton className="h-5 w-3/4 rounded-lg" />
        <Skeleton className="h-6 w-14 shrink-0 rounded-full" />
      </div>
      {/* Description */}
      <div className="space-y-2">
        <Skeleton className="h-4 w-full rounded" />
        <Skeleton className="h-4 w-4/5 rounded" />
      </div>
      {/* Entity badges */}
      <div className="flex gap-2 pt-1">
        <Skeleton className="h-7 w-20 rounded-full" />
        <Skeleton className="h-7 w-24 rounded-full" />
        <Skeleton className="h-7 w-16 rounded-full" />
      </div>
    </div>
  )
}

/**
 * Skeleton for stat cards on dashboard
 */
function StatCardSkeleton({ className }: { className?: string }) {
  return (
    <div
      className={cn(
        "relative rounded-xl border border-white/[0.08] bg-white/[0.02] p-6 space-y-4 overflow-hidden",
        "before:absolute before:inset-0 before:bg-gradient-to-br before:from-violet-500/[0.03] before:to-transparent",
        className
      )}
    >
      <div className="flex items-center gap-3">
        <Skeleton className="h-10 w-10 rounded-xl" />
        <Skeleton className="h-4 w-28 rounded" />
      </div>
      <Skeleton className="h-10 w-20 rounded-lg" />
      <Skeleton className="h-3 w-36 rounded" />
    </div>
  )
}

/**
 * Skeleton for graph loading state
 */
function GraphSkeleton({ className }: { className?: string }) {
  return (
    <div
      className={cn(
        "h-full w-full flex items-center justify-center bg-gradient-to-b from-slate-900/30 to-slate-900/60",
        className
      )}
    >
      <div className="text-center space-y-6">
        {/* Animated graph representation with pulsing nodes */}
        <div className="relative mx-auto h-40 w-56">
          {/* Central node with glow */}
          <div className="absolute top-1/2 left-1/2 -translate-x-1/2 -translate-y-1/2">
            <div className="absolute inset-0 w-16 h-16 bg-violet-500/20 rounded-xl blur-xl animate-pulse" />
            <Skeleton className="relative h-12 w-28 rounded-xl" />
          </div>

          {/* Orbiting nodes */}
          <div className="absolute top-2 left-1/2 -translate-x-1/2 animate-pulse" style={{ animationDelay: "0.2s" }}>
            <Skeleton className="h-8 w-20 rounded-full" />
          </div>
          <div className="absolute top-1/2 left-0 -translate-y-1/2 animate-pulse" style={{ animationDelay: "0.4s" }}>
            <Skeleton className="h-7 w-16 rounded-full" />
          </div>
          <div className="absolute top-1/2 right-0 -translate-y-1/2 animate-pulse" style={{ animationDelay: "0.6s" }}>
            <Skeleton className="h-7 w-18 rounded-full" />
          </div>
          <div className="absolute bottom-2 left-1/4 animate-pulse" style={{ animationDelay: "0.8s" }}>
            <Skeleton className="h-6 w-14 rounded-full" />
          </div>
          <div className="absolute bottom-4 right-1/4 animate-pulse" style={{ animationDelay: "1s" }}>
            <Skeleton className="h-6 w-16 rounded-full" />
          </div>

          {/* Animated connection lines */}
          <svg className="absolute inset-0 w-full h-full" style={{ zIndex: -1 }}>
            <defs>
              <linearGradient id="lineGrad" x1="0%" y1="0%" x2="100%" y2="0%">
                <stop offset="0%" stopColor="rgba(139, 92, 246, 0)" />
                <stop offset="50%" stopColor="rgba(139, 92, 246, 0.3)" />
                <stop offset="100%" stopColor="rgba(139, 92, 246, 0)" />
              </linearGradient>
            </defs>
            <line x1="50%" y1="15%" x2="50%" y2="40%" stroke="url(#lineGrad)" strokeWidth="1" className="animate-pulse" />
            <line x1="15%" y1="50%" x2="38%" y2="50%" stroke="url(#lineGrad)" strokeWidth="1" className="animate-pulse" style={{ animationDelay: "0.3s" }} />
            <line x1="62%" y1="50%" x2="85%" y2="50%" stroke="url(#lineGrad)" strokeWidth="1" className="animate-pulse" style={{ animationDelay: "0.5s" }} />
            <line x1="30%" y1="60%" x2="40%" y2="75%" stroke="url(#lineGrad)" strokeWidth="1" className="animate-pulse" style={{ animationDelay: "0.7s" }} />
            <line x1="60%" y1="60%" x2="70%" y2="70%" stroke="url(#lineGrad)" strokeWidth="1" className="animate-pulse" style={{ animationDelay: "0.9s" }} />
          </svg>
        </div>

        {/* Loading text with animated dots */}
        <div className="flex items-center justify-center gap-2">
          <div className="w-5 h-5 border-2 border-violet-500/30 border-t-violet-500 rounded-full animate-spin" />
          <span className="text-sm text-slate-400">Loading knowledge graph</span>
        </div>
      </div>
    </div>
  )
}

/**
 * List of skeleton cards
 */
function DecisionListSkeleton({ count = 5 }: { count?: number }) {
  return (
    <div className="space-y-4" role="status" aria-label="Loading decisions">
      {Array.from({ length: count }).map((_, i) => (
        <DecisionCardSkeleton key={i} />
      ))}
      <span className="sr-only">Loading decision list...</span>
    </div>
  )
}

export {
  Skeleton,
  DecisionCardSkeleton,
  StatCardSkeleton,
  GraphSkeleton,
  DecisionListSkeleton,
}
