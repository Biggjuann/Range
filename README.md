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

### Sigma (σ) moves — distribution of daily returns

Beyond range, it characterises the distribution of daily close-to-close
returns over the window:

| Metric | Definition |
|---|---|
| **Daily σ** | standard deviation of daily % returns (the daily volatility) |
| **Annualized vol** | daily σ × √252 |
| **±1σ / ±2σ / ±3σ counts** | how often the **close** exceeded k·σ, split **up vs down** |
| **vs Normal** | each count against the 68/95/99.7 rule (~31.73% / ~4.55% / ~0.27% of days) |
| **Tagged, held** | how often the **intraday** high/low reached ±k·σ (from the prior close) but the close stayed inside the band — i.e. the level was touched but not exceeded, split up vs down |

For SPX/SPY over ~200 days this answers "how often does it exceed a 2σ move
up or down": the dashboard shows the count, the frequency, and how many times
the normal-distribution expectation (~4.55%, i.e. ~9 of 200 days) it ran —
markets' fat tails usually overshoot ±2σ and badly overshoot ±3σ. The ±2σ+
days are listed with their return and σ magnitude.

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

The range report includes a `sigma` block: `daily_sigma_pct`,
`annualized_vol_pct`, per-k `buckets` (`up` / `down` / `total` /
`pct_of_days` / `expected_pct` / `expected_count`, plus
`touched_not_exceeded` = `{up, down, total, pct_of_days}` for the days that
tagged ±kσ intraday but closed inside), and `two_sigma_days` (the ±2σ+
exceedance days). Example: `/api/range?symbol=SPY&days=200`.

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
