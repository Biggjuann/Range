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


if __name__ == "__main__":
    test_adr_basic()
    test_atr_includes_gaps()
    test_window_trim()
    print("\nAll range tests passed.")
