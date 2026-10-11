"""FastAPI app: serves the dashboard and exposes the range API."""
from __future__ import annotations

import logging
import os

from fastapi import FastAPI, Query
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from app.config import settings
from app.range_calc import compute
from app.schwab import SchwabClient, SchwabError

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
)

STATIC_DIR = os.path.join(os.path.dirname(__file__), "static")

app = FastAPI(title="Range — Average Daily Range")
schwab = SchwabClient()


@app.get("/")
def index() -> FileResponse:
    return FileResponse(os.path.join(STATIC_DIR, "index.html"))


@app.get("/api/range")
def range_api(
    symbol: str = Query(..., description="Ticker: AAPL, QQQ, /ES, $SPX, …"),
    days: int = Query(None, ge=1, le=2000, description="Trading days to average"),
) -> JSONResponse:
    days = days or settings.default_days
    sym = symbol.strip().upper()
    if not sym:
        return JSONResponse({"error": "symbol is required"}, status_code=400)
    try:
        # Fetch one extra prior session so the σ/return window yields a full
        # `days` daily returns (range metrics still use the last `days`).
        candles = schwab.daily_history(sym, days + 1)
    except SchwabError as exc:
        return JSONResponse({"error": str(exc), "symbol": sym}, status_code=502)
    if not candles:
        return JSONResponse(
            {"error": f"no completed sessions for '{sym}'", "symbol": sym},
            status_code=404,
        )
    return JSONResponse(compute(sym, candles, days))


@app.get("/api/config")
def config() -> dict:
    """Healthcheck + non-secret config echo."""
    return {
        "app": "range",
        "schwab_base_url": settings.schwab_base_url,
        "token_url": settings.token_url,
        "auth_mode": settings.schwab_auth_mode,
        "token_configured": bool(settings.token_share_key),
        "default_days": settings.default_days,
    }


app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")


def main() -> None:
    import uvicorn

    uvicorn.run("app.server:app", host=settings.host, port=settings.port, reload=False)


if __name__ == "__main__":
    main()
