"""
Stock Dip Monitor v2
--------------------
Two-stage pipeline modeled on how a desk analyst triages a falling name:

  Stage 1  TECHNICAL SCREEN  (all tickers, every run)
           today's drop, drop vs SPY, distance from 52w high, RSI(14),
           volume spike, 50/200-DMA position

  Stage 2  KPI ENRICHMENT + DIP QUALITY SCORE  (candidates only)
           ROE, debt/equity, FCF margin, revenue growth, profit margin,
           P/E + forward P/E, PEG, analyst target upside, consensus rating,
           beta, short interest, dividend yield
           + earnings-date proximity warning
           + latest news headline (the "why")

Alerts are pushed via ntfy.sh and logged to state/history.json so the daily
summary can report how past alerts actually performed (7d / 30d forward
returns) -- i.e., whether your thresholds have an edge.

Usage:
  python monitor.py             # intraday scan
  python monitor.py --summary   # end-of-day watchlist health + performance
  python monitor.py --test      # send a test push

Env: NTFY_TOPIC (your private ntfy.sh topic)
"""

from __future__ import annotations

import json
import sys
from datetime import datetime, timezone, timedelta
from pathlib import Path

import pandas as pd
import yfinance as yf

import notify
from config import WATCHLIST, BENCHMARK, TECHNICAL, SCORING, ALERTS, SUMMARY
from kpis import (dip_quality_score, fetch_earnings_proximity,
                  fetch_fundamentals, fetch_top_news, score_label)

STATE_DIR = Path(__file__).parent / "state"
ALERT_STATE = STATE_DIR / "alerts.json"
HISTORY = STATE_DIR / "history.json"


# ---------------------------------------------------------------- state

def _load(path: Path, default):
    if path.exists():
        try:
            return json.loads(path.read_text())
        except json.JSONDecodeError:
            pass
    return default


def _save(path: Path, obj) -> None:
    STATE_DIR.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(obj, indent=2))


# ---------------------------------------------------------------- indicators

def rsi(closes: pd.Series, period: int = 14) -> float:
    delta = closes.diff()
    gain = delta.clip(lower=0).ewm(alpha=1 / period, adjust=False).mean()
    loss = (-delta.clip(upper=0)).ewm(alpha=1 / period, adjust=False).mean()
    rs = gain / loss.replace(0, 1e-10)
    return float((100 - 100 / (1 + rs)).iloc[-1])


# ---------------------------------------------------------------- stage 1

def technical_screen(ticker: str, df: pd.DataFrame, spy_change: float) -> dict | None:
    """Return metrics + fired signals if the ticker is a dip candidate."""
    closes = df["Close"].dropna()
    if len(closes) < 200:
        return None
    vols = df["Volume"].dropna()

    price = float(closes.iloc[-1])
    today_chg = (price / float(closes.iloc[-2]) - 1) * 100
    off_high = (price / float(closes.max()) - 1) * 100
    rsi_val = rsi(closes)
    vs_market = today_chg - spy_change
    dma50 = float(closes.rolling(50).mean().iloc[-1])
    dma200 = float(closes.rolling(200).mean().iloc[-1])
    vol_ratio = None
    if len(vols) >= 21 and float(vols.iloc[-21:-1].mean()) > 0:
        vol_ratio = float(vols.iloc[-1]) / float(vols.iloc[-21:-1].mean())

    t = TECHNICAL
    signals = []
    if today_chg <= -t["today_drop_pct"]:
        signals.append(f"Down {abs(today_chg):.1f}% today")
    if vs_market <= -t["drop_vs_market_pct"]:
        signals.append(f"{abs(vs_market):.1f}% worse than SPY (company-specific)")
    if off_high <= -t["off_52w_high_pct"]:
        signals.append(f"{abs(off_high):.1f}% below 52-wk high")
    if rsi_val <= t["rsi_oversold"]:
        signals.append(f"RSI {rsi_val:.0f} (oversold)")
    if vol_ratio and vol_ratio >= t["volume_spike_ratio"]:
        signals.append(f"Volume {vol_ratio:.1f}x its 20-day average")

    panic = today_chg <= -t["panic_drop_pct"]
    if panic and not signals:
        signals.append(f"Panic drop: {abs(today_chg):.1f}% today")
    if not (panic or len(signals) >= t["min_signals"]):
        return None

    return {
        "ticker": ticker, "price": price, "today_chg": today_chg,
        "off_high": off_high, "rsi": rsi_val, "vs_market": vs_market,
        "vol_ratio": vol_ratio, "below_50dma": price < dma50,
        "below_200dma": price < dma200, "signals": signals, "panic": panic,
    }


# ---------------------------------------------------------------- stage 2

