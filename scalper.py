"""
scalper.py — Main entry point for the Polymarket AI Scalper.

This is the trading loop that ties everything together:
  1. Initialize connections (Polymarket, Claude)
  2. Scan prices every SCAN_SECONDS
  3. Check exits on every scan
  4. Call Claude's brain every BRAIN_SECONDS
  5. Execute trades based on AI analysis
  6. Monitor circuit breaker conditions
  7. Print periodic status banners
  8. Summarize session on exit

Usage:
    python scalper.py

The bot runs until DURATION_HOURS is reached or you press Ctrl+C.
"""

import time
import signal
import sys
from datetime import datetime

import config
from state import create_initial_state
from logger import log, banner, COLORS
from markets import fetch_markets
from brain import analyze_markets
from executor import init_polymarket, execute_trade, get_real_balance, is_connected
from exits import check_exits


def print_startup_banner() -> None:
    """Print the startup banner with current configuration."""
    c = COLORS
    print(f"""{c['B']}{c['SYS']}
╔══════════════════════════════════════════════════════════════╗
║              POLYMARKET AI SCALPER                           ║
║                                                              ║
║   🧠 Model:       {config.MODEL:<43}║
║   ⚡ Scan:        every {config.SCAN_SECONDS}s | Brain: every {config.BRAIN_SECONDS}s{' ' * (25 - len(str(config.SCAN_SECONDS)) - len(str(config.BRAIN_SECONDS)))}║
║   🎯 Focus:       markets ≤{config.MAX_HOURS_TO_END}h to resolution                  ║
║   💰 TP/SL:       +{config.TP_NORMAL}% / {config.SL_NORMAL}% (trailing {config.TRAILING_PCT}%){' ' * 17}║
║   📊 Max pos:     {config.MAX_POSITIONS} × ${config.MAX_ORDER_USDC:.0f} max each{' ' * 25}║
║   🛡  Breaker:    {config.CB_MAX_LOSS_PCT}% P&L / {abs(config.CB_MAX_STREAK)} loss streak / {config.CB_MAX_DRAWDOWN}% DD  ║
╚══════════════════════════════════════════════════════════════╝
{c['R']}""")


def circuit_breaker_check(state: dict) -> bool:
    """
    Emergency stop: pause trading if losses are excessive.

    This protects against catastrophic losses by temporarily halting
    the bot when key risk thresholds are breached.

    Checks:
      1. Total P&L below CB_MAX_LOSS_PCT → pause 10 min
      2. Consecutive losses exceed CB_MAX_STREAK → pause 5 min
      3. Drawdown exceeds CB_MAX_DRAWDOWN → pause 10 min

    Args:
        state: Global state dict

    Returns:
        True if the circuit breaker was triggered (bot paused).
    """
    pnl_pct = ((state["balance"] - config.INITIAL_BALANCE)
               / config.INITIAL_BALANCE * 100)

    # ── Check 1: Total P&L threshold ──
    if pnl_pct <= config.CB_MAX_LOSS_PCT:
        log("WARN", f"🚨 CIRCUIT BREAKER: P&L {pnl_pct:.1f}% — "
                     f"Pausing 10 minutes")
        time.sleep(600)
        return True

    # ── Check 2: Losing streak ──
    if state["streak"] <= config.CB_MAX_STREAK:
        log("WARN", f"🚨 CIRCUIT BREAKER: {abs(state['streak'])} consecutive "
                     f"losses — Pausing 5 minutes")
        time.sleep(300)
        state["streak"] = -2  # Partial reset to allow resumption
        return True

    # ── Check 3: Drawdown from peak ──
    if state["max_drawdown"] > config.CB_MAX_DRAWDOWN:
        log("WARN", f"🚨 CIRCUIT BREAKER: Drawdown {state['max_drawdown']:.1f}% — "
                     f"Pausing 10 minutes")
        time.sleep(600)
        return True

    return False


