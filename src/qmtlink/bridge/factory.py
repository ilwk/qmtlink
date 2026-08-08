from __future__ import annotations

from qmtlink.config import ServerSettings
from qmtlink.errors import QMTLinkError

from .base import Bridge
from .mock import MockBridge
from .xtquant import XtQuantBridge


def create_bridge(settings: ServerSettings | str) -> Bridge:
    if isinstance(settings, str):
        settings = ServerSettings(mode=settings)
    normalized = settings.mode.strip().lower()
    if normalized == "mock":
        return MockBridge()
    if normalized == "real":
        return XtQuantBridge(settings)
    raise QMTLinkError("INVALID_MODE", f"unsupported bridge mode: {settings.mode}")
