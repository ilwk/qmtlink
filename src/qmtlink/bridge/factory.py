from __future__ import annotations

from qmtlink.errors import QMTLinkError

from .base import Bridge
from .mock import MockBridge
from .xtquant import XtQuantBridge


def create_bridge(mode: str) -> Bridge:
    normalized = mode.strip().lower()
    if normalized == "mock":
        return MockBridge()
    if normalized == "real":
        return XtQuantBridge()
    raise QMTLinkError("INVALID_MODE", f"unsupported bridge mode: {mode}")
