from __future__ import annotations

from typing import Protocol

from qmtlink.models import OrderPreview, OrderRequest, OrderResult, Quote


class Bridge(Protocol):
    mode: str

    def health(self) -> dict[str, object]: ...

    def capabilities(self) -> dict[str, object]: ...

    def get_quotes(self, symbols: list[str]) -> list[Quote]: ...

    def preview_order(self, order: OrderRequest) -> OrderPreview: ...

    def place_order(self, order: OrderRequest) -> OrderResult: ...
