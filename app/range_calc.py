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
"""
from __future__ import annotations

from typing import Dict, List, Optional

from app.schwab import Candle


def _mean(xs: List[float]) -> Optional[float]:
    return sum(xs) / len(xs) if xs else None


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
    """Build the full range report for the requested window of candles."""
    window = candles[-days:] if days else candles
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
        # Recent sessions (oldest -> newest) for the sparkline / table.
        "sessions": [
            {**c.as_dict(), "range": _round(c.high - c.low)} for c in window
        ],
    }
