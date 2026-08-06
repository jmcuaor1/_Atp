'use client'

import { useEffect, useState } from 'react'
import { motion } from 'framer-motion'
import { AlertTriangle, RefreshCw, Trophy } from 'lucide-react'
import { fetchTodayMatches } from '@/lib/api'
import type { TodayMatch, TodayMatchesResponse } from '@/lib/types'
import { cn } from '@/lib/utils'
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from '@/components/ui/card'
import { Button } from '@/components/ui/button'

function formatPercent(value: number) {
  return `${(value * 100).toFixed(1)}%`
}

function formatDateTime(iso: string | null) {
  if (!iso) return 'Sin horario confirmado'
  return new Date(iso).toLocaleString('es-ES', {
    weekday: 'short',
    day: '2-digit',
    month: 'short',
    hour: '2-digit',
    minute: '2-digit',
  })
}

function formatCutoff(iso: string | null) {
  if (!iso) return null
  return new Date(iso).toLocaleDateString('es-ES', {
    year: 'numeric',
    month: 'long',
    day: 'numeric',
  })
}

export function TodayMatches() {
  const [data, setData] = useState<TodayMatchesResponse | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)

  async function load(refresh = false) {
    setLoading(true)
    setError(null)
    try {
      setData(await fetchTodayMatches(refresh))
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Error desconocido')
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => {
    load()
  }, [])

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between gap-3">
        <div>
          <h1 className="text-3xl font-bold tracking-tight">
            <span className="gradient-text">Partidos ATP</span> de hoy
          </h1>
          <p className="mt-2 text-muted-foreground">
            Torneos ATP reales activos ahora mismo, con la predicción del modelo para cada uno.
          </p>
        </div>
        <Button
          variant="outline"
          size="icon"
          onClick={() => load(true)}
          disabled={loading}
          aria-label="Actualizar"
        >
          <RefreshCw className={cn('h-4 w-4', loading && 'animate-spin')} />
        </Button>
      </div>

      {data?.model_data_cutoff && (
        <div className="flex items-start gap-2 rounded-xl border border-amber-500/30 bg-amber-500/10 p-3 text-sm text-amber-600 dark:text-amber-400">
          <AlertTriangle className="mt-0.5 h-4 w-4 shrink-0" />
          <p>
            El modelo se entrenó con partidos hasta el{' '}
            <strong>{formatCutoff(data.model_data_cutoff)}</strong>. El estado de forma
            reciente de cada jugador puede no reflejar semanas más actuales que esa fecha.
          </p>
        </div>
      )}

      {error && (
        <Card className="glass-card border-destructive/30">
          <CardContent className="pt-6 text-sm text-destructive">{error}</CardContent>
        </Card>
      )}

      {loading && !data && (
        <p className="text-sm text-muted-foreground">Cargando partidos...</p>
      )}

      {data && data.matches.length === 0 && (
        <Card className="glass-card">
          <CardContent className="pt-6 text-sm text-muted-foreground">
            Ningún torneo ATP elegible activo en este momento (la cobertura solo incluye
            Grand Slam, ATP 1000 y ATP 500 — no ATP 250). Es normal en varias semanas del
            calendario.
          </CardContent>
        </Card>
      )}

      <div className="space-y-4">
        {data?.matches.map((match) => (
          <MatchCard key={match.event_id} match={match} />
        ))}
      </div>

      {data && (
        <p className="text-center text-xs text-muted-foreground">
          {data.cached ? 'Datos en caché · ' : ''}
          Actualizado: {new Date(data.generated_at).toLocaleTimeString('es-ES')}
        </p>
      )}
    </div>
  )
}

function MatchCard({ match }: { match: TodayMatch }) {
  const p1Wins = match.resolved && (match.player1_win_probability ?? 0) >= (match.player2_win_probability ?? 0)

  return (
    <motion.div initial={{ opacity: 0, y: 12 }} animate={{ opacity: 1, y: 0 }} transition={{ duration: 0.3 }}>
      <Card className="glass-card">
        <CardHeader className="pb-2">
          <CardTitle className="flex items-center justify-between text-base">
            <span>{match.tournament}</span>
            <span className="text-xs font-normal text-muted-foreground">{match.surface}</span>
          </CardTitle>
          <CardDescription>{formatDateTime(match.commence_time)}</CardDescription>
        </CardHeader>
        <CardContent className="space-y-3">
          {match.resolved ? (
            <>
              <PlayerRow
                name={match.player1_name}
                probability={match.player1_win_probability!}
                isWinner={p1Wins}
              />
              <PlayerRow
                name={match.player2_name}
                probability={match.player2_win_probability!}
                isWinner={!p1Wins}
              />
            </>
          ) : (
            <div className="flex items-start gap-2 text-sm text-muted-foreground">
              <AlertTriangle className="mt-0.5 h-4 w-4 shrink-0" />
              <div>
                <p>
                  {match.player1_name} vs. {match.player2_name}
                </p>
                <p className="text-xs">{match.note ?? 'No se pudo generar predicción.'}</p>
              </div>
            </div>
          )}
        </CardContent>
      </Card>
    </motion.div>
  )
}

function PlayerRow({
  name,
  probability,
  isWinner,
}: {
  name: string
  probability: number
  isWinner: boolean
}) {
  const percent = probability * 100
  return (
    <div className="space-y-1.5">
      <div className="flex items-center justify-between text-sm">
        <span className={cn('font-medium', isWinner ? 'text-primary' : 'text-muted-foreground')}>
          {name}
          {isWinner && <Trophy className="ml-1.5 inline h-3.5 w-3.5 text-primary" />}
        </span>
        <span className="font-mono font-semibold">{formatPercent(probability)}</span>
      </div>
      <div className="h-1.5 overflow-hidden rounded-full bg-secondary">
        <motion.div
          initial={{ width: 0 }}
          animate={{ width: `${percent}%` }}
          transition={{ duration: 0.6, ease: 'easeOut' }}
          className={cn(
            'h-full rounded-full',
            isWinner ? 'bg-gradient-to-r from-primary to-accent' : 'bg-muted-foreground/40',
          )}
        />
      </div>
    </div>
  )
}
