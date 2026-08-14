# Proceso de apuesta

Reglas fijas para pasar de una predicción del modelo a una apuesta real.
Estas reglas viven en texto porque son decisiones de disciplina, no de
código: el código en `app/services/staking.py` implementa el cálculo de
stake, pero las decisiones de *cuándo* apostar y *cómo revisar* el
proceso están acá.

## Recomendación

La apuesta es siempre `predicted_winner_name` — el jugador con mayor
`win_probability` según el modelo. Nunca se apuesta por un
`value_bet_player_name` distinto solo porque tenga edge positivo contra
la cuota de mercado: no se apuesta contra el modelo por valor de mercado.

## Umbral mínimo de probabilidad

No se apuesta si `win_probability` del favorito está por debajo de un
umbral mínimo, en el rango **55%–60%**. El valor exacto vive como la
constante `THRESHOLD` en `staking.py` (default `0.55`) — no se duplica
acá para no desincronizarse del código.

## Exclusiones

Cualquier partido con `low_sample_warning` en alguno de los dos
jugadores queda fuera de la estrategia, sin excepción y sin stake
reducido. No hay una versión "a mitad de tamaño" para estos casos: la
predicción del modelo sobre un jugador con poco historial no es lo
bastante confiable como para arriesgar banca en ninguna proporción.

## Sin apuestas en caliente

Prohibido apostar in-play o por impulso durante el partido. El stake se
fija antes de que arranque, usando solo datos pre-partido (probabilidad
del modelo, cuota disponible en ese momento, `low_sample_warning`). Una
vez que el partido empieza, la decisión ya está tomada.

## Cadencia de revisión

La revisión del proceso es **semanal**, y se basa en:

- Calibración (Brier score): si el modelo dice 70%, ¿gana ~70% de las
  veces?
- CLV promedio del período: ¿la cuota tomada fue mejor que la de cierre?

Nunca se revisa ni se ajusta la regla en base al resultado crudo
(ganado/perdido) de la semana — una racha de pérdidas con buena
calibración y buen CLV es varianza esperada, no una señal de que el
proceso esté roto. Cambiar reglas en base a resultados de corto plazo es
exactamente el error que separa a un apostador amateur de uno
profesional.

## Por qué

Los apostadores profesionales no se distinguen por acertar más picks
sueltos que el resto — a corto plazo, la varianza domina. Se distinguen
por gestión de riesgo (cuánto arriesgan y cuándo se excluyen) y por
proceso (revisar si el método es sólido, no si la última semana salió
bien). Esta capa existe para imponer esa disciplina alrededor de una
recomendación que ya es correcta en su lógica de fondo.
