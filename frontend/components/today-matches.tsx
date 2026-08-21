'use client'

import { useEffect, useState } from 'react'
import { motion } from 'framer-motion'
import { AlertTriangle, Gauge, RefreshCw, Trophy } from 'lucide-react'
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
  const hasValueBet = match.resolved && match.value_bet_player_name !== null

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
                odds={match.player1_odds}
                edge={match.player1_edge}
                matchesPlayed={match.player1_matches_played}
                lowSample={match.player1_low_sample}
              />
              <PlayerRow
                name={match.player2_name}
                probability={match.player2_win_probability!}
                isWinner={!p1Wins}
                odds={match.player2_odds}
                edge={match.player2_edge}
                matchesPlayed={match.player2_matches_played}
                lowSample={match.player2_low_sample}
              />
              {match.low_sample_warning && (
                <LowSampleWarning match={match} />
              )}
              {hasValueBet && (
                <div
                  className={cn(
                    'flex items-start gap-2 rounded-lg border p-2.5 text-xs',
                    match.suspicious_edge
                      ? 'border-amber-500/30 bg-amber-500/10 text-amber-600 dark:text-amber-400'
                      : 'border-emerald-500/30 bg-emerald-500/10 text-emerald-600 dark:text-emerald-400',
                  )}
                >
                  <span className="mt-0.5 shrink-0">{match.suspicious_edge ? '⚠️' : '💰'}</span>
                  <p>
                    Valor de apuesta: <strong>{match.value_bet_player_name}</strong> en {match.book}.
                    {match.suspicious_edge && (
                      <>
                        {' '}
                        Edge muy alto — antes de apostar, chequeá a mano si hay lesión, retiro o baja
                        reciente que el modelo no vio.
                      </>
                    )}
                  </p>
                </div>
              )}
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

function LowSampleWarning({ match }: { match: TodayMatch }) {
  const names = [
    match.player1_low_sample ? match.player1_name : null,
    match.player2_low_sample ? match.player2_name : null,
  ].filter((name): name is string => name !== null)
  const verb = names.length > 1 ? 'tienen' : 'tiene'

  return (
    <div className="flex items-start gap-2 rounded-lg border border-sky-500/30 bg-sky-500/10 p-2.5 text-xs text-sky-600 dark:text-sky-400">
      <Gauge className="mt-0.5 h-3.5 w-3.5 shrink-0" />
      <p>
        Predicción con menos respaldo: <strong>{names.join(' y ')}</strong> {verb} poco historial
        reciente en la base del modelo — la predicción es menos confiable que en un partido con ambos
        jugadores bien muestreados.
      </p>
    </div>
  )
}

function PlayerRow({
  name,
  probability,
  isWinner,
  odds,
  edge,
  matchesPlayed,
  lowSample,
}: {
  name: string
  probability: number
  isWinner: boolean
  odds?: number | null
  edge?: number | null
  matchesPlayed?: number | null
  lowSample?: boolean
}) {
  const percent = probability * 100
  return (
    <div className="space-y-1.5">
      <div className="flex items-center justify-between text-sm">
        <span className={cn('font-medium', isWinner ? 'text-primary' : 'text-muted-foreground')}>
          {name}
          {isWinner && <Trophy className="ml-1.5 inline h-3.5 w-3.5 text-primary" />}
          {lowSample && matchesPlayed != null && (
            <span
              className="ml-1.5 inline-flex items-center gap-0.5 text-[10px] font-normal text-sky-600 dark:text-sky-400"
              title="Pocos partidos recientes en la base del modelo"
            >
              <Gauge className="h-3 w-3" />
              {matchesPlayed}
            </span>
          )}
        </span>
        <span className="flex items-center gap-2">
          {odds != null && (
            <span className="font-mono text-xs text-muted-foreground">
              cuota {odds.toFixed(2)}
              {edge != null && edge > 0 && (
                <span className="ml-1 text-emerald-600 dark:text-emerald-400">+{(edge * 100).toFixed(1)}%</span>
              )}
            </span>
          )}
          <span className="font-mono font-semibold">{formatPercent(probability)}</span>
        </span>
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
