'use client'

import { useState } from 'react'
import { Brain, Loader2 } from 'lucide-react'
import { toast } from 'sonner'
import { predictMatch } from '@/lib/api'
import type {
  BestOf,
  PlayerSearchResult,
  PredictionResponse,
  Surface,
  TourneyLevel,
} from '@/lib/types'
import { BEST_OF, SURFACES, TOURNEY_LEVELS } from '@/lib/types'
import { PlayerSearchField } from '@/components/player-search-field'
import { Button } from '@/components/ui/button'
import { Label } from '@/components/ui/label'
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select'
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from '@/components/ui/card'

const TOURNEY_LABELS: Record<TourneyLevel, string> = {
  G: 'Grand Slam',
  M: 'Masters 1000',
  A: 'ATP',
  C: 'Challenger',
  F: 'Futures',
  D: 'Davis Cup',
}

interface PredictionFormProps {
  onResult: (result: PredictionResponse) => void
}

export function PredictionForm({ onResult }: PredictionFormProps) {
  const [p1Id, setP1Id] = useState('')
  const [p2Id, setP2Id] = useState('')
  const [p1Name, setP1Name] = useState('')
  const [p2Name, setP2Name] = useState('')
  const [surface, setSurface] = useState<Surface>('Hard')
  const [bestOf, setBestOf] = useState<BestOf>(3)
  const [tourneyLevel, setTourneyLevel] = useState<TourneyLevel>('A')
  const [loading, setLoading] = useState(false)

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault()

    const id1 = Number.parseInt(p1Id, 10)
    const id2 = Number.parseInt(p2Id, 10)

    if (!Number.isFinite(id1) || id1 <= 0) {
      toast.error('Selecciona o introduce un jugador 1 válido')
      return
    }
    if (!Number.isFinite(id2) || id2 <= 0) {
      toast.error('Selecciona o introduce un jugador 2 válido')
      return
    }
    if (id1 === id2) {
      toast.error('Los dos jugadores deben ser distintos')
      return
    }

    setLoading(true)
    try {
      const data = await predictMatch({
        player1: { id: id1 },
        player2: { id: id2 },
        surface,
        best_of: bestOf,
        tourney_level: tourneyLevel,
      })
      onResult(data)
      toast.success('Predicción generada')
    } catch (error) {
      const message =
        error instanceof Error
          ? error.message
          : 'No se pudo conectar con el servidor de IA'
      toast.error(message)
    } finally {
      setLoading(false)
    }
  }

  const selectPlayer1 = (player: PlayerSearchResult) => {
    setP1Name(player.name)
    setP1Id(String(player.id))
  }

  const selectPlayer2 = (player: PlayerSearchResult) => {
    setP2Name(player.name)
    setP2Id(String(player.id))
  }

  return (
    <Card className="glass-card border-border/50">
      <CardHeader>
        <CardTitle className="flex items-center gap-2">
          <Brain className="h-5 w-5 text-primary" />
          Nueva predicción
        </CardTitle>
        <CardDescription>
          Busca jugadores por nombre o introduce su ID ATP, superficie y formato
          del partido.
        </CardDescription>
      </CardHeader>
      <CardContent>
        <form onSubmit={handleSubmit} className="space-y-5">
          <div className="grid gap-5 sm:grid-cols-2">
            <PlayerSearchField
              id="player1-search"
              label="Jugador 1"
              playerId={p1Id}
              playerName={p1Name}
              onSelect={selectPlayer1}
              onIdChange={setP1Id}
              disabled={loading}
            />
            <PlayerSearchField
              id="player2-search"
              label="Jugador 2"
              playerId={p2Id}
              playerName={p2Name}
              onSelect={selectPlayer2}
              onIdChange={setP2Id}
              disabled={loading}
            />
          </div>

          <div className="grid gap-5 sm:grid-cols-3">
            <div className="space-y-2">
              <Label htmlFor="surface">Superficie</Label>
              <Select
                value={surface}
                onValueChange={(value) => setSurface(value as Surface)}
                disabled={loading}
              >
                <SelectTrigger id="surface" className="w-full">
                  <SelectValue placeholder="Superficie" />
                </SelectTrigger>
                <SelectContent>
                  {SURFACES.map((s) => (
                    <SelectItem key={s} value={s}>
                      {s === 'Hard'
                        ? 'Pista dura'
                        : s === 'Clay'
                          ? 'Tierra batida'
                          : 'Hierba'}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>

            <div className="space-y-2">
              <Label htmlFor="best-of">Formato</Label>
              <Select
                value={String(bestOf)}
                onValueChange={(v) => setBestOf(Number(v) as BestOf)}
                disabled={loading}
              >
                <SelectTrigger id="best-of" className="w-full">
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  {BEST_OF.map((n) => (
                    <SelectItem key={n} value={String(n)}>
                      Mejor de {n}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>

            <div className="space-y-2">
              <Label htmlFor="tourney-level">Nivel torneo</Label>
              <Select
                value={tourneyLevel}
                onValueChange={(v) => setTourneyLevel(v as TourneyLevel)}
                disabled={loading}
              >
                <SelectTrigger id="tourney-level" className="w-full">
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  {TOURNEY_LEVELS.map((level) => (
                    <SelectItem key={level} value={level}>
                      {TOURNEY_LABELS[level]}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>
          </div>

          <Button
            type="submit"
            className="w-full glow-green sm:w-auto"
            disabled={loading}
            aria-busy={loading}
          >
            {loading ? (
              <>
                <Loader2 className="mr-2 h-4 w-4 animate-spin" />
                Analizando…
              </>
            ) : (
              'Calcular probabilidades'
            )}
          </Button>
        </form>
      </CardContent>
    </Card>
  )
}
