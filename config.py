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
    # Industrial / energy
    "CAT", "XOM", "CVX", "LMT",
    # Semis / enterprise
    "TSM", "AMD", "CRM", "ADBE",
]

BENCHMARK = "SPY"

# ---------------------------------------------------------------------------
# Stage 1: TECHNICAL SCREEN (cheap, runs on every ticker every 30 min)
# A ticker becomes a "candidate" when min_signals fire, or on a panic drop.
# ---------------------------------------------------------------------------
TECHNICAL = {
    "today_drop_pct": 4.0,        # down >= 4% today
    "drop_vs_market_pct": 3.0,    # >= 3% worse than SPY (company-specific)
    "off_52w_high_pct": 20.0,     # >= 20% below 52-week high
    "rsi_oversold": 30.0,         # RSI(14) <= 30
    "volume_spike_ratio": 2.0,    # today's volume >= 2x its 20-day average
    "min_signals": 2,
    "panic_drop_pct": 7.0,        # single-day drop that always alerts
}

# ---------------------------------------------------------------------------
# Stage 2: DIP QUALITY SCORE (0-100), computed only for candidates.
# Blends dip severity, business quality, and valuation/street view --
# the same lenses a desk analyst applies before averaging into a name.
# ---------------------------------------------------------------------------
SCORING = {
    "min_alert_score": 40,   # candidates below this are logged but not pushed
    "strong": 70,            # label thresholds for the alert headline
    "solid": 55,
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
    "realert_hours": 24,           # don't re-alert same ticker within N hours...
    "realert_extra_drop_pct": 3.0, # ...unless it fell this much further
    "max_alerts_per_run": 5,       # cap pushes per scan (worst first)
}

# ---------------------------------------------------------------------------
# Daily summary (sent once after market close by daily-summary.yml)
# ---------------------------------------------------------------------------
SUMMARY = {
    "top_movers": 5,             # show top N losers and gainers
    "oversold_rsi": 35.0,        # list watchlist names with RSI below this
    "near_high_pct": 3.0,        # count names within N% of 52-week high
}
