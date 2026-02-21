"use client"

import { useState, useEffect, Suspense } from "react"
import { signIn } from "next-auth/react"
import { useRouter, useSearchParams } from "next/navigation"
import { GitBranch, Mail, Lock, ArrowRight, Sparkles } from "lucide-react"

import { Button } from "@/components/ui/button"
import { Input } from "@/components/ui/input"
import { Label } from "@/components/ui/label"

function LoginForm() {
  const router = useRouter()
  const searchParams = useSearchParams()
  const callbackUrl = searchParams.get("callbackUrl") || "/dashboard"

  const [email, setEmail] = useState("")
  const [password, setPassword] = useState("")
  const [isLoading, setIsLoading] = useState(false)
  const [error, setError] = useState("")
  const [focusedField, setFocusedField] = useState<string | null>(null)

  // Prevent hydration mismatch for animated elements
  const [mounted, setMounted] = useState(false)
  useEffect(() => {
    setMounted(true)
  }, [])

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault()
    setIsLoading(true)
    setError("")

    try {
      const result = await signIn("credentials", {
        email,
        password,
        redirect: false,
        callbackUrl,
      })

      if (result?.error) {
        setError("Invalid email or password")
      } else if (result?.ok) {
        router.push(callbackUrl)
      }
    } catch {
      setError("An error occurred. Please try again.")
    } finally {
      setIsLoading(false)
    }
  }

  return (
    <div className="dark min-h-screen flex items-center justify-center relative overflow-hidden bg-[hsl(250,20%,6%)]">
      {/* Animated nebula background */}
      <div className="nebula-bg" aria-hidden="true" />

      {/* Floating orbs - only render after mount to prevent hydration mismatch */}
      {mounted && (
        <div className="absolute inset-0 overflow-hidden pointer-events-none" aria-hidden="true">
          <div className="absolute top-1/4 left-1/4 w-64 h-64 bg-violet-500/10 rounded-full blur-3xl animate-float" />
          <div className="absolute bottom-1/4 right-1/4 w-96 h-96 bg-fuchsia-500/8 rounded-full blur-3xl animate-float [animation-delay:-1.5s]" />
          <div className="absolute top-1/2 right-1/3 w-48 h-48 bg-rose-500/6 rounded-full blur-3xl animate-float [animation-delay:-3s]" />
        </div>
      )}

      {/* Subtle grid pattern */}
      <div
        className="absolute inset-0 opacity-[0.015] bg-[linear-gradient(rgba(139,92,246,0.5)_1px,transparent_1px),linear-gradient(90deg,rgba(139,92,246,0.5)_1px,transparent_1px)] bg-[size:60px_60px]"
        aria-hidden="true"
      />

      {/* Main content */}
      <div className="relative z-10 w-full max-w-md px-6 animate-in fade-in slide-in-from-bottom-8 duration-700">
        {/* Logo & Title */}
        <div className="text-center mb-8">
          <div className="inline-flex items-center justify-center mb-6 relative">
            {/* Glow ring */}
            <div className="absolute inset-0 w-20 h-20 rounded-2xl bg-gradient-to-br from-violet-500/30 to-fuchsia-500/20 blur-xl" />

            {/* Logo container */}
            <div className="relative w-16 h-16 rounded-2xl bg-gradient-to-br from-violet-500/20 to-fuchsia-500/10 border border-violet-500/30 flex items-center justify-center backdrop-blur-sm">
              <GitBranch className="w-8 h-8 text-violet-400" />

              {/* Animated sparkle */}
              <Sparkles className="absolute -top-1 -right-1 w-4 h-4 text-fuchsia-400 animate-pulse" />
            </div>
          </div>

          <h1 className="text-3xl font-bold tracking-tight mb-2">
            <span className="gradient-text">Continuum</span>
          </h1>
          <p className="text-slate-400 text-sm">
            Your knowledge graph awaits
          </p>
        </div>

        {/* Login card — explicit dark styling to avoid light-mode glass-card override */}
        <div className="relative p-8 bg-white/[0.03] backdrop-blur-2xl border border-white/[0.08] rounded-2xl shadow-[0_8px_32px_rgba(0,0,0,0.4)]">
          <form onSubmit={handleSubmit} className="space-y-5">
            {/* Email field */}
            <div className="space-y-2">
              <Label
                htmlFor="email"
                className={`text-sm font-medium transition-colors ${
                  focusedField === 'email' ? 'text-violet-300' : 'text-slate-300'
                }`}
              >
                Email
              </Label>
              <div className="relative">
                <div className={`absolute left-3 top-1/2 -translate-y-1/2 transition-colors ${
                  focusedField === 'email' ? 'text-violet-400' : 'text-slate-500'
                }`}>
                  <Mail className="w-4 h-4" />
                </div>
                <Input
                  id="email"
                  type="email"
                  placeholder="you@example.com"
                  value={email}
                  onChange={(e) => setEmail(e.target.value)}
                  onFocus={() => setFocusedField('email')}
                  onBlur={() => setFocusedField(null)}
                  required
                  disabled={isLoading}
                  className="pl-10 h-12 bg-white/[0.03] border-white/10 text-slate-100 placeholder:text-slate-500 focus:border-violet-500/50 focus:ring-2 focus:ring-violet-500/20 transition-all"
                />
              </div>
            </div>

            {/* Password field */}
            <div className="space-y-2">
              <Label
                htmlFor="password"
                className={`text-sm font-medium transition-colors ${
                  focusedField === 'password' ? 'text-violet-300' : 'text-slate-300'
                }`}
              >
                Password
              </Label>
              <div className="relative">
                <div className={`absolute left-3 top-1/2 -translate-y-1/2 transition-colors ${
                  focusedField === 'password' ? 'text-violet-400' : 'text-slate-500'
                }`}>
                  <Lock className="w-4 h-4" />
                </div>
                <Input
                  id="password"
                  type="password"
                  placeholder="Enter your password"
                  value={password}
                  onChange={(e) => setPassword(e.target.value)}
                  onFocus={() => setFocusedField('password')}
                  onBlur={() => setFocusedField(null)}
                  required
                  disabled={isLoading}
                  className="pl-10 h-12 bg-white/[0.03] border-white/10 text-slate-100 placeholder:text-slate-500 focus:border-violet-500/50 focus:ring-2 focus:ring-violet-500/20 transition-all"
                />
              </div>
            </div>

            {/* Error message */}
            {error && (
              <div className="p-3 rounded-xl bg-red-500/10 border border-red-500/20 animate-in fade-in slide-in-from-top-2 duration-300">
                <p className="text-sm text-red-400 text-center">{error}</p>
              </div>
            )}

            {/* Submit button */}
            <Button
              type="submit"
              disabled={isLoading}
              className="w-full h-12 btn-gradient text-base font-semibold group"
            >
              {isLoading ? (
                <div className="flex items-center gap-2">
                  <div className="w-5 h-5 border-2 border-white/30 border-t-white rounded-full animate-spin" />
                  <span>Signing in...</span>
                </div>
              ) : (
                <div className="flex items-center justify-center gap-2">
                  <span>Sign in</span>
                  <ArrowRight className="w-4 h-4 group-hover:translate-x-1 transition-transform" />
                </div>
              )}
            </Button>

            {/* Divider */}
            <div className="relative my-6">
              <div className="absolute inset-0 flex items-center">
                <div className="w-full border-t border-white/10" />
              </div>
              <div className="relative flex justify-center text-xs uppercase">
                <span className="px-2 bg-[hsl(252,20%,10%)] text-slate-500">or</span>
              </div>
            </div>

            {/* Sign up link */}
            <p className="text-center text-sm text-slate-400">
              Don&apos;t have an account?{" "}
              <a
                href="/register"
                className="text-violet-400 hover:text-violet-300 font-medium transition-colors hover:underline decoration-violet-400/50 underline-offset-4"
              >
                Create one
              </a>
            </p>
          </form>
        </div>

        {/* Footer text */}
        <p className="text-center text-xs text-slate-600 mt-6">
          Powered by your development decisions
        </p>
      </div>
    </div>
  )
}

export default function LoginPage() {
  return (
    <Suspense fallback={
      <div className="min-h-screen flex items-center justify-center bg-[hsl(250,20%,6%)]">
        <div className="nebula-bg" aria-hidden="true" />
        <div className="relative z-10 flex flex-col items-center gap-4">
          <div className="w-12 h-12 rounded-xl bg-gradient-to-br from-violet-500/20 to-fuchsia-500/10 border border-violet-500/30 flex items-center justify-center">
            <div className="w-6 h-6 border-2 border-violet-500/30 border-t-violet-500 rounded-full animate-spin" />
          </div>
          <span className="text-slate-400 text-sm">Loading...</span>
        </div>
      </div>
    }>
      <LoginForm />
    </Suspense>
  )
}
