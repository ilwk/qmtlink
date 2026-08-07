"""Public Python SDK for QmtLink."""

from importlib.metadata import PackageNotFoundError, version

from .client import QMTClient
from .models import OrderRequest, OrderSide, OrderType

try:
    __version__ = version("qmtlink")
except PackageNotFoundError:  # pragma: no cover - source tree without installation
    __version__ = "0.0.0"

__all__ = ["QMTClient", "OrderRequest", "OrderSide", "OrderType", "__version__"]