def print_session_summary(state: dict) -> None:
    """
    Print a detailed summary when the session ends.

    Shows:
      - Final portfolio status (via banner)
      - Full trade history with exit reasons
      - Aggregate statistics (avg win, avg loss, profit factor)
      - Breakdown by exit type
    """
    c = COLORS

    log("SYS", "\n" + "═" * 60)
    log("SYS", "SESSION COMPLETE")
    log("SYS", "═" * 60)
    banner(state)

    trades = state["closed_trades"]
    if not trades:
        log("SYS", "No trades were executed this session.")
        return

    # ── Full trade history ──
    log("SYS", "\n📋 Trade History:")
    for t in trades:
        icon = "✅" if t["result"] == "win" else "❌"
        log("SYS", f"  {icon} {t['outcome']} | {t['pnl']:+.2f} | "
                    f"{t['exit_reason']} | {t.get('duration_min', 0):.0f}min | "
                    f"{t['question'][:40]}")

    # ── Aggregate statistics ──
    win_trades = [t for t in trades if t["result"] == "win"]
    loss_trades = [t for t in trades if t["result"] == "loss"]

    print(f"\n{c['B']}── Statistics ──{c['R']}")
    print(f"  Total trades:    {len(trades)}")
    print(f"  Win rate:        {len(win_trades)}/{len(trades)} "
          f"({len(win_trades) / max(len(trades), 1) * 100:.0f}%)")

    if win_trades:
        avg_win = sum(t["pnl"] for t in win_trades) / len(win_trades)
        avg_win_dur = sum(t.get("duration_min", 0)
                         for t in win_trades) / len(win_trades)
        print(f"  Avg win:         +${avg_win:.2f} ({avg_win_dur:.0f}min avg)")

    if loss_trades:
        avg_loss = sum(t["pnl"] for t in loss_trades) / len(loss_trades)
        avg_loss_dur = sum(t.get("duration_min", 0)
                          for t in loss_trades) / len(loss_trades)
        print(f"  Avg loss:        ${avg_loss:.2f} ({avg_loss_dur:.0f}min avg)")

    # Profit factor = avg_win / avg_loss (> 1.0 is good)
    if win_trades and loss_trades:
        avg_w = sum(t["pnl"] for t in win_trades) / len(win_trades)
        avg_l = abs(sum(t["pnl"] for t in loss_trades) / len(loss_trades))
        print(f"  Profit factor:   {avg_w / max(avg_l, 0.01):.2f}")

    print(f"  Max drawdown:    {state['max_drawdown']:.1f}%")
    print(f"  Total P&L:       {'+'if state['total_pnl']>=0 else ''}"
          f"{state['total_pnl']:.2f} USDC")

    # ── Breakdown by exit type ──
    reasons = {}
    for t in trades:
        reason = t.get("exit_reason", "unknown")
        if reason not in reasons:
            reasons[reason] = {"count": 0, "pnl": 0.0}
        reasons[reason]["count"] += 1
        reasons[reason]["pnl"] += t.get("pnl", 0)

    print(f"\n{c['B']}── By Exit Type ──{c['R']}")
    for reason, data in sorted(reasons.items(), key=lambda x: -x[1]["pnl"]):
        print(f"  {reason:20s}: {data['count']} trades | "
              f"${data['pnl']:+.2f}")


# ══════════════════════════════════════════════════════════════
# MAIN LOOP
# ══════════════════════════════════════════════════════════════

def main() -> None:
    """
    Main trading loop.

    The loop has two frequencies:
      - Fast loop (SCAN_SECONDS):  fetch prices + check exits
      - Slow loop (BRAIN_SECONDS): call Claude for analysis + execute trades

    This ensures exits react quickly to price changes while limiting
    the number of (expensive) Claude API calls.
    """
    # ── Initialize state ──
    state = create_initial_state()

    # ── Handle Ctrl+C gracefully ──
    def signal_handler(sig, frame):
        log("SYS", "\n⚡ Interrupted! Printing summary...")
        print_session_summary(state)
        sys.exit(0)

    signal.signal(signal.SIGINT, signal_handler)

    # ── Startup ──
    print_startup_banner()

    if not config.ANTHROPIC_KEY:
        log("WARN", "❌ ANTHROPIC_KEY not set in .env — cannot start")
        return

    log("SYS", f"Balance: ${config.INITIAL_BALANCE:.2f} USDC | "
                f"Duration: {config.DURATION_HOURS}h")

    # ── Connect to Polymarket ──
    poly_ok = init_polymarket()
    if poly_ok:
        log("SYS", "🟢 MODE: LIVE TRADING")
        real_balance = get_real_balance()
        if real_balance and real_balance > 0:
            state["balance"] = real_balance
            state["peak_balance"] = real_balance
            log("INFO", f"Real balance: ${real_balance:.2f}")
    else:
        log("SYS", "🟡 MODE: SIMULATION (no Polymarket keys)")

    log("SYS", "🚀 Scalper started!")

    # ── Compute end time ──
    if config.DURATION_HOURS > 0:
        end_time = time.time() + config.DURATION_HOURS * 3600
    else:
        end_time = float("inf")  # Run forever

    last_brain_time = 0

    # ══════════════════════════════════════════════════════════
    # MAIN LOOP
    # ══════════════════════════════════════════════════════════
    while time.time() < end_time:
        state["scan_cycle"] += 1
        now = time.time()

        # ── 1. Fetch market prices (every SCAN_SECONDS) ──
        markets = fetch_markets(state)
        if not markets:
            time.sleep(15)
            continue

        # ── 2. Check exits ALWAYS (fast reaction to price moves) ──
        if state["positions"]:
            check_exits(state, markets)

        # ── 3. Circuit breaker ──
        if circuit_breaker_check(state):
            continue

        # ── 4. Brain analysis (every BRAIN_SECONDS) ──
        if now - last_brain_time >= config.BRAIN_SECONDS:
            state["cycle"] += 1
            remaining = (end_time - now) / 3600 if end_time != float("inf") else 0

            log("SYS", f"{'─' * 56}")
            log("SYS", f"CYCLE #{state['cycle']} | ${state['balance']:.2f} | "
                       f"{len(state['positions'])} pos | "
                       f"{remaining:.1f}h left" if remaining else "")

            # Call Claude for analysis
            analysis = analyze_markets(state, markets)
            # Execute trade if Claude says buy
            execute_trade(state, analysis)

            last_brain_time = now

            # ── 5. Periodic status banner ──
            if state["cycle"] % 10 == 0:
                banner(state)

        # ── 6. Wait for next scan ──
        time.sleep(config.SCAN_SECONDS)

    # ══════════════════════════════════════════════════════════
    # SESSION ENDED
    # ══════════════════════════════════════════════════════════
    print_session_summary(state)


if __name__ == "__main__":
    main()
