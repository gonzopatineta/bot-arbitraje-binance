[README.md](https://github.com/user-attachments/files/26763461/README.md)
# Binance Futures Funding Rate Arbitrage Bot

Automated algorithmic trading system in Python that runs 24/7 on a Linux VPS, capturing funding rate premiums on Binance Futures perpetual contracts.

---

## Results

| Period | Starting Capital | P&L |
|--------|-----------------|-----|
| 7 days (demo) | $100 → $500 USDT | +$1,000 USDT |
| Live trading | $100 USDT real | Active |

---

## Strategy

The bot opens SHORT positions when the annualized funding rate exceeds a configurable threshold. Since long traders pay the funding fee every 8 hours, the bot collects this premium passively. It operates in three automatic modes based on market conditions:

| Mode | Condition | Behavior |
|------|-----------|----------|
| **Aggressive** | Funding > 300% annual | Enters immediately, full capital, no technical filter |
| **Moderate** | Funding 50–300% annual | Verifies RSI + EMA before entry, uses 50% of capital |
| **No operation** | Funding < 50% annual | Waits for better conditions |

---

## Key Features

- **Real-time market scanning** — monitors 300+ perpetual futures pairs every cycle
- **Multi-filter entry logic** — minimum volume, maximum volatility, funding rate threshold
- **Technical analysis** (moderate mode) — RSI (14 periods) + EMA (20 periods) on 1h candles
- **Native stop loss** — STOP_MARKET order placed directly on Binance servers at position open
- **Automatic compounding** — operating capital scales from $100 to $500 USDT in $50 increments per profit threshold reached
- **Persistent state** — `estado.json` with atomic write and `.bak` backup survives VPS reboots
- **Position verification on restart** — queries Binance API to confirm open positions before resuming
- **N+1 fix** — single API request fetches all 24h ticker data instead of one per symbol
- **stepSize cache** — `exchangeInfo` loaded once at startup (712 symbols), no redundant heavy requests
- **Daily summary** — automatic P&L report at midnight logged to Google Sheets and Telegram

---

## Remote Control via Telegram

Full bot control from your phone. Commands are processed in a dedicated thread — never blocks the trading loop.

| Command | Description |
|---------|-------------|
| `/estado` | Current position, funding rate, mode, P&L, balance, capital, next compound threshold |
| `/ganancia` | Total accumulated gain vs initial balance |
| `/pausa` | Pause new entries (current position stays open) |
| `/reanudar` | Resume normal operation |
| `/cerrar` | Manually close current position |
| `/ayuda` | List all available commands |

Only responds to the authorized owner chat ID — no unauthorized access possible.

---

## Tech Stack

| Layer | Technology |
|-------|-----------|
| Language | Python 3 |
| Exchange API | Binance Futures REST API (HMAC/SHA256 auth) |
| Order types | MARKET, STOP_MARKET |
| Notifications | Telegram Bot API |
| Data logging | Google Sheets API (OAuth2) |
| Infrastructure | Ubuntu 24.04 VPS, systemd service, auto-restart |
| Remote access | SSH (PuTTY), SFTP (WinSCP) |
| Concurrency | Python threading (Telegram worker thread) |
| Precision | Python Decimal for order quantity calculation |

---

## Configuration

Key parameters in `bot.py`:

```python
UMBRAL_AGRESIVO   = 300    # % annual — aggressive mode threshold
UMBRAL_MODERADO   = 50     # % annual — minimum threshold to operate
RSI_MINIMO        = 40     # RSI minimum for moderate mode entry
EMA_PERIODO       = 20     # EMA period for trend filter
CAPITAL_MINIMO    = 100    # USDT — starting capital
CAPITAL_MAXIMO    = 500    # USDT — maximum capital cap
UMBRAL_REINVERSION = 50   # USDT — profit threshold per compounding step
STOP_LOSS_PCT     = 5      # % — stop loss on entry price
VOLUMEN_MINIMO    = 1000000  # USDT — minimum 24h volume filter
MAX_VOLATILIDAD   = 10     # % — maximum 24h volatility filter
```

---

## Project Structure

```
bot-arbitraje-binance/
├── bot.py              # Main system — strategy, execution, monitoring
├── funding_rates.py    # Funding rate monitor
├── config.py           # API credentials (use environment variables in production)
└── README.md
```

---

## Setup

1. Clone the repository
2. Install dependencies: `pip install requests gspread google-auth`
3. Configure `config.py` with your Binance API keys, Telegram token and Google credentials
4. Run: `python3 bot.py`

For production deployment on Linux VPS with systemd auto-restart, configure the service file accordingly.

---

## Architecture Notes

This project demonstrates several production-grade patterns:

- **Event-driven alerts** — Telegram notifications on every significant event (position open/close, stop loss, compounding, daily summary)
- **Fault-tolerant persistence** — atomic file writes with backup prevent state corruption on unexpected shutdowns
- **API efficiency** — batch requests and in-memory caching reduce Binance rate limit consumption
- **Risk management** — native exchange-side stop loss executes even if the script goes offline

---

## Disclaimer

This project is for educational and experimental purposes. Trading derivatives involves risk of capital loss. Use at your own risk.

---

## Author

**Gonzalo Escobar** — Technical sales professional with industrial background, Python automation and API integration  
[LinkedIn](https://linkedin.com/in/gonzalo-escobar-168062216) · [GitHub](https://github.com/gonzopatineta)
