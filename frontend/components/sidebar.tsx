"use client"

import { motion } from "framer-motion"
import { Brain, ChevronLeft, ChevronRight } from "lucide-react"
import { Button } from "@/components/ui/button"
import { cn } from "@/lib/utils"
import { ApiStatus } from "@/components/api-status"

interface SidebarProps {
  collapsed: boolean
  onCollapsedChange: (collapsed: boolean) => void
}

export function Sidebar({ collapsed, onCollapsedChange }: SidebarProps) {
  return (
    <motion.aside
      initial={{ x: -20, opacity: 0 }}
      animate={{ x: 0, opacity: 1 }}
      transition={{ duration: 0.5, delay: 0.1 }}
      className={cn(
        "fixed left-0 top-16 bottom-0 z-40 hidden glass-card border-r border-border/50 transition-all duration-300 md:block",
        collapsed ? "w-16" : "w-64",
      )}
    >
      <div className="flex h-full flex-col">
        <Button
          variant="ghost"
          size="icon"
          onClick={() => onCollapsedChange(!collapsed)}
          className="absolute -right-3 top-6 h-6 w-6 rounded-full border border-border/50 bg-secondary hover:bg-secondary/80"
          aria-label={collapsed ? "Expandir menú" : "Contraer menú"}
        >
          {collapsed ? (
            <ChevronRight className="h-3 w-3" />
          ) : (
            <ChevronLeft className="h-3 w-3" />
          )}
        </Button>

        <nav className="mt-6 flex-1 p-3">
          <a
            href="/"
            className={cn(
              "flex items-center gap-3 rounded-xl px-3 py-2.5 transition-colors",
              "bg-primary/10 text-primary",
            )}
          >
            <Brain className="h-5 w-5 shrink-0" />
            {!collapsed && (
              <span className="text-sm font-medium">Predicciones IA</span>
            )}
          </a>
        </nav>

        <ApiStatus collapsed={collapsed} />
      </div>
    </motion.aside>
  )
}
