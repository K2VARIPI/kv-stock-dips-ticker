# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project overview

Stock Dip Monitor v2 — a free, two-stage scanner that screens a watchlist for
deep/oversold dips, enriches candidates with fundamentals into a 0-100 "Dip
Quality Score", and pushes alerts to a phone via ntfy.sh. Runs on GitHub
Actions (no servers, no cost). Notify-only — never places trades.

## Commands

```bash
pip install -r requirements.txt

NTFY_TOPIC=your-topic python monitor.py --test      # send a test push
NTFY_TOPIC=your-topic python monitor.py             # intraday scan
NTFY_TOPIC=your-topic python monitor.py --summary   # daily summary

python screen_watchlist.py --dry-run                # preview monthly watchlist refresh
```

No test suite or linter is configured.

### Local Windows note

If something intercepts HTTPS for SSL scanning (e.g. Norton), `yfinance` and
ntfy pushes fail with certificate errors. Use `run_local.py` instead of
`monitor.py` directly — it injects the Windows certificate store via
`truststore` and sets `CURL_CA_BUNDLE`. Requires `pip install -r
requirements-local.txt` and the `NTFY_TOPIC` + `CA_BUNDLE` env vars (never
hardcode these).

## Architecture

### Pipeline (`monitor.py`)

Two-stage pipeline modeled on a desk analyst's triage:

1. **Stage 1 — `technical_screen()`** runs on every `WATCHLIST` ticker
   (from `config.py`) every scan: today's % drop, drop vs `SPY`, distance
   below 52-week high, RSI(14), volume vs 20-day average, position vs
   50/200-day moving averages. A ticker becomes a *candidate* if
   `TECHNICAL["min_signals"]` fire, or immediately on a `panic_drop_pct`
   single-day drop.
2. **De-dupe — `should_alert()`** suppresses re-alerting the same ticker
   within `ALERTS["realert_hours"]` unless it has fallen an additional
   `realert_extra_drop_pct`. State lives in `state/alerts.json`.
3. **Stage 2 — `enrich()`** (candidates only, via `kpis.py`):
   fundamentals (ROE, D/E, FCF margin, revenue growth, profit margin, P/E,
   forward P/E, PEG, analyst target/rating, beta, short interest, dividend
   yield), earnings-date proximity warning, and a recent news headline (the
   "why"). `dip_quality_score()` blends these into 0-100 across three
   pillars: technical severity (35), business quality (40), valuation/street
   (25) — see `score_label()` for STRONG/SOLID/SPECULATIVE thresholds.
4. **Alerting** — only candidates that are `panic` or score ≥
   `SCORING["min_alert_score"]` are pushed (value-trap filter), sorted by
   score, capped at `ALERTS["max_alerts_per_run"]`, sent via `notify.send()`
   (ntfy.sh). Sent alerts are recorded in `state/alerts.json` (for de-dupe)
   and appended to `state/history.json` (for performance tracking).
5. **Daily summary — `run_summary()`** (`--summary`): worst/best movers,
   oversold names (RSI ≤ threshold), count near 52-week highs, today's
   alerts, and `_forward_returns()` — 7d/30d forward returns + win rate of
   past alerts from `state/history.json`, to validate whether the configured
   thresholds have an edge.

### Configuration (`config.py`)

All tunables live here: `WATCHLIST`, `BENCHMARK`, `TECHNICAL`, `SCORING`,
`RISK`, `ALERTS`, `SUMMARY`. The `WATCHLIST` block between the
`# --- AUTO-WATCHLIST:BEGIN/END ---` markers is rewritten automatically by
`screen_watchlist.py` — manual edits become the new baseline for the next
diff.

### Watchlist refresh (`screen_watchlist.py`)

Run monthly. Re-screens `universe.csv` (broad large-cap universe) against
hard filters (`MIN_ROE`, `MIN_MARGIN`, `MAX_DEBT_TO_EQUITY`, `MIN_MARKET_CAP`)
and scores survivors on quality/performance/stability (0-100, reusing
`kpis._pts`). Rewrites the `WATCHLIST` block in `config.py` with the top
`TOP_N` and writes `watchlist_diff.md` describing additions/removals. Never
commits directly — only proposes via PR.

### GitHub Actions workflows (`.github/workflows/`)

- `monitor.yml` — intraday scan every 30 min during market hours; commits
  `state/` back to the repo; pushes an ntfy failure alert on error.
- `daily-summary.yml` — runs `monitor.py --summary` at ~4:15pm ET.
- `watchlist-refresh.yml` — monthly; runs `screen_watchlist.py` and opens a
  PR via `peter-evans/create-pull-request` if the watchlist changed.

All three need the `NTFY_TOPIC` repo secret. `monitor.yml` and
`daily-summary.yml` need `contents: write`; `watchlist-refresh.yml` also
needs `pull-requests: write`.

## Secrets

`NTFY_TOPIC` (and locally, `CA_BUNDLE`) must never be hardcoded or committed —
read from environment/GitHub Actions secrets only. Treat the ntfy topic name
like a password: anyone with it can read alerts or push fake ones.
