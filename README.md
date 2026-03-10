# 🤖 Polymarket AI Scalper

Proof of concept — An autonomous trading bot for [Polymarket](https://polymarket.com) prediction markets, powered by Anthropic's Claude API.

The bot analyzes short-term prediction markets (resolving in minutes to hours), identifies mispricings using AI reasoning, and executes trades automatically via Polymarket's CLOB API.

![Python](https://img.shields.io/badge/python-3.10+-blue)
![License](https://img.shields.io/badge/license-MIT-green)

---

## ⚠️ Important Disclaimers

- **This bot trades with REAL money.** You can lose your entire balance.
- **No bot wins 100% of the time.** This is experimental software.
- **LLMs don't have insider information.** Claude analyzes publicly available data — it doesn't have a true quantitative edge over informed humans.
- **API costs can be significant.** See the [Cost Analysis](#-cost-analysis) section before running.
- **This is NOT financial advice.** Use at your own risk.

---

## 🏗 Architecture

```
┌─────────────────────────────────────────────────┐
│                   Main Loop                      │
│                                                  │
│   ┌──────────┐   ┌──────────┐   ┌───────────┐  │
│   │  Price    │   │  Claude   │   │  Order    │  │
│   │  Scanner  │──▶│  Brain    │──▶│  Executor │  │
│   │  (15s)    │   │  (30s)    │   │  (CLOB)   │  │
│   └──────────┘   └──────────┘   └───────────┘  │
│        │                              │          │
│        ▼                              ▼          │
│   ┌──────────┐              ┌───────────────┐   │
│   │  Signal   │              │  Exit System  │   │
│   │  Engine   │              │  TP/SL/Trail  │   │
│   └──────────┘              └───────────────┘   │
│                                                  │
│   ┌──────────────────────────────────────────┐  │
│   │          Circuit Breaker (Safety)         │  │
│   └──────────────────────────────────────────┘  │
└─────────────────────────────────────────────────┘
```

### How it works

1. **Price Scanner** — Fetches active markets from Polymarket's Gamma API every 15 seconds. Filters only short-term markets (≤72h to resolution). Computes momentum, volatility, and volume signals.

2. **Claude Brain** — Every 30 seconds, sends market data + portfolio state + trade history to Claude. The model identifies mispricings and returns a structured JSON decision (buy/hold).

3. **Signal Validation** — The bot validates Claude's decision against minimum edge, confidence, position limits, and risk thresholds before executing.

4. **Order Executor** — Sends orders to Polymarket via the CLOB API. Tries Fill-or-Kill (instant) first, falls back to Good-til-Cancelled limit orders.

5. **Exit System** — Checks every 15 seconds for take-profit, stop-loss, trailing stop, time stop, and breakeven conditions.

6. **Circuit Breaker** — Pauses trading if losses exceed thresholds (drawdown, losing streak, total P&L).

---

## 📦 Installation

```bash
# Clone the repo
git clone https://github.com/YOUR_USERNAME/polymarket-ai-scalper.git
cd polymarket-ai-scalper

# Create virtual environment (recommended)
python -m venv venv
source venv/bin/activate  # Linux/Mac
# venv\Scripts\activate   # Windows

# Install dependencies
pip install -r requirements.txt

# Configure environment variables
cp .env.example .env
# Edit .env with your actual keys
```

---

## ⚙️ Configuration

### Required: `.env` file

Copy `.env.example` to `.env` and fill in your credentials:

```bash
cp .env.example .env
```

| Variable | Description | Where to get it |
|---|---|---|
| `ANTHROPIC_KEY` | Anthropic API key | [console.anthropic.com](https://console.anthropic.com) |
| `POLY_PRIVATE_KEY` | Polymarket private key | Polymarket → Settings → Export Private Key |
| `POLY_FUNDER` | Your Polymarket wallet address | Polymarket → Profile |
| `INITIAL_BALANCE` | Starting balance in USDC | Your Polymarket balance |

### Optional: `config.py`

All trading parameters are in `config.py` with detailed comments. Key settings:

| Parameter | Default | Description |
|---|---|---|
| `BRAIN_SECONDS` | 30 | How often Claude analyzes markets |
| `SCAN_SECONDS` | 15 | How often prices are scanned |
| `MAX_HOURS_TO_END` | 72 | Only trade markets closing within this window |
| `MIN_EDGE` | 0.05 | Minimum edge (5%) to enter a trade |
| `MIN_CONFIDENCE` | 0.75 | Minimum AI confidence to execute |
| `TAKE_PROFIT_PCT` | 15 | Close at +15% profit |
| `STOP_LOSS_PCT` | -8 | Close at -8% loss |
| `MAX_POSITIONS` | 6 | Maximum simultaneous positions |
| `MODEL` | `claude-sonnet-4-6` | Claude model to use |

---

## 🚀 Usage

```bash
# Run the bot
python scalper.py

# Run in simulation mode (no Polymarket keys needed)
# Just leave POLY_PRIVATE_KEY empty in .env
python scalper.py
```

The bot will:
- Connect to Polymarket (or run in simulation mode)
- Start scanning markets and making decisions
- Log all activity to the console with colored output
- Print a summary when the session ends (or on Ctrl+C)

---

## 💰 Cost Analysis

Claude API costs depend on the model and cycle frequency:

| Model | Input $/MTok | Output $/MTok | ~Cost/call | Cost/hour | Cost/24h |
|---|---|---|---|---|---|
| `claude-opus-4-6` | $5.00 | $25.00 | ~$0.045 | ~$5.40 | ~$130 |
| `claude-sonnet-4-6` | $3.00 | $15.00 | ~$0.027 | ~$3.24 | ~$78 |
| `claude-haiku-4-5` | $1.00 | $5.00 | ~$0.009 | ~$1.08 | ~$26 |

**Recommendation:** Use `claude-haiku-4-5` or `claude-sonnet-4-6` unless your balance justifies Opus costs. As a rule of thumb, your balance should be **at least 50x your daily API cost** to have any chance of profitability.

| Model | Min recommended balance |
|---|---|
| Haiku 4.5 | ~$1,300 |
| Sonnet 4.6 | ~$3,900 |
| Opus 4.6 | ~$6,500 |

---

## 📁 Project Structure

```
polymarket-ai-scalper/
├── scalper.py          # Main bot — entry point
├── config.py           # All configurable parameters
├── brain.py            # Claude AI integration (prompts, parsing)
├── markets.py          # Market data fetching & signal computation
├── executor.py         # Order execution via Polymarket CLOB
├── exits.py            # Exit system (TP, SL, trailing, time stop)
├── state.py            # Global state management
├── logger.py           # Colored console logging
├── requirements.txt    # Python dependencies
├── .env.example        # Environment variable template
├── .gitignore          # Git ignore rules
├── LICENSE             # MIT License
└── README.md           # This file
```

---

## 🛡 Safety Features

- **Circuit Breaker** — Pauses trading if P&L drops below -15%, losing streak hits 5, or drawdown exceeds 20%
- **Position Limits** — Max 6 simultaneous positions, max 30% of balance at risk
- **Dynamic Sizing** — Reduces position size during losing streaks
- **Breakeven Stop** — Moves stop-loss to breakeven after +8% profit
- **Blacklist** — Temporarily avoids markets where recent losses occurred
- **Simulation Mode** — Runs without real money if Polymarket keys aren't configured

---

## 🤝 Contributing

PRs welcome! Some ideas:

- [ ] WebSocket integration for real-time price feeds
- [ ] Database storage for trade history (SQLite)
- [ ] Web dashboard for monitoring
- [ ] Backtesting framework with historical data
- [ ] Multi-model ensemble (use multiple LLMs and vote)
- [ ] Telegram/Discord notifications

---

## 📄 License

MIT — see [LICENSE](LICENSE).

---

## 🙏 Credits

- [Anthropic Claude API](https://docs.anthropic.com)
- [Polymarket CLOB API](https://docs.polymarket.com)
- [py-clob-client](https://github.com/Polymarket/py-clob-client)
