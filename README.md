# Stock Dip Monitor v2 (100% free)

A two-stage scanner modeled on how a desk analyst triages a falling stock:
a cheap **technical screen** runs on every watchlist name every 30 minutes,
and anything that trips becomes a **candidate** that gets enriched with
fundamental KPIs, scored 0–100, and pushed to your phone — for free.

**Cost: $0.** Yahoo Finance data + GitHub Actions compute + ntfy.sh push.

> ⚠️ Notify-only. It never places trades (Robinhood has no official retail
> API). A drop alone isn't a buy signal — the alert includes a news headline
> and earnings warning precisely so you check *why* it fell. Not financial advice.

---

## What an alert looks like

```
📉 NVDA -6.2% → $112.40 [78/100]
DIP SCORE 78/100 — STRONG (tech 27/35 · quality 36/40 · value 15/25)
Technical: RSI 27 | 24% off 52w high | vol 3.1x | below 50DMA
Quality: ROE 45% | D/E 0.4 | FCF mgn 32% | Rev +22% YoY
Value: P/E 28 (fwd 24) | PEG 1.1 | Target $145 (+29%) | Rating 1.8
Risk: beta 1.7 | short int 1.2% | div 0.1%
⚠️ Earnings in 4d (2026-06-15)
News: Nvidia falls after report of new export restrictions...
Triggers: Down 6.2% today; 5.1% worse than SPY; RSI 27; Volume 3.1x avg
```

## The KPI stack

**Stage 1 — Technical screen** (all tickers, every run):
today's % drop · drop relative to SPY (company-specific vs market-wide) ·
distance below 52-week high · RSI(14) · volume vs 20-day average ·
position vs 50/200-day moving averages.

**Stage 2 — Dip Quality Score** (candidates only):

| Pillar | Max | KPIs |
|---|---|---|
| Technical severity | 35 | drop size, % off high, RSI, volume spike |
| Business quality | 40 | ROE, debt/equity, FCF margin, revenue growth, profit margin |
| Valuation & street | 25 | analyst target upside, forward vs trailing P/E, PEG, consensus rating |

Labels: **STRONG** ≥ 70 (high-priority push) · **SOLID** ≥ 55 · **SPECULATIVE** below.
Candidates scoring under `min_alert_score` (default 40) are logged but not pushed —
that's the value-trap filter: a big drop in a weak business stays quiet.

**Risk context on every alert:** beta, short interest, dividend yield,
earnings-date proximity (warns within ±7 days), and the latest news headline.

## Daily summary (4:15pm ET push)

Worst/best movers · oversold names (RSI ≤ 35) · how many names sit near
52-week highs · alerts fired today · and an **alert track record**: average
7-day and 30-day forward returns of all past alerts, with win rate — so you
can see whether your thresholds actually have an edge and tune `config.py`.

---

## Setup (15 minutes)

1. **ntfy.sh (free push):** install the ntfy app, subscribe to a long private
   topic name (e.g. `yourname-dips-x9k2m7q4`). Treat it like a password --
   never commit it to git or share it; anyone with it can read your alerts
   or push fake ones to your phone.
2. **GitHub:** create a **private** repo, upload these files (keep the
   `.github/workflows/` structure). Settings → Secrets → Actions →
   new secret `NTFY_TOPIC` = your topic name.
3. **Test:** Actions tab → "Stock Dip Monitor" → Run workflow. To force a
   notification end-to-end, temporarily set `today_drop_pct: 0.5` and
   `min_signals: 1` and `min_alert_score: 0` in `config.py`, run, then revert.

Local testing:
```bash
pip install -r requirements.txt
NTFY_TOPIC=your-topic python monitor.py --test      # test push
NTFY_TOPIC=your-topic python monitor.py             # intraday scan
NTFY_TOPIC=your-topic python monitor.py --summary   # daily summary
```

> If your machine intercepts HTTPS traffic for SSL scanning (e.g. Norton),
> `yfinance` and the ntfy push may fail with certificate errors. Use
> `run_local.py` instead -- it works around this via a custom CA bundle and
> `truststore`. See `requirements-local.txt` for its extra dependency
> (`pip install -r requirements-local.txt`), then set `NTFY_TOPIC` and
> `CA_BUNDLE` (path to a CA bundle file containing certifi's certs plus
> your intercepting AV's exported root cert) as environment variables --
> do not hardcode them in the script -- then run e.g.
> `python run_local.py --test`.

## Files

| File | Purpose |
|---|---|
| `config.py` | Watchlist, thresholds, scoring floor (edit this) |
| `monitor.py` | Pipeline: screen → enrich → score → alert / summary |
| `kpis.py` | Fundamentals, earnings proximity, news, scoring model |
| `notify.py` | ntfy.sh push |
| `.github/workflows/monitor.yml` | Intraday scans every 30 min, market hours |
| `.github/workflows/daily-summary.yml` | End-of-day summary push |
| `state/` | Alert de-dupe + history (auto-committed by the workflow) |
