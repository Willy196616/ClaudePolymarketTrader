"""
exits.py — Position exit system.

Checks all open positions against multiple exit conditions every scan cycle.
This runs MORE FREQUENTLY than the brain (every 15s vs every 30s) to ensure
we don't miss fast price moves.

Exit types (checked in this order):
  1. Take Profit   — Close at target profit %
  2. Stop Loss     — Close at max acceptable loss %
  3. Trailing Stop — If price drops X% from its peak, lock in gains
  4. Time Stop     — If position is flat after N minutes, free up capital
  5. Breakeven     — After +8%, stop loss moves to 0% (can't lose anymore)

Each closed trade is recorded in state["closed_trades"] with full metadata
for performance analysis.
"""

from datetime import datetime

import config
from logger import log
from executor import sell_position


def check_exits(state: dict, markets: list[dict]) -> None:
    """
    Check all open positions for exit conditions.

    This is the core risk management function. It runs every SCAN_SECONDS
    (default 15s) and evaluates each position against TP, SL, trailing stop,
    time stop, and breakeven rules.

    When a position is closed:
      - Balance is updated with the realized P&L
      - Win/loss counters are updated
      - The trade is recorded in closed_trades
      - Losing markets are added to the blacklist
      - The sell order is sent to Polymarket

    Args:
        state:    Global state dict
        markets:  Current market data (for live prices)
    """
    if not state["positions"]:
        return

    # Build a lookup for fast price access
    price_map = {m["condition_id"]: m for m in markets}
    positions_to_close = []

    for cid, position in state["positions"].items():
        market = price_map.get(cid)
        if not market:
            continue

        # ── Get current price for this position's side ──
        current_price = (market["yes_price"] if position["outcome"] == "YES"
                         else market["no_price"])
        entry_price = position["entry_price"]
        if entry_price <= 0:
            continue

        # ── Core metrics ──
        pnl_pct = (current_price - entry_price) / entry_price * 100
        pnl_usdc = position["amount"] * (current_price / entry_price - 1)
        elapsed_min = (
            datetime.now() - datetime.fromisoformat(position["timestamp"])
        ).total_seconds() / 60

        # ── Update peak price (for trailing stop) ──
        if current_price > position.get("max_price", entry_price):
            position["max_price"] = current_price
        max_price = position.get("max_price", entry_price)

        # ── Determine TP/SL thresholds for this position ──
        # High-edge trades get a wider TP target
        tp_threshold = config.TP_NORMAL
        if position.get("edge", 0) >= config.STRONG_EDGE:
            tp_threshold = config.TP_STRONG

        sl_threshold = config.SL_NORMAL
        time_stop = position.get("time_stop_min", config.TIME_STOP_MIN)

        # ── BREAKEVEN: after +8%, move SL to 0% ──
        # Once the position has been profitable enough, we guarantee
        # we won't lose money on it (worst case: break even).
        if pnl_pct >= config.BREAKEVEN_AFTER:
            sl_threshold = max(sl_threshold, 0)

        # ── Check exit conditions (priority order) ──
        exit_reason = None
        is_win = False

        # 1. TAKE PROFIT
        if pnl_pct >= tp_threshold:
            exit_reason = "take_profit"
            is_win = True

        # 2. STOP LOSS
        elif pnl_pct <= sl_threshold:
            exit_reason = "stop_loss"
            is_win = pnl_usdc >= 0  # Could be win if breakeven kicked in

        # 3. TRAILING STOP
        # If price was above entry (profitable) but has dropped from peak
        elif max_price > entry_price and pnl_pct > 0:
            drop_from_peak = (max_price - current_price) / max_price * 100
            if drop_from_peak >= config.TRAILING_PCT:
                exit_reason = "trailing_stop"
                is_win = True  # Trailing only triggers in profit

        # 4. TIME STOP
        # Position hasn't moved significantly — free up capital
        elif elapsed_min >= time_stop and abs(pnl_pct) < 3:
            exit_reason = "time_stop"
            is_win = pnl_usdc >= 0

        # ── Execute exit if triggered ──
        if exit_reason:
            _close_position(state, cid, position, pnl_usdc, pnl_pct,
                            elapsed_min, exit_reason, is_win)
            positions_to_close.append(cid)
        else:
            # Periodically log active positions
            if state["cycle"] % 5 == 0:
                log("INFO", f"  📊 {position['outcome']} "
                            f"{entry_price:.3f}→{current_price:.3f} "
                            f"({pnl_pct:+.1f}%) peak:{max_price:.3f} | "
                            f"{elapsed_min:.0f}min")

    # ── Remove closed positions from state ──
    for cid in positions_to_close:
        if cid in state["positions"]:
            del state["positions"][cid]

    # ── Update drawdown tracking ──
    _update_drawdown(state)

    # ── Clean blacklist periodically ──
    if state["cycle"] % 50 == 0 and state["blacklist"]:
        state["blacklist"].clear()
        log("INFO", "🔓 Blacklist cleared")


# ══════════════════════════════════════════════════════════════
# HELPERS (private)
# ══════════════════════════════════════════════════════════════

def _close_position(state: dict, cid: str, position: dict,
                    pnl_usdc: float, pnl_pct: float,
                    elapsed_min: float, exit_reason: str,
                    is_win: bool) -> None:
    """
    Close a position: update balance, counters, and records.

    Args:
        state:        Global state dict
        cid:          Market condition_id
        position:     Position data dict
        pnl_usdc:     Realized P&L in USDC
        pnl_pct:      Realized P&L in %
        elapsed_min:  How long the position was open
        exit_reason:  Why it was closed (take_profit, stop_loss, etc.)
        is_win:       Whether this counts as a win
    """
    # Update balance (return principal + profit/loss)
    state["balance"] += position["amount"] + pnl_usdc
    state["total_pnl"] += pnl_usdc

    # Update win/loss counters and streak
    if is_win:
        state["wins"] += 1
        state["streak"] = max(1, state["streak"] + 1)
    else:
        state["losses"] += 1
        state["streak"] = min(-1, state["streak"] - 1)
        # Blacklist this market temporarily to avoid revenge trading
        state["blacklist"].add(cid)

    # Log with appropriate icon
    icons = {
        "take_profit":   "✅ TP",
        "stop_loss":     "❌ SL",
        "trailing_stop": "🔻 TRAIL",
        "time_stop":     "⏱  TIME",
    }
    icon = icons.get(exit_reason, "?")
    log("TRADE", f"{icon} {pnl_pct:+.1f}% (${pnl_usdc:+.2f}) | "
                 f"{elapsed_min:.0f}min | {position['question'][:45]}")

    # Record the closed trade
    state["closed_trades"].append({
        **position,
        "pnl":           pnl_usdc,
        "pnl_pct":       pnl_pct,
        "result":        "win" if is_win else "loss",
        "exit_reason":   exit_reason,
        "duration_min":  elapsed_min,
    })

    # Attempt to sell on Polymarket
    sell_position(position)


def _update_drawdown(state: dict) -> None:
    """
    Update peak equity and maximum drawdown.

    Drawdown = how far equity has fallen from its highest point.
    This is a key risk metric — the circuit breaker uses it.
    """
    current_equity = state["balance"] + sum(
        p["amount"] for p in state["positions"].values()
    )

    # Update peak
    if current_equity > state["peak_balance"]:
        state["peak_balance"] = current_equity

    # Calculate drawdown
    if state["peak_balance"] > 0:
        drawdown = (
            (state["peak_balance"] - current_equity)
            / state["peak_balance"] * 100
        )
        if drawdown > state["max_drawdown"]:
            state["max_drawdown"] = drawdown
