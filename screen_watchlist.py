"""
Monthly watchlist refresh.

Re-screens universe.csv (a broad large-cap universe) for quality, momentum,
and stability, and proposes the top N as the new WATCHLIST in config.py.
Run via .github/workflows/watchlist-refresh.yml, which opens a PR with the
result -- it never commits directly to main.

Usage:
  python screen_watchlist.py            # rewrite config.py + write
                                         # watchlist_diff.md if changed
  python screen_watchlist.py --dry-run  # print results, change nothing
"""

from __future__ import annotations

import csv
import re
import sys
import time
from pathlib import Path

import yfinance as yf

from kpis import _pts, quality_score  # reuse the same scoring-band helper

ROOT = Path(__file__).resolve().parent
UNIVERSE_FILE = ROOT / "universe.csv"
CONFIG_FILE = ROOT / "config.py"
DIFF_FILE = ROOT / "watchlist_diff.md"

TOP_N = 24

# Minimum quality/stability bar -- names failing any of these are dropped
# from consideration regardless of score, no matter how "hot" they are.
MIN_ROE = 0.10          # >= 10% return on equity
MIN_MARGIN = 0.0        # profitable
MAX_DEBT_TO_EQUITY = 200.0
MIN_MARKET_CAP = 10e9   # $10B+


def load_universe() -> list[str]:
    with open(UNIVERSE_FILE, newline="") as f:
        return [row["ticker"].strip() for row in csv.DictReader(f) if row["ticker"].strip()]


def score_ticker(symbol: str) -> dict | None:
    tk = yf.Ticker(symbol)
    try:
        info = tk.info or {}
    except Exception as e:  # noqa: BLE001
        print(f"  {symbol}: info fetch failed ({e})")
        return None

    roe = info.get("returnOnEquity")
    margin = info.get("profitMargins")
    de = info.get("debtToEquity")
    mcap = info.get("marketCap")
    rev_growth = info.get("revenueGrowth")
    fcf = info.get("freeCashflow")
    revenue = info.get("totalRevenue")
    beta = info.get("beta")
    price = info.get("currentPrice") or info.get("regularMarketPrice")
    high52 = info.get("fiftyTwoWeekHigh")
    low52 = info.get("fiftyTwoWeekLow")

    fcf_margin = (fcf / revenue) if (fcf and revenue) else None

    # --- hard filters: "stable" means profitable, solvent, large ---
    if roe is None or roe < MIN_ROE:
        return None
    if margin is None or margin < MIN_MARGIN:
        return None
    if de is not None and de > MAX_DEBT_TO_EQUITY:
        return None
    if mcap is None or mcap < MIN_MARKET_CAP:
        return None

    # --- QUALITY (0-40), same bands as the dip-quality scorer ---
    quality = quality_score({
        "roe": roe, "de": de, "fcf_margin": fcf_margin,
        "rev_growth": rev_growth, "margin": margin,
    })

    # --- PERFORMANCE (0-30): "high performing" = strong, resilient price action ---
    off_high_pct = None
    if price and high52:
        off_high_pct = (price / high52 - 1) * 100  # <= 0
    return_1y_pct = None
    if price and low52 and high52:
        # crude proxy for trend strength: where in the 52w range is it sitting?
        rng = high52 - low52
        if rng > 0:
            return_1y_pct = (price - low52) / rng * 100  # 0-100

    performance = 0.0
    performance += _pts(off_high_pct, [(-3, 15), (-10, 10), (-20, 5)], higher_is_better=True)
    performance += _pts(return_1y_pct, [(80, 15), (60, 10), (40, 5)])
    performance = min(performance, 30)

    # --- STABILITY (0-30): low beta + mega-cap size ---
    stability = 0.0
    stability += _pts(beta, [(0.8, 15), (1.1, 10), (1.4, 5)], higher_is_better=False)
    stability += _pts(mcap, [(200e9, 15), (50e9, 10), (10e9, 5)])
    stability = min(stability, 30)

    total = round(quality + performance + stability)
    return {
        "ticker": symbol,
        "score": total,
        "quality": round(quality),
        "performance": round(performance),
        "stability": round(stability),
        "roe": roe,
        "margin": margin,
        "mcap": mcap,
        "beta": beta,
    }


AUTO_WATCHLIST_PATTERN = (
    r"# --- AUTO-WATCHLIST:BEGIN ---\nWATCHLIST = \[.*?\]\n# --- AUTO-WATCHLIST:END ---"
)


def rewrite_config(new_watchlist: list[str]) -> str:
    """Replace the WATCHLIST block between the AUTO-WATCHLIST markers."""
    text = CONFIG_FILE.read_text()
    lines = ["    " + ", ".join(f'"{t}"' for t in new_watchlist[i:i + 7]) + ","
             for i in range(0, len(new_watchlist), 7)]
    block = ("# --- AUTO-WATCHLIST:BEGIN ---\nWATCHLIST = [\n" + "\n".join(lines)
             + "\n]\n# --- AUTO-WATCHLIST:END ---")
    new_text = re.sub(AUTO_WATCHLIST_PATTERN, block, text, count=1, flags=re.DOTALL)
    CONFIG_FILE.write_text(new_text)
    return new_text


def current_watchlist() -> list[str]:
    text = CONFIG_FILE.read_text()
    m = re.search(AUTO_WATCHLIST_PATTERN, text, re.DOTALL)
    return re.findall(r'"([^"]+)"', m.group(0))


def main():
    dry_run = "--dry-run" in sys.argv
    universe = load_universe()
    results = []
    for i, symbol in enumerate(universe):
        result = score_ticker(symbol)
        if result:
            results.append(result)
            print(f"  {symbol}: score {result['score']} "
                  f"(quality {result['quality']}, performance {result['performance']}, "
                  f"stability {result['stability']})")
        else:
            print(f"  {symbol}: filtered out")
        if i < len(universe) - 1:
            time.sleep(0.3)  # be polite to Yahoo

    results.sort(key=lambda r: -r["score"])
    new_watchlist = sorted(r["ticker"] for r in results[:TOP_N])

    old_watchlist = current_watchlist()
    added = sorted(set(new_watchlist) - set(old_watchlist))
    removed = sorted(set(old_watchlist) - set(new_watchlist))

    print(f"\nTop {TOP_N}: {new_watchlist}")
    print(f"Added: {added}")
    print(f"Removed: {removed}")

    if dry_run:
        return

    if not added and not removed:
        print("No change.")
        return

    rewrite_config(new_watchlist)

    score_by_ticker = {r["ticker"]: r["score"] for r in results}
    lines = ["## Watchlist refresh\n",
             f"Re-screened {len(universe)} large-cap names for quality, "
             f"performance, and stability. Top {TOP_N} by composite score:\n"]
    if added:
        lines.append("**Added:**")
        for t in added:
            lines.append(f"- {t} (score {score_by_ticker.get(t)})")
        lines.append("")
    if removed:
        lines.append("**Removed:**")
        for t in removed:
            lines.append(f"- {t}")
        lines.append("")
    lines.append("Review before merging -- this is a proposal, not gospel.")
    DIFF_FILE.write_text("\n".join(lines))


if __name__ == "__main__":
    main()
