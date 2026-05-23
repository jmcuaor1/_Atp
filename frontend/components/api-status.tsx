'use client'

import { useEffect, useState } from 'react'
import { fetchHealth, getApiUrl } from '@/lib/api'
import type { HealthResponse } from '@/lib/types'
import { cn } from '@/lib/utils'

export function ApiStatus({ collapsed }: { collapsed: boolean }) {
  const [health, setHealth] = useState<HealthResponse | null>(null)
  const [error, setError] = useState(false)

  useEffect(() => {
    let cancelled = false

    const load = async () => {
      try {
        const data = await fetchHealth()
        if (!cancelled) {
          setHealth(data)
          setError(false)
        }
      } catch {
        if (!cancelled) {
          setHealth(null)
          setError(true)
        }
      }
    }

    load()
    const interval = setInterval(load, 30_000)
    return () => {
      cancelled = true
      clearInterval(interval)
    }
  }, [])

  if (collapsed) return null

  const ready = health?.status === 'ok' && health.model_loaded

  return (
    <div className="border-t border-border/50 p-4">
      <div className="glass-card rounded-xl p-4 space-y-2">
        <div className="flex items-center gap-2">
          <span
            className={cn(
              'h-2 w-2 rounded-full',
              ready ? 'bg-primary animate-pulse-live' : error ? 'bg-destructive' : 'bg-warning',
            )}
          />
          <p className="text-xs font-semibold text-primary">Estado del API</p>
        </div>
        {health ? (
          <>
            <p className="text-xs text-muted-foreground">
              {health.players_count.toLocaleString()} jugadores ·{' '}
              {health.feature_count} features
            </p>
            <p className="break-all text-[10px] text-muted-foreground">{getApiUrl()}</p>
          </>
        ) : (
          <p className="text-xs text-destructive">
            {error ? 'API no disponible' : 'Comprobando…'}
          </p>
        )}
      </div>
    </div>
  )
}
