"""Environment-backed settings shared by the CLI and server."""

from __future__ import annotations

import os
from dataclasses import dataclass


def _env_bool(name: str, default: bool = False) -> bool:
    value = os.getenv(name)
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


@dataclass(frozen=True, slots=True)
class ClientSettings:
    base_url: str = "http://127.0.0.1:8000"
    api_key: str | None = None
    timeout: float = 30.0

    @classmethod
    def from_env(cls) -> ClientSettings:
        defaults = cls()
        return cls(
            base_url=os.getenv("QMTLINK_URL", defaults.base_url),
            api_key=os.getenv("QMTLINK_API_KEY") or None,
            timeout=float(os.getenv("QMTLINK_TIMEOUT", str(defaults.timeout))),
        )


@dataclass(frozen=True, slots=True)
class ServerSettings:
    host: str = "127.0.0.1"
    port: int = 8000
    mode: str = "real"
    api_key: str | None = None
    allow_live_orders: bool = False

    @classmethod
    def from_env(cls) -> ServerSettings:
        defaults = cls()
        return cls(
            host=os.getenv("QMTLINK_HOST", defaults.host),
            port=int(os.getenv("QMTLINK_PORT", str(defaults.port))),
            mode=os.getenv("QMTLINK_MODE", defaults.mode),
            api_key=os.getenv("QMTLINK_API_KEY") or None,
            allow_live_orders=_env_bool("QMTLINK_ALLOW_LIVE_ORDERS"),
        )
