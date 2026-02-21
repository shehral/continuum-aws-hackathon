"use client"

import * as React from "react"
import { AlertCircle, RefreshCw, Home, Bug } from "lucide-react"
import { Button } from "@/components/ui/button"
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card"
import Link from "next/link"

export interface ErrorStateProps {
  title?: string
  message?: string
  error?: Error | null
  retry?: () => void
  showHomeLink?: boolean
  className?: string
}

/**
 * Reusable error state component for failed data fetching.
 * Provides user-friendly error display with retry option.
 */
export function ErrorState({
  title = "Something went wrong",
  message = "We encountered an error loading this content.",
  error,
  retry,
  showHomeLink = false,
  className,
}: ErrorStateProps) {
  const [showDetails, setShowDetails] = React.useState(false)

  return (
    <div
      className={`flex flex-col items-center justify-center py-12 px-4 ${className}`}
      role="alert"
      aria-live="assertive"
    >
      <div className="mx-auto mb-6 h-16 w-16 rounded-2xl bg-red-500/10 flex items-center justify-center">
        <AlertCircle className="h-8 w-8 text-red-400" aria-hidden="true" />
      </div>
      
      <h3 className="text-lg font-semibold text-slate-200 mb-2">{title}</h3>
      <p className="text-slate-400 text-center max-w-md mb-6">{message}</p>
      
      <div className="flex gap-3">
        {retry && (
          <Button
            onClick={retry}
            className="bg-gradient-to-r from-cyan-500 to-teal-400 text-slate-900 hover:shadow-[0_0_20px_rgba(34,211,238,0.3)]"
          >
            <RefreshCw className="h-4 w-4 mr-2" aria-hidden="true" />
            Try Again
          </Button>
        )}
        {showHomeLink && (
          <Button
            variant="outline"
            asChild
            className="border-white/10 text-slate-300 hover:bg-white/[0.08]"
          >
            <Link href="/dashboard">
              <Home className="h-4 w-4 mr-2" aria-hidden="true" />
              Go Home
            </Link>
          </Button>
        )}
      </div>

      {/* Error details for debugging */}
      {error && (
        <div className="mt-6 w-full max-w-md">
          <button
            onClick={() => setShowDetails(!showDetails)}
            className="text-xs text-slate-500 hover:text-slate-400 flex items-center gap-1 mx-auto"
          >
            <Bug className="h-3 w-3" aria-hidden="true" />
            {showDetails ? "Hide" : "Show"} technical details
          </button>
          {showDetails && (
            <Card className="mt-2 bg-slate-800/50 border-slate-700">
              <CardHeader className="py-2 px-3">
                <CardTitle className="text-xs text-slate-400">Error Details</CardTitle>
              </CardHeader>
              <CardContent className="py-2 px-3">
                <pre className="text-xs text-red-400 overflow-auto max-h-32 whitespace-pre-wrap">
                  {error.message}
                  {error.stack && `\n\n${error.stack}`}
                </pre>
              </CardContent>
            </Card>
          )}
        </div>
      )}
    </div>
  )
}

/**
 * Full page error state for use in error boundaries
 */
export function FullPageError({
  error,
  reset,
}: {
  error: Error & { digest?: string }
  reset: () => void
}) {
  return (
    <div className="min-h-screen flex items-center justify-center bg-slate-950 p-4">
      <div className="w-full max-w-md">
        <ErrorState
          title="Application Error"
          message="An unexpected error occurred. Our team has been notified."
          error={error}
          retry={reset}
          showHomeLink
        />
        {error.digest && (
          <p className="text-center text-xs text-slate-600 mt-4">
            Error ID: {error.digest}
          </p>
        )}
      </div>
    </div>
  )
}

/**
 * Empty state component for when there's no data
 */
export interface EmptyStateProps {
  icon?: React.ReactNode
  title: string
  description?: string
  action?: {
    label: string
    href?: string
    onClick?: () => void
  }
  className?: string
}

export function EmptyState({
  icon,
  title,
  description,
  action,
  className,
}: EmptyStateProps) {
  return (
    <div className={`text-center py-12 px-4 ${className}`}>
      {icon && (
        <div className="mx-auto mb-4 h-16 w-16 rounded-2xl bg-cyan-500/10 flex items-center justify-center">
          {icon}
        </div>
      )}
      <h3 className="text-lg font-semibold text-slate-200 mb-2">{title}</h3>
      {description && (
        <p className="text-slate-400 text-center max-w-md mx-auto mb-6">
          {description}
        </p>
      )}
      {action && (
        action.href ? (
          <Button
            asChild
            className="bg-gradient-to-r from-cyan-500 to-teal-400 text-slate-900 hover:shadow-[0_0_20px_rgba(34,211,238,0.3)]"
          >
            <Link href={action.href}>{action.label}</Link>
          </Button>
        ) : action.onClick ? (
          <Button
            onClick={action.onClick}
            className="bg-gradient-to-r from-cyan-500 to-teal-400 text-slate-900 hover:shadow-[0_0_20px_rgba(34,211,238,0.3)]"
          >
            {action.label}
          </Button>
        ) : null
      )}
    </div>
  )
}
