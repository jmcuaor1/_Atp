'use client'

import { useState } from 'react'
import { cn } from '@/lib/utils'
import { Navbar } from '@/components/navbar'
import { Sidebar } from '@/components/sidebar'

export function AppShell({ children }: { children: React.ReactNode }) {
  const [sidebarCollapsed, setSidebarCollapsed] = useState(false)

  return (
    <div className="min-h-screen gradient-bg">
      <Navbar />
      <Sidebar
        collapsed={sidebarCollapsed}
        onCollapsedChange={setSidebarCollapsed}
      />
      <main
        className={cn(
          'min-h-screen pt-16 transition-[padding] duration-300',
          'pl-0',
          sidebarCollapsed ? 'md:pl-16' : 'md:pl-64',
        )}
      >
        <div className="mx-auto max-w-3xl px-4 py-8 sm:px-6 lg:px-8">
          {children}
        </div>
      </main>
    </div>
  )
}
