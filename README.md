# Bot de Arbitraje de Funding Rate — Binance Futures

Sistema automatizado de trading algorítmico en Python que opera 24/7 sobre Binance Futures, aprovechando tasas de financiamiento (funding rates) elevadas en futuros perpetuos.

---

## Resultados

| Período | Capital operativo | Ganancia |
|---------|------------------|---------|
| 7 días (demo) | $100 → $500 USDT | +1.000 USDT |
| Actualmente | $100 USDT real | En producción |

---

## Estrategia

El bot cobra el funding rate abriendo posiciones SHORT cuando la tasa anualizada supera el umbral configurado. Opera en tres modos automáticos según las condiciones del mercado:

| Modo | Condición | Comportamiento |
|------|-----------|----------------|
| **Agresivo** | Funding > 500% anual | Entra directo, capital completo |
| **Moderado** | Funding 50–500% anual | Verifica RSI + EMA antes de entrar, 50% del capital |
| **Sin operación** | Funding < 50% anual | Espera sin operar |

---

## Características principales

- **Selección automática de símbolo** — escanea más de 300 pares de futuros perpetuos en tiempo real y elige el de mayor funding que pase todos los filtros
- **Filtros de entrada** — volumen mínimo 24hs, volatilidad máxima y umbral de funding configurable
- **Análisis técnico** (modo moderado) — RSI de 14 períodos + EMA de 20 períodos sobre velas de 1h
- **Stop loss nativo** — orden STOP_MARKET colocada directamente en Binance al abrir cada posición
- **Rotación automática** — cierra y rota a mejor oportunidad si aparece una con funding 50% superior
- **Interés compuesto automático** — capital operativo sube de $100 a $500 USDT en incrementos de $50 por cada umbral de ganancia alcanzado
- **Estado persistente** — `estado.json` preserva balance inicial, capital y umbral entre reinicios
- **Resumen diario** — registro automático de ganancia del día a medianoche
- **Panel en tiempo real** — hoja "Panel" en Google Sheets actualizada cada 30 minutos con estado actual

---

## Control por Telegram

El bot acepta comandos en tiempo real desde Telegram (solo responde al operador autorizado por chat ID):

| Comando | Función |
|---------|---------|
| `/estado` | Símbolo activo, funding, modo, P&L, balance, capital, umbral |
| `/ganancia` | Balance inicial vs actual y ganancia total acumulada |
| `/pausa` | Detiene nuevas operaciones (posición actual sigue abierta) |
| `/reanudar` | Reactiva el bot |
| `/cerrar` | Cierra la posición actual manualmente |
| `/ayuda` | Lista de comandos disponibles |

---

## Stack técnico

- **Python 3** — lógica principal
- **Binance Futures API** — autenticación HMAC/SHA256, órdenes MARKET y STOP_MARKET
- **Google Sheets API** — registro de operaciones y panel en tiempo real (OAuth)
- **Telegram Bot API** — alertas automáticas y control remoto
- **Linux / Ubuntu 24.04** — deploy en VPS como servicio systemd con auto-reinicio
- **SSH / WinSCP** — administración remota

---

## Parámetros configurables

```python
UMBRAL_AGRESIVO   = 500    # % anual — umbral para modo agresivo
UMBRAL_MODERADO   = 50     # % anual — umbral mínimo para operar
CAPITAL_MINIMO    = 100    # USDT — capital inicial
CAPITAL_MAXIMO    = 500    # USDT — techo de capital operativo
UMBRAL_REINVERSION = 50    # USDT — incremento de capital por umbral
STOP_LOSS_PCT     = 5      # % — stop loss sobre precio de entrada
VOLUMEN_MINIMO    = 1000000  # USDT — volumen mínimo 24hs
MAX_VOLATILIDAD   = 10     # % — volatilidad máxima 24hs
RSI_MINIMO        = 55     # RSI mínimo para abrir en modo moderado
EMA_PERIODO       = 20     # Período de la EMA
```

---

## Estructura del proyecto

```
bot-arbitraje-binance/
├── bot.py              # Sistema principal
├── funding_rates.py    # Monitor de funding rates
├── config.py           # Claves API (no incluidas — usar variables de entorno)
└── README.md
```

---

## Configuración

1. Clonar el repositorio
2. Instalar dependencias: `pip install requests gspread google-auth`
3. Configurar `config.py` con las claves de Binance, Telegram y Google
4. Agregar credenciales de Google Sheets (`bot-arbitraje-492116-xxxxx.json`)
5. Ejecutar: `python3 bot.py`

Para deploy en VPS con systemd, configurar el servicio para auto-reinicio ante fallos.

---

## Aviso

Este proyecto es de uso educativo y experimental. El trading con derivados implica riesgo de pérdida de capital. Úsalo bajo tu propia responsabilidad.

---

## Autor

**Gonzalo Escobar** — Comercial técnico con base industrial y automatización con Python  
[LinkedIn](https://linkedin.com/in/gonzalo-escobar-168062216) · [GitHub](https://github.com/gonzopatineta)
