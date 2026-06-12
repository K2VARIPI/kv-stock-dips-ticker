"""
Configuration for the stock dip monitor (v2).

WATCHLIST: Edit freely. A starting point of large-cap, financially strong
companies -- NOT a recommendation. The tool works best when this list only
contains companies you've researched and would genuinely buy at a discount.
"""

WATCHLIST = [
    # Mega-cap tech
    "MSFT", "AAPL", "GOOGL", "AMZN", "META", "NVDA", "AVGO",
    # Payments / financials
    "V", "MA", "JPM", "BRK-B",
    # Healthcare
    "UNH", "LLY", "JNJ", "ABBV", "TMO",
    # Consumer / retail
    "COST", "WMT", "PG", "KO", "MCD", "HD",
    # Enterprise software
    "CRM", "ADBE",
]
# Dropped vs v1: CAT, XOM, CVX, LMT (commodity/cyclical, lower margin quality),
# AMD, TSM (more volatile / geopolitical risk). Keep this list to names with
# durable moats, strong balance sheets, and consistent profitability -- the
# kind you'd genuinely back up the truck on during a crash.

BENCHMARK = "SPY"

# ---------------------------------------------------------------------------
# Stage 1: TECHNICAL SCREEN (cheap, runs on every ticker every 30 min)
# A ticker becomes a "candidate" when min_signals fire, or on a panic drop.
# ---------------------------------------------------------------------------
TECHNICAL = {
    "today_drop_pct": 8.0,        # down >= 8% today (crash-level single day)
    "drop_vs_market_pct": 5.0,    # >= 5% worse than SPY (company-specific carnage)
    "off_52w_high_pct": 30.0,     # >= 30% below 52-week high (deep correction)
    "rsi_oversold": 20.0,         # RSI(14) <= 20 (extreme, rare oversold)
    "volume_spike_ratio": 3.0,    # today's volume >= 3x its 20-day average (panic selling)
    "min_signals": 3,             # require strong confirmation, not just one signal
    "panic_drop_pct": 10.0,       # single-day drop that always alerts
}

# ---------------------------------------------------------------------------
# Stage 2: DIP QUALITY SCORE (0-100), computed only for candidates.
# Blends dip severity, business quality, and valuation/street view --
# the same lenses a desk analyst applies before averaging into a name.
# ---------------------------------------------------------------------------
SCORING = {
    "min_alert_score": 70,   # candidates below this are logged but not pushed --
                             # only push when it's a genuinely strong opportunity
    "strong": 80,            # label thresholds for the alert headline
    "solid": 70,
}

# ---------------------------------------------------------------------------
# Risk flags
# ---------------------------------------------------------------------------
RISK = {
    "earnings_warn_days": 7,     # warn if earnings within N days (pre or post)
}

# ---------------------------------------------------------------------------
# Alerting behavior
# ---------------------------------------------------------------------------
ALERTS = {
    "realert_hours": 48,           # don't re-alert same ticker within N hours...
    "realert_extra_drop_pct": 5.0, # ...unless it fell this much further
    "max_alerts_per_run": 3,       # cap pushes per scan (worst first)
}

# ---------------------------------------------------------------------------
# Daily summary (sent once after market close by daily-summary.yml)
# ---------------------------------------------------------------------------
SUMMARY = {
    "top_movers": 5,             # show top N losers and gainers
    "oversold_rsi": 35.0,        # list watchlist names with RSI below this
    "near_high_pct": 3.0,        # count names within N% of 52-week high
}
