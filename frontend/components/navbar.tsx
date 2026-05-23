"use client"

import { useState } from "react"
import { motion } from "framer-motion"
import { Activity, Menu, X } from "lucide-react"
import Link from "next/link"
import { Button } from "@/components/ui/button"

export function Navbar() {
  const [isMobileMenuOpen, setIsMobileMenuOpen] = useState(false)

  return (
    <motion.nav
      initial={{ y: -20, opacity: 0 }}
      animate={{ y: 0, opacity: 1 }}
      transition={{ duration: 0.5 }}
      className="fixed top-0 right-0 left-0 z-50 glass border-b border-border/50"
    >
      <div className="mx-auto max-w-7xl px-4 sm:px-6 lg:px-8">
        <div className="flex h-16 items-center justify-between">
          <Link href="/" className="flex items-center gap-3">
            <div className="flex h-10 w-10 items-center justify-center rounded-xl bg-gradient-to-br from-primary to-accent glow-green">
              <Activity className="h-5 w-5 text-primary-foreground" />
            </div>
            <div className="hidden sm:block">
              <span className="text-xl font-bold gradient-text">TennisAI</span>
              <span className="ml-2 hidden text-xs text-muted-foreground md:inline">
                Predicciones ATP
              </span>
            </div>
          </Link>

          <Button
            variant="ghost"
            size="icon"
            className="h-9 w-9 md:hidden"
            onClick={() => setIsMobileMenuOpen(!isMobileMenuOpen)}
            aria-label={isMobileMenuOpen ? "Cerrar menú" : "Abrir menú"}
            aria-expanded={isMobileMenuOpen}
          >
            {isMobileMenuOpen ? (
              <X className="h-5 w-5" />
            ) : (
              <Menu className="h-5 w-5" />
            )}
          </Button>
        </div>
      </div>

      {isMobileMenuOpen && (
        <motion.div
          initial={{ opacity: 0, height: 0 }}
          animate={{ opacity: 1, height: "auto" }}
          className="border-t border-border/50 glass md:hidden"
        >
          <div className="px-4 py-3">
            <Link
              href="/"
              className="block rounded-lg bg-secondary px-3 py-2 text-sm font-medium text-foreground"
              onClick={() => setIsMobileMenuOpen(false)}
            >
              Predicciones IA
            </Link>
          </div>
        </motion.div>
      )}
    </motion.nav>
  )
}
