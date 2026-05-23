'use client'

import { useEffect, useState } from 'react'
import { Search } from 'lucide-react'
import { searchPlayers } from '@/lib/api'
import type { PlayerSearchResult } from '@/lib/types'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { cn } from '@/lib/utils'

interface PlayerSearchFieldProps {
  id: string
  label: string
  playerId: string
  playerName: string
  onSelect: (player: PlayerSearchResult) => void
  onIdChange: (id: string) => void
  disabled?: boolean
}

export function PlayerSearchField({
  id,
  label,
  playerId,
  playerName,
  onSelect,
  onIdChange,
  disabled,
}: PlayerSearchFieldProps) {
  const [query, setQuery] = useState(playerName)
  const [results, setResults] = useState<PlayerSearchResult[]>([])
  const [open, setOpen] = useState(false)
  const [searching, setSearching] = useState(false)

  useEffect(() => {
    if (!query.trim() || query.length < 2) {
      setResults([])
      return
    }

    const timer = setTimeout(async () => {
      setSearching(true)
      try {
        const data = await searchPlayers(query, 8)
        setResults(data)
        setOpen(data.length > 0)
      } catch {
        setResults([])
      } finally {
        setSearching(false)
      }
    }, 300)

    return () => clearTimeout(timer)
  }, [query])

  return (
    <div className="relative space-y-2">
      <Label htmlFor={id}>{label}</Label>
      <div className="relative">
        <Search className="absolute left-2.5 top-1/2 h-4 w-4 -translate-y-1/2 text-muted-foreground" />
        <Input
          id={id}
          className="pl-9"
          placeholder="Buscar por nombre o ID…"
          value={query}
          onChange={(e) => {
            setQuery(e.target.value)
            onIdChange('')
          }}
          onFocus={() => results.length > 0 && setOpen(true)}
          disabled={disabled}
          autoComplete="off"
        />
      </div>
      {playerId && playerName && (
        <p className="text-xs text-muted-foreground">
          Seleccionado: <span className="text-foreground">{playerName}</span>{' '}
          <span className="font-mono">(ID {playerId})</span>
        </p>
      )}
      {open && results.length > 0 && (
        <ul
          className="absolute z-20 mt-1 max-h-48 w-full overflow-auto rounded-lg border border-border/50 bg-popover py-1 shadow-lg"
          role="listbox"
        >
          {results.map((player) => (
            <li key={player.id}>
              <button
                type="button"
                role="option"
                className={cn(
                  'flex w-full flex-col px-3 py-2 text-left text-sm hover:bg-secondary/80',
                )}
                onClick={() => {
                  onSelect(player)
                  setQuery(player.name)
                  onIdChange(String(player.id))
                  setOpen(false)
                }}
              >
                <span className="font-medium">{player.name}</span>
                <span className="text-xs text-muted-foreground">
                  ID {player.id}
                  {player.rank != null && ` · ATP #${player.rank}`}
                  {player.ioc && ` · ${player.ioc}`}
                </span>
              </button>
            </li>
          ))}
        </ul>
      )}
      {searching && (
        <p className="text-xs text-muted-foreground">Buscando…</p>
      )}
    </div>
  )
}
