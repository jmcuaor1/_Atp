export const SURFACES = ['Hard', 'Clay', 'Grass'] as const
export type Surface = (typeof SURFACES)[number]

export const TOURNEY_LEVELS = ['G', 'M', 'A', 'C', 'F', 'D'] as const
export type TourneyLevel = (typeof TOURNEY_LEVELS)[number]

export const BEST_OF = [3, 5] as const
export type BestOf = (typeof BEST_OF)[number]

export interface PlayerSearchResult {
  id: number
  name: string
  rank: number | null
  ioc: string | null
  elo: number | null
}

export interface PredictionResponse {
  player1_id: number
  player2_id: number
  player1_name: string
  player2_name: string
  player1_win_probability: number
  player2_win_probability: number
  predicted_winner_id: number
  predicted_winner_name: string
  surface: string
  message: string
}

export interface PredictionRequest {
  player1: { id: number }
  player2: { id: number }
  surface: Surface
  best_of?: BestOf
  tourney_level?: TourneyLevel
}

export interface HealthResponse {
  status: string
  model_loaded: boolean
  players_count: number
  feature_count: number
}
