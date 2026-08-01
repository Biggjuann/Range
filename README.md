# Range — Average Daily Range

A tiny web app that measures the **average daily range** of any tradable
symbol — stock, ETF, index, or futures contract — using **Schwab market data**.

Enter a symbol, pick a window, and get its ADR/ATR in both dollars and percent,
a range-per-session chart, and the raw OHLC table.

It uses the **shared Schwab token** owned by the
[MM](https://github.com/Biggjuann/MM) service — the same single Schwab
authorization the [0DTE](https://github.com/Biggjuann/0DTE) app uses — so no
Schwab OAuth credentials live in this repo.

---

## What it measures

For the requested window of completed daily sessions:

| Metric | Definition |
|---|---|
| **ADR ($)** | mean of the daily range (`high − low`) |
| **ADR (%)** | mean of `(high − low) / close × 100` |
| **ATR ($)** | mean **True Range** = `max(high−low, \|high−prevClose\|, \|low−prevClose\|)` — captures gaps |
| **ATR (%)** | mean of `TR / prevClose × 100` |

It also surfaces the most recent session, the widest/narrowest sessions in the
window, and 5 / 10 / 20 / 60-day ADR windows for a quick trend read.

## Symbols

- **Stocks / ETFs**: `AAPL`, `QQQ`, `SPY`, `NVDA`
- **Indices**: leading `$` — `$SPX`, `$VIX`
- **Futures**: leading `/` — `/ES`, `/NQ`, `/CL`

Symbols are URL-encoded before hitting Schwab, so the `/` and `$` survive.

## API

```
GET /api/range?symbol=QQQ&days=20      -> full range report (JSON)
GET /api/config                        -> healthcheck + non-secret config
GET /                                  -> the dashboard
```

`days` defaults to `RANGE_DEFAULT_DAYS` (20) and is clamped to `1…2000`.

## Shared Schwab token

With `SCHWAB_AUTH_MODE=shared`, the app fetches a short-lived access token from
`SCHWAB_TOKEN_URL` (defaults to `MM_BASE_URL + /auth/token`) using
`SCHWAB_TOKEN_SHARE_KEY` as the bearer:

```
GET <token_url>   Authorization: Bearer <share_key>
-> { "access_token": "…", "expires_in": 1800 }
```

The token is cached until ~30 s before expiry and automatically re-fetched on a
Schwab `401` (the shared token rotated). This is the exact mechanism the 0DTE
app's `app/clients/token.py` uses.

## Architecture

```
app/
  config.py        env-driven settings (safe defaults)
  token.py         SharedTokenProvider — pulls MM's shared Schwab token
  schwab.py        SchwabClient — daily price history for any symbol
  range_calc.py    ADR / ATR / windows from daily candles
  server.py        FastAPI: dashboard + /api/range + /api/config
  static/index.html  self-contained dark dashboard (no CDNs)
tests/test_range.py  range-math tests (no network)
run.py             entrypoint: python run.py
```

## Run locally

```bash
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt

cp .env.example .env
# set SCHWAB_TOKEN_SHARE_KEY=<the shared key MM uses>

python run.py
# open http://localhost:8080

# tests (no network):
python tests/test_range.py
```

Without `SCHWAB_TOKEN_SHARE_KEY` set, the dashboard loads and `/api/range`
returns a clear error explaining the token is missing.

## Deploy to Railway

Configured via `railway.json` + `Procfile` (binds `0.0.0.0:$PORT`):

1. New Railway project → deploy this repo.
2. **Variables**: `SCHWAB_TOKEN_SHARE_KEY=…` (the same shared key MM uses);
   optionally `SCHWAB_TOKEN_URL`, `RANGE_DEFAULT_DAYS`.
3. Healthcheck is `/api/config`; the dashboard is the domain root `/`.

## Notes

- A still-forming candle for the current day is dropped, so ranges are always
  of **completed** sessions.
- Educational tooling; not investment advice.
