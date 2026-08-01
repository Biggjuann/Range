"""Schwab market-data adapter — daily price history for any tradable symbol.

The OAuth access token is the *shared* token owned by the MM service; we pull
it through the SharedTokenProvider rather than holding Schwab credentials here.

Works for equities and ETFs (``AAPL``, ``QQQ``) and for futures, which Schwab
symbols with a leading slash (``/ES``, ``/NQ``, ``/CL``). Indices use a leading
``$`` (``$SPX``, ``$VIX``). Symbols are URL-encoded so the slash survives.
"""
from __future__ import annotations

import datetime as dt
import logging
from typing import List, Optional

import httpx

from app.config import settings
from app.token import SharedTokenProvider

log = logging.getLogger("schwab")


class Candle:
    __slots__ = ("date", "open", "high", "low", "close", "volume")

    def __init__(self, epoch_ms: int, o: float, h: float, l: float, c: float, v: float):
        self.date = dt.datetime.fromtimestamp(epoch_ms / 1000, tz=dt.timezone.utc).date()
        self.open = o
        self.high = h
        self.low = l
        self.close = c
        self.volume = v

    def as_dict(self) -> dict:
        return {
            "date": self.date.isoformat(),
            "open": self.open,
            "high": self.high,
            "low": self.low,
            "close": self.close,
            "volume": self.volume,
        }


class SchwabError(RuntimeError):
    """Raised with a human-readable reason when a market-data call fails."""


class SchwabClient:
    def __init__(self, timeout: float = 12.0):
        self.base = settings.schwab_base_url.rstrip("/")
        self.tokens = SharedTokenProvider()
        self.client = httpx.Client(timeout=timeout)

    def _headers(self) -> dict:
        tok = self.tokens.get_token()
        if not tok:
            raise SchwabError(
                "no shared Schwab token — set SCHWAB_TOKEN_SHARE_KEY "
                "(and SCHWAB_TOKEN_URL / MM_BASE_URL)"
            )
        return {"Authorization": f"Bearer {tok}", "Accept": "application/json"}

    def _get(self, path: str, params: Optional[dict] = None) -> httpx.Response:
        """GET with one automatic retry: on 401 the shared token has rotated,
        so invalidate the cache, re-fetch, and try again."""
        url = f"{self.base}{path}"
        last: Optional[httpx.Response] = None
        for attempt in (0, 1):
            r = self.client.get(url, headers=self._headers(), params=params)
            if r.status_code == 401 and attempt == 0:
                log.warning("schwab 401 — refreshing shared token and retrying")
                self.tokens.invalidate()
                continue
            last = r
            break
        return last

    def daily_history(self, symbol: str, days: int) -> List[Candle]:
        """Return up to the last ``days`` completed daily candles for ``symbol``.

        We pull a generous window (so weekends/holidays don't starve the count)
        and trim to the most recent completed sessions.
        """
        symbol = symbol.strip().upper()
        if not symbol:
            raise SchwabError("empty symbol")

        # Ask for enough calendar span to cover `days` trading sessions plus slack.
        # ~252 trading days per year; add headroom for holidays/weekends.
        need = max(days, 1)
        years = max(1, (need // 240) + 1)

        r = self._get(
            "/marketdata/v1/pricehistory",
            params={
                "symbol": symbol,
                "periodType": "year",
                "period": years,
                "frequencyType": "daily",
                "frequency": 1,
                "needExtendedHoursData": "false",
            },
        )
        if r is None:
            raise SchwabError("no response from Schwab")
        if r.status_code == 404:
            raise SchwabError(f"symbol '{symbol}' not found")
        if r.status_code != 200:
            snippet = (r.text or "")[:200]
            raise SchwabError(f"Schwab HTTP {r.status_code}: {snippet}")

        try:
            body = r.json()
        except Exception as exc:  # pragma: no cover - network
            raise SchwabError(f"bad JSON from Schwab: {exc}")

        if body.get("empty") or not body.get("candles"):
            raise SchwabError(f"no price history for '{symbol}'")

        candles = [
            Candle(
                int(c["datetime"]),
                float(c["open"]),
                float(c["high"]),
                float(c["low"]),
                float(c["close"]),
                float(c.get("volume") or 0),
            )
            for c in body["candles"]
            if c.get("high") is not None and c.get("low") is not None
        ]
        candles.sort(key=lambda c: c.date)

        # Drop a possibly-forming candle for the current day so ranges are of
        # completed sessions only.
        today = dt.datetime.now(tz=dt.timezone.utc).date()
        completed = [c for c in candles if c.date < today] or candles

        return completed[-need:]