def enrich(hit: dict) -> dict:
    """Attach fundamentals, score, earnings proximity, and a news headline."""
    tk = yf.Ticker(hit["ticker"])
    fund = fetch_fundamentals(tk)
    score, breakdown = dip_quality_score(hit, fund)
    hit.update(fund=fund, score=score, breakdown=breakdown,
               earnings=fetch_earnings_proximity(tk),
               news=fetch_top_news(tk))
    return hit


def _fmt(v, spec="{:.1f}", scale=1.0, suffix=""):
    return (spec.format(v * scale) + suffix) if isinstance(v, (int, float)) else "n/a"


def format_alert(h: dict) -> str:
    f, lines = h["fund"], []
    bd = h["breakdown"]
    lines.append(f"DIP SCORE {h['score']}/100 — {score_label(h['score'])} "
                 f"(tech {bd['technical']}/35 · quality {bd['quality']}/40 · value {bd['valuation']}/25)")

    trend = []
    if h["below_200dma"]:
        trend.append("below 200DMA")
    elif h["below_50dma"]:
        trend.append("below 50DMA")
    vol = f"vol {h['vol_ratio']:.1f}x" if h.get("vol_ratio") else ""
    lines.append(f"Technical: RSI {h['rsi']:.0f} | {abs(h['off_high']):.0f}% off 52w high | "
                 + " | ".join(x for x in [vol, *trend] if x))

    lines.append(f"Quality: ROE {_fmt(f.get('roe'), '{:.0f}', 100, '%')} | "
                 f"D/E {_fmt(f.get('de'), '{:.1f}', 0.01)} | "
                 f"FCF mgn {_fmt(f.get('fcf_margin'), '{:.0f}', 100, '%')} | "
                 f"Rev {_fmt(f.get('rev_growth'), '{:+.0f}', 100, '% YoY')}")

    lines.append(f"Value: P/E {_fmt(f.get('pe'), '{:.0f}')} (fwd {_fmt(f.get('fwd_pe'), '{:.0f}')}) | "
                 f"PEG {_fmt(f.get('peg'))} | "
                 f"Target ${_fmt(f.get('target'), '{:,.0f}')} "
                 f"({_fmt(f.get('upside'), '{:+.0f}', 1, '%')}) | "
                 f"Rating {_fmt(f.get('rec'))}")

    extras = []
    if isinstance(f.get("beta"), float):
        extras.append(f"beta {f['beta']:.1f}")
    if isinstance(f.get("short_pct"), float):
        extras.append(f"short int {f['short_pct'] * 100:.1f}%")
    if isinstance(f.get("div_yield"), float):
        dy = f["div_yield"] * 100 if f["div_yield"] < 1 else f["div_yield"]
        extras.append(f"div {dy:.1f}%")
    if extras:
        lines.append("Risk: " + " | ".join(extras))

    if h["earnings"]["warn"]:
        lines.append(f"⚠️ {h['earnings']['label']}")
    if h["news"]:
        lines.append(f"News: {h['news']}")
    lines.append("Triggers: " + "; ".join(h["signals"]))
    lines.append("\nReview WHY it dropped before buying.")
    return "\n".join(lines)


# ---------------------------------------------------------------- de-dupe

def should_alert(hit: dict, state: dict) -> bool:
    last = state.get(hit["ticker"])
    if not last:
        return True
    age = datetime.now(timezone.utc) - datetime.fromisoformat(last["time"])
    if age > timedelta(hours=ALERTS["realert_hours"]):
        return True
    extra_drop = (hit["price"] / last["price"] - 1) * 100
    return extra_drop <= -ALERTS["realert_extra_drop_pct"]


# ---------------------------------------------------------------- data

def download_watchlist() -> tuple[dict, float, list[str]]:
    tickers = list(dict.fromkeys(WATCHLIST))
    data = yf.download(tickers + [BENCHMARK], period="1y", interval="1d",
                       group_by="ticker", auto_adjust=True,
                       progress=False, threads=True)
    spy = data[BENCHMARK]["Close"].dropna()
    spy_change = float((spy.iloc[-1] / spy.iloc[-2] - 1) * 100)
    return data, spy_change, tickers


# ---------------------------------------------------------------- scan mode

