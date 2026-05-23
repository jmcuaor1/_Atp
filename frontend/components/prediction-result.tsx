'use client'

import { motion } from 'framer-motion'
import { Trophy, TrendingUp } from 'lucide-react'
import type { PredictionResponse } from '@/lib/types'
import { cn } from '@/lib/utils'
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from '@/components/ui/card'

interface PredictionResultProps {
  result: PredictionResponse
}

function formatPercent(value: number) {
  return `${(value * 100).toFixed(1)}%`
}

export function PredictionResult({ result }: PredictionResultProps) {
  const p1Wins = result.predicted_winner_id === result.player1_id

  return (
    <motion.div
      initial={{ opacity: 0, y: 16 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.35 }}
      aria-live="polite"
    >
      <Card className="glass-card border-primary/30">
        <CardHeader>
          <CardTitle className="flex items-center gap-2">
            <Trophy className="h-5 w-5 text-primary" />
            Resultado del análisis
          </CardTitle>
          <CardDescription>{result.message}</CardDescription>
        </CardHeader>
        <CardContent className="space-y-6">
          <div className="rounded-xl border border-primary/30 bg-primary/10 p-4">
            <p className="text-sm text-muted-foreground">Ganador predicho</p>
            <p className="mt-1 text-2xl font-bold text-primary">
              {result.predicted_winner_name}
            </p>
            <p className="mt-1 text-xs text-muted-foreground">
              ID {result.predicted_winner_id} · {result.surface}
            </p>
          </div>

          <div className="space-y-4">
            <PlayerProbability
              label={result.player1_name}
              probability={result.player1_win_probability}
              isWinner={p1Wins}
            />
            <PlayerProbability
              label={result.player2_name}
              probability={result.player2_win_probability}
              isWinner={!p1Wins}
            />
          </div>
        </CardContent>
      </Card>
    </motion.div>
  )
}

function PlayerProbability({
  label,
  probability,
  isWinner,
}: {
  label: string
  probability: number
  isWinner: boolean
}) {
  const percent = probability * 100

  return (
    <div className="space-y-2">
      <div className="flex items-center justify-between text-sm">
        <span
          className={cn(
            'font-medium',
            isWinner ? 'text-primary' : 'text-muted-foreground',
          )}
        >
          {label}
          {isWinner && (
            <TrendingUp className="ml-1.5 inline h-3.5 w-3.5 text-primary" />
          )}
        </span>
        <span className="font-mono font-semibold">{formatPercent(probability)}</span>
      </div>
      <div className="h-2 overflow-hidden rounded-full bg-secondary">
        <motion.div
          initial={{ width: 0 }}
          animate={{ width: `${percent}%` }}
          transition={{ duration: 0.8, ease: 'easeOut' }}
          className={cn(
            'h-full rounded-full',
            isWinner
              ? 'bg-gradient-to-r from-primary to-accent'
              : 'bg-muted-foreground/40',
          )}
        />
      </div>
    </div>
  )
}
