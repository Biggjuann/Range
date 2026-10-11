"""Average-daily-range statistics from a series of daily candles.

Definitions (all computed over the supplied completed sessions):

* **Daily range**    high - low  for a session.
* **ADR ($)**        mean of the daily ranges.
* **ADR (%)**        mean of (range / close * 100) — the range as a share of
                     that day's close.
* **ATR ($)**        mean True Range, where
                     TR = max(high-low, |high-prevClose|, |low-prevClose|).
                     ATR captures gaps that a plain high-low misses.
* **ATR (%)**        mean of (TR / prevClose * 100).

We also surface the most-recent session, the widest/narrowest sessions in the
window, and multi-window ADRs (5 / 10 / 20 / 60 day) for quick comparison.

Sigma (σ) moves
---------------
Beyond range, we characterise the *distribution of daily close-to-close
returns* over the window: their standard deviation (σ, the daily volatility),
and how often the actual move exceeded ±1σ / ±2σ / ±3σ — split into up and
down days. Each count is compared against the Normal-distribution expectation
(68/95/99.7 rule: ~31.73% of days beyond ±1σ, ~4.55% beyond ±2σ, ~0.27%
beyond ±3σ). Fat-tailed markets routinely exceed the ±2σ/±3σ expectation.
"""
from __future__ import annotations

import math
from typing import Dict, List, Optional

from app.schwab import Candle

# Normal-distribution share of observations beyond ±kσ (two-tailed), as a %.
# P(|Z| > k) = erfc(k / sqrt(2)).
NORMAL_BEYOND = {
    1: math.erfc(1 / math.sqrt(2)) * 100,  # 31.73%
    2: math.erfc(2 / math.sqrt(2)) * 100,  # 4.55%
    3: math.erfc(3 / math.sqrt(2)) * 100,  # 0.27%
}


def _mean(xs: List[float]) -> Optional[float]:
    return sum(xs) / len(xs) if xs else None


def _stdev(xs: List[float]) -> Optional[float]:
    """Sample standard deviation (ddof=1)."""
    if len(xs) < 2:
        return None
    m = sum(xs) / len(xs)
    var = sum((x - m) ** 2 for x in xs) / (len(xs) - 1)
    return math.sqrt(var)


def _sigma_stats(candles: List[Candle]) -> Optional[Dict]:
    """Distribution of daily close-to-close % returns + σ-exceedance counts.

    ``candles`` is the return window (oldest -> newest); it yields len-1
    returns. Thresholds are a multiple of the window's own return σ.
    """
    rets: List[Dict] = []
    for i in range(1, len(candles)):
        prev, cur = candles[i - 1], candles[i]
        if not prev.close:
            continue
        pc = prev.close
        rets.append({
            "date": cur.date.isoformat(),
            "ret": (cur.close - pc) / pc * 100,       # close-to-close %
            "hi": (cur.high - pc) / pc * 100,         # intraday high move vs prior close
            "lo": (cur.low - pc) / pc * 100,          # intraday low move vs prior close
        })
    vals = [r["ret"] for r in rets]
    sd = _stdev(vals)
    if sd is None or sd == 0:
        return None
    mean = _mean(vals) or 0.0
    n = len(vals)

    def bucket(k: int) -> Dict:
        thr = k * sd
        up = [r for r in rets if r["ret"] > thr]
        down = [r for r in rets if r["ret"] < -thr]
        total = len(up) + len(down)
        # "Touched but didn't exceed": the intraday high/low reached the ±kσ
        # level (measured from the prior close) but the close stayed within it.
        touch_up = [r for r in rets if r["hi"] >= thr and r["ret"] <= thr]
        touch_down = [r for r in rets if r["lo"] <= -thr and r["ret"] >= -thr]
        touched_held = len(touch_up) + len(touch_down)
        exp_pct = NORMAL_BEYOND[k]
        return {
            "k": k,
            "threshold_pct": _round(thr, 3),
            "up": len(up),
            "down": len(down),
            "total": total,
            "pct_of_days": _round(total / n * 100, 2),
            "expected_pct": _round(exp_pct, 2),
            "expected_count": _round(exp_pct / 100 * n, 1),
            # touched the level intraday but closed back inside
            "touched_not_exceeded": {
                "up": len(touch_up),
                "down": len(touch_down),
                "total": touched_held,
                "pct_of_days": _round(touched_held / n * 100, 2),
            },
        }

    # The ±2σ+ exceedance days, most recent first (chronological order).
    two_sd = sorted(
        (r for r in rets if abs(r["ret"]) > 2 * sd),
        key=lambda r: r["date"],
        reverse=True,
    )

    return {
        "return_count": n,
        "daily_sigma_pct": _round(sd, 3),
        "mean_daily_return_pct": _round(mean, 4),
        "annualized_vol_pct": _round(sd * math.sqrt(252), 2),
        "buckets": {str(k): bucket(k) for k in (1, 2, 3)},
        "two_sigma_days": [
            {"date": r["date"], "return_pct": _round(r["ret"], 2),
             "sigmas": _round(r["ret"] / sd, 2)}
            for r in two_sd
        ],
    }


