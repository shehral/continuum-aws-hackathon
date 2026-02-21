"use client"

import { useState } from "react"
import { Sidebar } from "./sidebar"

interface AppShellProps {
  children: React.ReactNode
}

export function AppShell({ children }: AppShellProps) {
  const [sidebarCollapsed, setSidebarCollapsed] = useState(false)

  return (
    <div className="flex h-screen overflow-hidden bg-background">
      {/* Nebula background effects - only visible in dark mode */}
      <div className="nebula-bg dark:block hidden" aria-hidden="true" />

      {/* Sidebar */}
      <Sidebar
        collapsed={sidebarCollapsed}
        onCollapsedChange={setSidebarCollapsed}
      />

      {/* Main content */}
      <main className="flex-1 overflow-auto relative z-10">
        <div className="page-transition">
          {children}
        </div>
      </main>
    </div>
  )
}
