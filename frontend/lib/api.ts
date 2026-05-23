import type {
  HealthResponse,
  PlayerSearchResult,
  PredictionRequest,
  PredictionResponse,
} from '@/lib/types'

export function getApiUrl(): string {
  return process.env.NEXT_PUBLIC_API_URL ?? 'http://localhost:8000'
}

async function parseError(response: Response): Promise<string> {
  let detail = 'Error en la solicitud'
  try {
    const body = await response.json()
    if (typeof body.detail === 'string') {
      detail = body.detail
    } else if (Array.isArray(body.detail)) {
      detail = body.detail
        .map((d: { msg?: string }) => d.msg ?? JSON.stringify(d))
        .join(', ')
    }
  } catch {
    // respuesta no JSON
  }
  return detail
}

export async function fetchHealth(): Promise<HealthResponse> {
  const response = await fetch(`${getApiUrl()}/health`)
  if (!response.ok) {
    throw new Error(await parseError(response))
  }
  return response.json()
}

export async function searchPlayers(
  query: string,
  limit = 10,
): Promise<PlayerSearchResult[]> {
  const params = new URLSearchParams({ q: query, limit: String(limit) })
  const response = await fetch(`${getApiUrl()}/players/search?${params}`)
  if (!response.ok) {
    throw new Error(await parseError(response))
  }
  return response.json()
}

export async function predictMatch(
  request: PredictionRequest,
): Promise<PredictionResponse> {
  const response = await fetch(`${getApiUrl()}/predict`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      best_of: 3,
      tourney_level: 'A',
      ...request,
    }),
  })

  if (!response.ok) {
    throw new Error(await parseError(response))
  }

  return response.json()
}
