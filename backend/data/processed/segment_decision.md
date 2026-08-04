# Fase 6 — Descubrimiento de segmento con edge real: resultado

**Pregunta:** dado que el modelo no tiene edge en agregado contra el mercado
(ROI -11.76%, ver `backtest_odds.py`), ¿hay algún segmento específico
(superficie, nivel de torneo, ronda, brecha de ranking/Elo, favorito vs.
underdog, o book) donde sí lo tenga?

**Respuesta corta: no.** Sobre ATP main tour singles, cruzando 2022-2024
contra tres books (`Avg`, `Pinnacle`, `Bet365`), **ningún segmento muestra
un intervalo de confianza de ROI positivo tanto en el período de discovery
(2022-2023) como en el de confirmación/holdout (2024)**. Ver metodología y
cómo reproducir esto en `backend/scripts/segment_backtest.py`.

## Metodología

1. Split temporal fijo: **discovery = 2022-2023**, **confirmation = 2024**
   (el holdout nunca se usó para elegir segmentos).
2. Se descartaron segmentos con menos de 150 apuestas en discovery (con
   menos muestra el CI es inservible).
3. Se rankeó por el **límite inferior del CI bootstrap del ROI** (no por el
   ROI puntual), sobre 8 dimensiones (`surface`, `Series`, `Court`, `Round`,
   `rank_gap_bucket`, `odds_bucket`, `elo_diff_bucket`, `side`
   favorito/underdog) × 3 books = 69 combinaciones evaluadas en total.
4. Los segmentos que pasaron el filtro de muestra se reevaluaron tal cual en
   el holdout de 2024.

## Resultado

De las 69 combinaciones evaluadas: **0 tuvieron CI de ROI completamente
positivo en discovery, y 0 lo tuvieron en ambos períodos a la vez.**

Los candidatos menos malos (más cerca de romper parejo, sin llegar a
positivo con confianza) fueron consistentes en ambos períodos:

| Segmento | Book | ROI discovery (CI) | ROI confirmation (CI) |
|---|---|---|---|
| Cuota del favorito 1.5-2.0 | Pinnacle | -1.6% (-6.5%, +3.3%) | -4.3% (-10.5%, +1.5%) |
| Apostar al favorito | Pinnacle | -3.6% (-7.5%, +0.1%) | -3.3% (-8.2%, +2.0%) |
| Apostar al favorito | Bet365 | -5.1% (-9.3%, -1.1%) | -1.8% (-7.2%, +3.9%) |

Ninguno cruza a positivo con confianza en los dos períodos — son
"casi parejo", no "edge confirmado". Cualquiera de los tres podría
explorarse más (más años de datos, sizing más conservador) pero **no hay
base hoy para apostar dinero real en ellos**.

### Ejemplo de por qué el split discovery/confirmation importa

`rank_gap_bucket = "<10"` (rivales con ranking muy parecido) en Bet365 y
Pinnacle dio **ROI +20% con CI positivo (+0.3% a +39.5%) en el holdout de
2024** — si solo se hubiera mirado 2024, esto habría parecido el mejor
hallazgo de todos. Pero en discovery (2022-2023) el mismo segmento dio
**-6% con CI (-16.4%, +3.9%)**, signo contrario. Es el patrón clásico de
ruido/regresión a la media que aparece cuando se prueban ~70 combinaciones:
por azar, algunas van a verse bien en un período nada más. Por eso la regla
de esta fase es exigir ambos períodos, no solo el más reciente.

## Conclusión / go-no-go

**No-go** para apostar dinero real en ATP main tour singles (match-winner),
en ningún segmento probado, contra ningún book de los tres evaluados. El
modelo, tal como está, no tiene un edge explotable — ni en agregado ni en
ningún corte razonable de agregado.

## Próximos pasos posibles (no ejecutados en esta fase)

- **Mercados con menos información pública**: Challengers/ITF. `tennis-data.co.uk`
  no los publica; requeriría buscar y validar otra fuente de cuotas antes de
  poder intentar esto.
- **Blend modelo+mercado**: en vez de apostar cuando el modelo solo ve EV+
  contra la cuota, apostar cuando el modelo diverge de una mezcla
  modelo+probabilidad-implícita-de-mercado — reduce el ruido de que el
  modelo esté simplemente equivocado en vez de ver algo que el mercado no ve.
- **CLV en vivo**: siendo que `predictions_log.jsonl` (Fase 5) ya registra
  cada predicción servida, con suficiente historial en vivo se puede medir
  closing line value real hacia adelante, que es una señal más limpia que
  el ROI de una muestra histórica de tamaño fijo.

## Reproducir

```bash
python backend/scripts/segment_backtest.py --min-n 150 --bootstrap 2000
```

Salidas: `segment_discovery.csv` (todas las combinaciones que pasan el
filtro de muestra) y `segment_confirmation.csv` (esas mismas combinaciones
reevaluadas en 2024), ambas en este mismo directorio.
