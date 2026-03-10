"""
config.py — All configurable parameters for the Polymarket AI Scalper.

Edit these values to tune the bot's behavior. The defaults are conservative
and designed for small balances. If you have a larger balance, you can
increase risk parameters accordingly.

Environment variables (from .env) override some of these defaults.
"""

import os
from dotenv import load_dotenv

load_dotenv()

# ══════════════════════════════════════════════════════════════
# CREDENTIALS
# These MUST be set in your .env file. Never hardcode them here.
# ══════════════════════════════════════════════════════════════

# Anthropic API key — get one at https://console.anthropic.com
ANTHROPIC_KEY = os.getenv("ANTHROPIC_KEY")

# Polymarket private key — export from Polymarket Settings
# Leave empty to run in simulation mode (no real trades)
POLY_PRIVATE_KEY = os.getenv("POLY_PRIVATE_KEY", "")

# Your Polymarket wallet address — visible on your profile page
POLY_FUNDER = os.getenv("POLY_FUNDER", "")

# ══════════════════════════════════════════════════════════════
# BALANCE & SESSION
# ══════════════════════════════════════════════════════════════

# Starting balance in USDC. If connected to Polymarket, the bot
# will attempt to read your real balance and override this value.
INITIAL_BALANCE = float(os.getenv("INITIAL_BALANCE", "100"))

# How long the bot runs before stopping (in hours).
# Set to 0 for unlimited (runs until you Ctrl+C).
DURATION_HOURS = float(os.getenv("DURATION_HOURS", "24"))

# ══════════════════════════════════════════════════════════════
# TIMING — How often the bot acts
# ══════════════════════════════════════════════════════════════

# Price scan interval in seconds.
# Every SCAN_SECONDS, the bot fetches prices and checks exits.
# Lower = faster reaction to price changes, but more API calls to Polymarket.
SCAN_SECONDS = 15

# Brain cycle interval in seconds.
# Every BRAIN_SECONDS, the bot sends data to Claude for analysis.
# Lower = more trades but higher API cost.
# Cost per hour ≈ (3600 / BRAIN_SECONDS) × cost_per_call
BRAIN_SECONDS = 30

# ══════════════════════════════════════════════════════════════
# CLAUDE MODEL SELECTION
# ══════════════════════════════════════════════════════════════

# Primary model for trading decisions.
# Options (from cheapest to most expensive):
#   "claude-haiku-4-5-20251001"  — Fast & cheap (~$0.009/call)
#   "claude-sonnet-4-6"          — Balanced   (~$0.027/call)
#   "claude-opus-4-6"            — Best brain (~$0.045/call)
#
# Recommendation: Start with Haiku or Sonnet. Only use Opus if
# your balance is large enough to absorb the API costs.
MODEL = os.getenv("MODEL", "claude-sonnet-4-6")

# Fallback model if the primary model fails (rate limit, error, etc.)
FALLBACK_MODEL = os.getenv("FALLBACK_MODEL", "claude-haiku-4-5-20251001")

# ══════════════════════════════════════════════════════════════
# MARKET FILTERS — What markets the bot looks at
# ══════════════════════════════════════════════════════════════

# How many markets to fetch from Polymarket's API per scan.
# More = wider search but larger prompt (more tokens = more cost).
TOP_MARKETS = 50

# Minimum 24h trading volume in USDC.
# Low-volume markets have poor liquidity and wide spreads.
MIN_VOLUME = 8000

# Minimum liquidity in USDC.
# Below this, orders may not fill or will have significant slippage.
MIN_LIQUIDITY = 3000

# CRITICAL: Maximum hours until market resolution.
# The bot ONLY trades markets closing within this window.
# This is the core of the "short-term scalping" strategy.
#   72  = markets closing within 3 days
#   24  = markets closing within 1 day (aggressive)
#   6   = only imminent markets (very aggressive)
MAX_HOURS_TO_END = 72

# Preferred window — markets within this range get priority scoring.
PREFER_HOURS = 24

# ══════════════════════════════════════════════════════════════
# SIGNAL THRESHOLDS — When to enter trades
# ══════════════════════════════════════════════════════════════

