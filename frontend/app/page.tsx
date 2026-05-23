'use client'

import { useState } from 'react'
import { AppShell } from '@/components/app-shell'
import { PredictionForm } from '@/components/prediction-form'
import { PredictionResult } from '@/components/prediction-result'
import type { PredictionResponse } from '@/lib/types'

export default function HomePage() {
  const [result, setResult] = useState<PredictionResponse | null>(null)

  return (
    <AppShell>
      <header className="mb-8">
        <h1 className="text-3xl font-bold tracking-tight">
          <span className="gradient-text">Predicciones</span> TennisAI
        </h1>
        <p className="mt-2 text-muted-foreground">
          Calcula probabilidades de victoria entre dos jugadores ATP usando el
          modelo de machine learning.
        </p>
      </header>

      <div className="space-y-8">
        <PredictionForm onResult={setResult} />
        {result && <PredictionResult result={result} />}
      </div>
    </AppShell>
  )
}
