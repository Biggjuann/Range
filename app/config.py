"""Runtime configuration, loaded from environment / .env.

The Schwab authorization is the *shared* token owned by the MM service
(https://github.com/Biggjuann/MM) — the same one the 0DTE app uses. We never
hold Schwab OAuth credentials here; instead we fetch a short-lived access token
over HTTP and present it to Schwab's market-data endpoints.
"""
from __future__ import annotations

import os
from dataclasses import dataclass, field

try:
    from dotenv import load_dotenv

    load_dotenv()
except Exception:  # pragma: no cover - dotenv optional
    pass


def _int(name: str, default: int) -> int:
    try:
        return int(float(os.getenv(name, default)))
    except (TypeError, ValueError):
        return default


@dataclass
class Settings:
    # ----- Schwab market-data API --------------------------------------------
    schwab_base_url: str = field(
        default_factory=lambda: os.getenv("SCHWAB_BASE_URL", "https://api.schwabapi.com")
    )

    # ----- Shared Schwab token (mirrors the MM / 0DTE services) --------------
    # "shared" pulls the access token over HTTP so this app shares MM's single
    # Schwab authorization for market data.
    schwab_auth_mode: str = field(
        default_factory=lambda: os.getenv("SCHWAB_AUTH_MODE", "shared").lower()
    )
    # Token endpoint. Leave blank to default to MM_BASE_URL + /auth/token.
    schwab_token_url: str = field(
        default_factory=lambda: os.getenv("SCHWAB_TOKEN_URL", "")
    )
    # Bearer key presented to the token endpoint (== MM's SCHWAB_TOKEN_SHARE_KEY).
    schwab_token_share_key: str = field(
        default_factory=lambda: os.getenv("SCHWAB_TOKEN_SHARE_KEY", "")
    )

    # MM service base (source of the shared token when SCHWAB_TOKEN_URL is blank).
    mm_base_url: str = field(
        default_factory=lambda: os.getenv(
            "MM_BASE_URL", "https://web-production-fff5c.up.railway.app"
        )
    )
    mm_api_key: str = field(default_factory=lambda: os.getenv("MM_API_KEY", ""))

    # ----- Default measurement window ----------------------------------------
    # Number of trading days averaged when the request omits it.
    default_days: int = field(default_factory=lambda: _int("RANGE_DEFAULT_DAYS", 20))

    # ----- Dashboard ---------------------------------------------------------
    host: str = field(default_factory=lambda: os.getenv("HOST", "0.0.0.0"))
    port: int = field(default_factory=lambda: _int("PORT", 8080))

    @property
    def token_url(self) -> str:
        """Resolved Schwab token endpoint (defaults to MM's /auth/token)."""
        return self.schwab_token_url or f"{self.mm_base_url.rstrip('/')}/auth/token"

    @property
    def token_share_key(self) -> str:
        """Bearer key for the shared token (SCHWAB_TOKEN_SHARE_KEY, MM_API_KEY fallback)."""
        return self.schwab_token_share_key or self.mm_api_key


settings = Settings()
