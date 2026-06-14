"""
Fundamental KPIs, earnings awareness, news context, and the composite
Dip Quality Score (0-100).

These are the lenses an experienced analyst applies before averaging into
a falling name:

  TECHNICAL (0-35)   How severe/oversold is the dip itself?
  QUALITY   (0-40)   Is this a business worth owning? (ROE, leverage,
                     free cash flow, growth, margins)
  VALUATION (0-25)   Is the street's view + multiple supportive?
                     (analyst upside, PEG, forward vs trailing P/E,
                     consensus rating)

Fundamentals are fetched ONLY for tickers that pass the technical screen,
keeping API usage light.
"""

from __future__ import annotations

from datetime import date, datetime, timezone

import yfinance as yf

from config import RISK, SCORING

_INFO_KEYS = {
    "trailingPE": "pe",
    "forwardPE": "fwd_pe",
    "trailingPegRatio": "peg",
    "pegRatio": "peg_alt",
    "returnOnEquity": "roe",                 # fraction, e.g. 0.32
    "debtToEquity": "de",                    # percent-style, e.g. 45.2
    "freeCashflow": "fcf",
    "totalRevenue": "revenue",
    "revenueGrowth": "rev_growth",           # fraction YoY
    "profitMargins": "margin",               # fraction
    "targetMeanPrice": "target",
    "recommendationMean": "rec",             # 1=Strong Buy ... 5=Sell
    "recommendationKey": "rec_key",
    "marketCap": "mcap",
    "beta": "beta",
    "dividendYield": "div_yield",
    "shortPercentOfFloat": "short_pct",
}


# ---------------------------------------------------------------- fetchers

def fetch_fundamentals(tk: yf.Ticker) -> dict:
    """Pull the KPI set from Yahoo. Missing fields come back as None."""
    out = {v: None for v in _INFO_KEYS.values()}
    try:
        info = tk.info or {}
    except Exception as e:  # noqa: BLE001
        print(f"    info fetch failed: {e}")
        return out
    for src, dst in _INFO_KEYS.items():
        val = info.get(src)
        if isinstance(val, (int, float)):
            out[dst] = float(val)
        elif isinstance(val, str):
            out[dst] = val
    if out["peg"] is None:
        out["peg"] = out.pop("peg_alt", None)
    else:
        out.pop("peg_alt", None)
    # FCF margin if both pieces exist
    if out.get("fcf") and out.get("revenue"):
        out["fcf_margin"] = out["fcf"] / out["revenue"]
    else:
        out["fcf_margin"] = None
    return out


def fetch_earnings_proximity(tk: yf.Ticker) -> dict:
    """Days to next earnings (negative = just reported N days ago)."""
    out = {"days_to_earnings": None, "warn": False, "label": None}
    today = date.today()
    candidates: list[date] = []
    try:
        cal = tk.calendar
        dates = (cal or {}).get("Earnings Date", []) if isinstance(cal, dict) else []
        for d in dates:
            if isinstance(d, datetime):
                d = d.date()
            if isinstance(d, date):
                candidates.append(d)
    except Exception as e:  # noqa: BLE001
        print(f"    earnings fetch failed: {e}")
    if not candidates:
        return out
    nearest = min(candidates, key=lambda d: abs((d - today).days))
    days = (nearest - today).days
    out["days_to_earnings"] = days
    warn_window = RISK["earnings_warn_days"]
    if 0 <= days <= warn_window:
        out["warn"] = True
        out["label"] = f"Earnings in {days}d ({nearest})"
    elif -warn_window <= days < 0:
        out["warn"] = True
        out["label"] = f"Earnings {abs(days)}d ago — check the report/guidance"
    return out


def fetch_top_news(tk: yf.Ticker) -> str | None:
    """Most recent headline, to hint at WHY the stock is down."""
    try:
        items = tk.news or []
        for item in items[:3]:
            # yfinance has shipped two shapes over time
            title = (item.get("content") or {}).get("title") or item.get("title")
            if title:
                return str(title)[:140]
    except Exception as e:  # noqa: BLE001
        print(f"    news fetch failed: {e}")
    return None


# ---------------------------------------------------------------- scoring

def _pts(value, bands: list[tuple[float, float]], higher_is_better=True) -> float:
    """Award points from (threshold, points) bands. None -> 0.

    IMPORTANT: bands must be ordered from best to worst threshold
    (descending if higher_is_better, ascending otherwise) -- the first
    matching band wins.
    """
    if value is None:
        return 0.0
    for threshold, points in bands:
        if (value >= threshold) if higher_is_better else (value <= threshold):
            return points
    return 0.0


# Shared with screen_watchlist.py so the dip-quality scorer and the monthly
# watchlist refresher agree on what "quality" means -- tune in one place.
QUALITY_BANDS = {
    "roe": [(0.25, 8), (0.15, 6), (0.05, 3)],
    "de": [(50, 8), (100, 5), (200, 2)],
    "fcf_margin": [(0.20, 8), (0.10, 6), (0.0001, 3)],
    "rev_growth": [(0.12, 8), (0.05, 6), (0.0, 3)],
    "margin": [(0.20, 8), (0.10, 5), (0.0, 2)],
}


def quality_score(fund: dict) -> float:
    """Business-quality score (0-40) from ROE, leverage, FCF margin, growth, and margin."""
    q = 0.0
    q += _pts(fund.get("roe"), QUALITY_BANDS["roe"])
    q += _pts(fund.get("de"), QUALITY_BANDS["de"], higher_is_better=False)
    q += _pts(fund.get("fcf_margin"), QUALITY_BANDS["fcf_margin"])
    q += _pts(fund.get("rev_growth"), QUALITY_BANDS["rev_growth"])
    q += _pts(fund.get("margin"), QUALITY_BANDS["margin"])
    return min(q, 40)


def dip_quality_score(tech: dict, fund: dict) -> tuple[int, dict]:
    """Composite 0-100 score plus per-pillar breakdown."""

    # --- TECHNICAL severity (0-35): bigger, more oversold dip = more points
    t = 0.0
    t += _pts(abs(tech["today_chg"]), [(8, 10), (6, 8), (4, 5)])
    t += _pts(abs(min(tech["off_high"], 0)), [(30, 10), (20, 7), (10, 4)])
    t += _pts(tech["rsi"], [(25, 10), (30, 7), (40, 4)], higher_is_better=False)
    t += _pts(tech.get("vol_ratio"), [(3, 5), (2, 3), (1.5, 1)])
    technical = min(t, 35)

    # --- QUALITY (0-40): is this a business you want more of when it's down?
    quality = quality_score(fund)

    # --- VALUATION / STREET (0-25)
    v = 0.0
    upside = None
    if fund.get("target") and tech.get("price"):
        upside = (fund["target"] / tech["price"] - 1) * 100
        fund["upside"] = upside
    v += _pts(upside, [(25, 10), (15, 7), (5, 4)])
    if fund.get("fwd_pe") and fund.get("pe") and fund["fwd_pe"] < fund["pe"]:
        v += 5  # earnings expected to grow into the multiple
    v += _pts(fund.get("peg"), [(1.5, 5), (2.5, 3)], higher_is_better=False)
    v += _pts(fund.get("rec"), [(2.0, 5), (2.5, 3)], higher_is_better=False)
    valuation = min(v, 25)

    total = round(technical + quality + valuation)
    return total, {"technical": round(technical), "quality": round(quality),
                   "valuation": round(valuation)}


def score_label(score: int) -> str:
    if score >= SCORING["strong"]:
        return "STRONG"
    if score >= SCORING["solid"]:
        return "SOLID"
    return "SPECULATIVE"