# Minimum confidence from Claude (0.0 to 1.0).
# Higher = fewer trades but (theoretically) better quality.
# 0.75 means Claude must be at least 75% sure.
MIN_CONFIDENCE = 0.75

# Minimum edge (difference between Claude's probability estimate
# and the market price). This is the core signal.
# 0.05 = 5% edge. If Claude thinks an event is 60% likely
# and the market prices it at 54%, that's a 6% edge → trade.
MIN_EDGE = 0.05

# Strong edge threshold — positions are sized larger when
# the edge exceeds this value.
STRONG_EDGE = 0.12

# Volume spike multiplier — if recent volume is this many times
# higher than the average, it's flagged as a volume spike.
# Spikes often indicate informed trading / news.
VOLUME_SPIKE_MULT = 2.5

# ══════════════════════════════════════════════════════════════
# POSITION SIZING & RISK
# ══════════════════════════════════════════════════════════════

# Maximum risk per individual trade as a fraction of balance.
# 0.05 = 5% of balance per trade.
MAX_RISK_PCT = float(os.getenv("MAX_RISK_PCT", "0.05"))

# Maximum total capital at risk across ALL open positions.
# 0.30 = max 30% of balance in active trades.
MAX_RISK_TOTAL = 0.30

# Maximum simultaneous open positions.
MAX_POSITIONS = 6

# Minimum order size in USDC.
# Polymarket has minimum order requirements.
MIN_ORDER_USDC = 1.0

# Maximum order size in USDC per trade.
# Caps individual trade size regardless of edge.
MAX_ORDER_USDC = 10.0

# ══════════════════════════════════════════════════════════════
# EXIT STRATEGY — When to close trades
# ══════════════════════════════════════════════════════════════

# Take Profit — close the position at this % gain.
# Lower = more frequent small wins.
# Higher = fewer but larger wins (more risk of reversal).
TP_NORMAL = 15          # Standard take profit: +15%
TP_STRONG = 25          # For high-edge trades: +25%

# Stop Loss — close the position at this % loss.
# Tighter stops = less damage per loss but more false exits.
SL_NORMAL = -8          # Standard stop loss: -8%

# Trailing Stop — once in profit, if price drops this much
# from its peak, close the position to lock in gains.
# Example: price goes +20%, then drops 3.5% from peak → close.
TRAILING_PCT = 3.5

# Breakeven Stop — after the position gains this much,
# move the stop loss to 0% (breakeven). This means you can
# no longer lose money on this trade.
BREAKEVEN_AFTER = 8     # Move SL to breakeven after +8%

# Time Stop — if the position hasn't moved significantly
# (less than 3% in either direction) after this many minutes,
# close it to free up capital for better opportunities.
TIME_STOP_MIN = 20

# ══════════════════════════════════════════════════════════════
# CIRCUIT BREAKER — Emergency stop conditions
# ══════════════════════════════════════════════════════════════

# If total P&L drops below this %, pause trading for 10 minutes.
# -15 means stop if you've lost 15% of your starting balance.
CB_MAX_LOSS_PCT = -15

# If you hit this many consecutive losses, pause for 5 minutes.
CB_MAX_STREAK = -5

# If drawdown from peak equity exceeds this %, pause for 10 minutes.
CB_MAX_DRAWDOWN = 20

# ══════════════════════════════════════════════════════════════
# POLYMARKET CONNECTION
# ══════════════════════════════════════════════════════════════

# Polymarket CLOB API endpoint. Don't change unless you know
# what you're doing.
POLY_HOST = "https://clob.polymarket.com"

# Polygon network chain ID (137 = mainnet).
POLY_CHAIN_ID = 137

# Signature type for Polymarket authentication.
# 0 = browser wallet (MetaMask, etc.)
# 1 = email/Magic login (most common for Polymarket users)
# 2 = Polymarket proxy wallet
POLY_SIGNATURE_TYPE = 1

# Market data cache duration in seconds.
# Prevents hammering the Gamma API with repeated requests.
MARKET_CACHE_SECONDS = 12