def _round(x: Optional[float], nd: int = 4) -> Optional[float]:
    return round(x, nd) if x is not None else None


def _adr_dollars(candles: List[Candle]) -> Optional[float]:
    return _mean([c.high - c.low for c in candles])


def _adr_percent(candles: List[Candle]) -> Optional[float]:
    return _mean([(c.high - c.low) / c.close * 100 for c in candles if c.close])


def _true_ranges(candles: List[Candle]) -> List[float]:
    trs: List[float] = []
    prev: Optional[Candle] = None
    for c in candles:
        if prev is None:
            trs.append(c.high - c.low)
        else:
            trs.append(
                max(
                    c.high - c.low,
                    abs(c.high - prev.close),
                    abs(c.low - prev.close),
                )
            )
        prev = c
    return trs


def compute(symbol: str, candles: List[Candle], days: int) -> Dict:
    """Build the full range report for the requested window of candles.

    Range metrics use the last ``days`` sessions. Return/σ metrics use one
    extra prior session (``days + 1`` closes) so the window yields a full
    ``days`` daily returns.
    """
    window = candles[-days:] if days else candles
    ret_window = candles[-(days + 1):] if days else candles
    n = len(window)

    ranges = [c.high - c.low for c in window]
    trs = _true_ranges(window)
    atr_pcts = [
        tr / window[i - 1].close * 100
        for i, tr in enumerate(trs)
        if i > 0 and window[i - 1].close
    ]

    widest = max(window, key=lambda c: c.high - c.low) if window else None
    narrowest = min(window, key=lambda c: c.high - c.low) if window else None
    last = window[-1] if window else None

    def window_adr(k: int) -> Optional[float]:
        return _round(_adr_dollars(window[-k:]), 4) if n >= 1 else None

    return {
        "symbol": symbol.upper(),
        "requested_days": days,
        "sessions_used": n,
        "from_date": window[0].date.isoformat() if window else None,
        "to_date": window[-1].date.isoformat() if window else None,
        "adr_dollars": _round(_adr_dollars(window)),
        "adr_percent": _round(_adr_percent(window)),
        "atr_dollars": _round(_mean(trs)),
        "atr_percent": _round(_mean(atr_pcts)),
        "last_session": {
            "date": last.date.isoformat(),
            "range_dollars": _round(last.high - last.low),
            "range_percent": _round((last.high - last.low) / last.close * 100)
            if last.close
            else None,
            "close": last.close,
        }
        if last
        else None,
        "widest": {
            "date": widest.date.isoformat(),
            "range_dollars": _round(widest.high - widest.low),
        }
        if widest
        else None,
        "narrowest": {
            "date": narrowest.date.isoformat(),
            "range_dollars": _round(narrowest.high - narrowest.low),
        }
        if narrowest
        else None,
        "windows": {
            "5": window_adr(5),
            "10": window_adr(10),
            "20": window_adr(20),
            "60": window_adr(60),
        },
        "sigma": _sigma_stats(ret_window),
        # Recent sessions (oldest -> newest) for the sparkline / table.
        "sessions": [
            {**c.as_dict(), "range": _round(c.high - c.low)} for c in window
        ],
    }