def run_scan() -> None:
    data, spy_change, tickers = download_watchlist()
    print(f"{BENCHMARK} today: {spy_change:+.2f}%")

    state = _load(ALERT_STATE, {})
    history = _load(HISTORY, [])

    candidates = []
    for tk in tickers:
        try:
            hit = technical_screen(tk, data[tk], spy_change)
        except Exception as e:  # noqa: BLE001
            print(f"  {tk}: error ({e})")
            continue
        if not hit:
            print(f"  {tk}: ok")
        elif should_alert(hit, state):
            candidates.append(hit)
        else:
            print(f"  {tk}: dip, suppressed (recent alert)")

    if not candidates:
        print("No new candidates.")
        return

    print(f"Enriching {len(candidates)} candidate(s) with KPIs...")
    enriched = [enrich(h) for h in candidates]
    alerts = [h for h in enriched
              if h["panic"] or h["score"] >= SCORING["min_alert_score"]]
    alerts.sort(key=lambda h: -h["score"])
    skipped = [h["ticker"] for h in enriched if h not in alerts]
    if skipped:
        print(f"Below score floor, not pushed: {skipped}")

    now = datetime.now(timezone.utc).isoformat()
    for h in alerts[:ALERTS["max_alerts_per_run"]]:
        title = (f"📉 {h['ticker']} {h['today_chg']:+.1f}% → ${h['price']:,.2f} "
                 f"[{h['score']}/100]")
        prio = "high" if h["panic"] or h["score"] >= SCORING["strong"] else "default"
        if notify.send(title, format_alert(h), prio):
            state[h["ticker"]] = {"time": now, "price": h["price"]}
            history.append({"date": now[:10], "time": now, "ticker": h["ticker"],
                            "price": round(h["price"], 2), "score": h["score"],
                            "today_chg": round(h["today_chg"], 2)})
            print(f"Alerted {h['ticker']} (score {h['score']})")

    _save(ALERT_STATE, state)
    _save(HISTORY, history)


# ---------------------------------------------------------------- summary

def _forward_returns(history: list, data: dict) -> list[str]:
    """How did past alerts work out? 7d/30d forward returns + win rate."""
    out = []
    today = datetime.now(timezone.utc).date()
    for horizon in (7, 30):
        rets = []
        for h in history:
            alert_date = datetime.fromisoformat(h["time"]).date()
            if (today - alert_date).days < horizon:
                continue
            try:
                closes = data[h["ticker"]]["Close"].dropna()
                target_day = pd.Timestamp(alert_date) + pd.Timedelta(days=horizon)
                future = closes.loc[closes.index >= target_day]
                px = float(future.iloc[0]) if len(future) else float(closes.iloc[-1])
                rets.append((px / h["price"] - 1) * 100)
            except Exception:  # noqa: BLE001
                continue
        if rets:
            wins = sum(1 for r in rets if r > 0)
            out.append(f"  {horizon}d fwd: {sum(rets) / len(rets):+.1f}% avg, "
                       f"{wins}/{len(rets)} positive")
    return out


def run_summary() -> None:
    data, spy_change, tickers = download_watchlist()
    history = _load(HISTORY, [])
    today = datetime.now(timezone.utc).date().isoformat()

    rows = []
    for tk in tickers:
        try:
            closes = data[tk]["Close"].dropna()
            if len(closes) < 60:
                continue
            price = float(closes.iloc[-1])
            chg = (price / float(closes.iloc[-2]) - 1) * 100
            rows.append({"tk": tk, "chg": chg, "rsi": rsi(closes),
                         "off_high": (price / float(closes.max()) - 1) * 100})
        except Exception:  # noqa: BLE001
            continue
    rows.sort(key=lambda r: r["chg"])

    n = SUMMARY["top_movers"]
    lines = [f"SPY {spy_change:+.1f}%", ""]
    lines.append("Worst today:")
    lines += [f"  {r['tk']} {r['chg']:+.1f}% (RSI {r['rsi']:.0f})" for r in rows[:n]]
    lines.append("Best today:")
    lines += [f"  {r['tk']} {r['chg']:+.1f}%" for r in rows[-n:][::-1]]

    oversold = [r for r in rows if r["rsi"] <= SUMMARY["oversold_rsi"]]
    if oversold:
        lines.append("Oversold (watch closely):")
        lines += [f"  {r['tk']} RSI {r['rsi']:.0f}, {abs(r['off_high']):.0f}% off high"
                  for r in sorted(oversold, key=lambda r: r["rsi"])]

    near_high = sum(1 for r in rows if r["off_high"] >= -SUMMARY["near_high_pct"])
    lines.append(f"\n{near_high}/{len(rows)} names within "
                 f"{SUMMARY['near_high_pct']:.0f}% of 52w highs")

    todays = [h for h in history if h["date"] == today]
    lines.append(f"Alerts today: "
                 + (", ".join(f"{h['ticker']} [{h['score']}]" for h in todays)
                    if todays else "none"))

    perf = _forward_returns(history, data)
    if perf:
        lines.append(f"Alert track record ({len(history)} total):")
        lines += perf

    notify.send(f"📊 Daily watchlist summary — {today}", "\n".join(lines),
                "min", tags="bar_chart")
    print("Summary sent.")


# ---------------------------------------------------------------- main

if __name__ == "__main__":
    if "--test" in sys.argv:
        ok = notify.send("✅ Dip Monitor: test",
                         "ntfy is wired up correctly. You're ready to go.")
        sys.exit(0 if ok else 1)
    elif "--summary" in sys.argv:
        run_summary()
    else:
        run_scan()
