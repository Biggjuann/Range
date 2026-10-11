"""Range-math tests — no network. Run: python tests/test_range.py"""
import datetime as dt
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.range_calc import compute
from app.schwab import Candle


def _candle(day: int, o, h, l, c, v=1000):
    epoch_ms = int(dt.datetime(2024, 1, day, tzinfo=dt.timezone.utc).timestamp() * 1000)
    return Candle(epoch_ms, o, h, l, c, v)


def approx(a, b, tol=1e-6):
    return abs(a - b) <= tol


def test_adr_basic():
    # ranges: 2, 4, 6  -> ADR = 4
    candles = [
        _candle(1, 100, 101, 99, 100),   # range 2
        _candle(2, 100, 102, 98, 100),   # range 4
        _candle(3, 100, 103, 97, 100),   # range 6
    ]
    rep = compute("TEST", candles, 3)
    assert rep["sessions_used"] == 3, rep["sessions_used"]
    assert approx(rep["adr_dollars"], 4.0), rep["adr_dollars"]
    # ADR% = mean(2/100, 4/100, 6/100)*100 = 4.0
    assert approx(rep["adr_percent"], 4.0), rep["adr_percent"]
    assert rep["widest"]["range_dollars"] == 6.0
    assert rep["narrowest"]["range_dollars"] == 2.0
    print("test_adr_basic OK")


def test_atr_includes_gaps():
    # Day 2 gaps up: prev close 100, low 105 -> TR = max(H-L, |H-pc|, |L-pc|)
    candles = [
        _candle(1, 100, 101, 99, 100),          # TR = 2 (first)
        _candle(2, 106, 108, 105, 107),         # H-L=3, |108-100|=8, |105-100|=5 -> 8
    ]
    rep = compute("GAP", candles, 2)
    # ATR = mean(2, 8) = 5
    assert approx(rep["atr_dollars"], 5.0), rep["atr_dollars"]
    print("test_atr_includes_gaps OK")


def test_window_trim():
    candles = [_candle(d, 10, 10 + d, 10, 10 + d) for d in range(1, 11)]  # 10 sessions
    rep = compute("WIN", candles, 5)
    assert rep["sessions_used"] == 5, rep["sessions_used"]
    # only the last 5 sessions used
    assert rep["from_date"] == candles[5].date.isoformat()
    assert rep["windows"]["5"] is not None
    print("test_window_trim OK")


def test_sigma_moves():
    # Build closes with mostly tiny moves and a few deliberate large jumps so
    # the σ-exceedance counting is checkable.
    closes = [100.0]
    # 30 small alternating +/-0.1% moves
    for i in range(30):
        closes.append(closes[-1] * (1.001 if i % 2 == 0 else 0.999))
    # one big up day, one big down day
    closes.append(closes[-1] * 1.08)   # +8%
    closes.append(closes[-1] * 0.92)   # -8%
    candles = [
        _candle_seq(i, c) for i, c in enumerate(closes)
    ]
    rep = compute("SIG", candles, len(candles) - 1)
    sig = rep["sigma"]
    assert sig is not None, "sigma block missing"
    assert sig["return_count"] == len(closes) - 1, sig["return_count"]
    assert sig["daily_sigma_pct"] > 0
    # the two 8% moves must each be well beyond 2σ and show up as exceedances
    assert sig["buckets"]["2"]["up"] >= 1, sig["buckets"]["2"]
    assert sig["buckets"]["2"]["down"] >= 1, sig["buckets"]["2"]
    assert len(sig["two_sigma_days"]) >= 2, sig["two_sigma_days"]
    # normal expectation for ±2σ is ~4.55%
    assert abs(sig["buckets"]["2"]["expected_pct"] - 4.55) < 0.1, sig["buckets"]["2"]["expected_pct"]
    print("test_sigma_moves OK")


def _candle_seq(i, close):
    # a flat-ish OHLC around `close`; dates must be strictly increasing
    day = 1 + i
    base = dt.datetime(2024, 1, 1, tzinfo=dt.timezone.utc) + dt.timedelta(days=i)
    epoch_ms = int(base.timestamp() * 1000)
    return Candle(epoch_ms, close, close * 1.002, close * 0.998, close, 1000)


def _candle_ohlc(i, o, h, l, c):
    base = dt.datetime(2024, 1, 1, tzinfo=dt.timezone.utc) + dt.timedelta(days=i)
    return Candle(int(base.timestamp() * 1000), o, h, l, c, 1000)


def test_touched_not_exceeded():
    # Small, steady moves set a tiny σ (~0.1%). Then one "tag and fade" day:
    # intraday high spikes +2% above the prior close (≫ 2σ) but the close
    # finishes flat (inside the band) -> counts as tagged-but-not-exceeded up,
    # and NOT as an exceedance.
    closes = [100.0]
    for i in range(40):
        closes.append(closes[-1] * (1.001 if i % 2 == 0 else 0.999))
    candles = [_candle_seq(i, c) for i, c in enumerate(closes)]

    prior = closes[-1]
    # tag-and-fade up day: high = +2%, close ~ flat (+0.02%)
    tag_close = prior * 1.0002
    candles.append(_candle_ohlc(len(closes), prior, prior * 1.02, prior * 0.999, tag_close))

    rep = compute("TAG", candles, len(candles) - 1)
    b2 = rep["sigma"]["buckets"]["2"]
    held = b2["touched_not_exceeded"]
    # the tag day reached +2σ intraday but closed inside -> held, not exceeded
    assert held["up"] >= 1, held
    # and it must NOT be counted as a close-based exceedance
    assert b2["up"] == 0, b2
    assert held["total"] == held["up"] + held["down"], held
    print("test_touched_not_exceeded OK")


if __name__ == "__main__":
    test_adr_basic()
    test_atr_includes_gaps()
    test_window_trim()
    test_sigma_moves()
    test_touched_not_exceeded()
    print("\nAll range tests passed.")
