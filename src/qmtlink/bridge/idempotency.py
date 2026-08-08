from __future__ import annotations

import hashlib
import json
import os
import sqlite3
import time
from pathlib import Path
from threading import RLock

from qmtlink.errors import QMTLinkError
from qmtlink.models import OrderRequest, OrderResult


def default_idempotency_path() -> Path:
    root = Path(os.getenv("XDG_CONFIG_HOME", Path.home() / ".config"))
    return root / "qmtlink" / "orders.sqlite3"


def order_fingerprint(order: OrderRequest) -> str:
    payload = {
        "symbol": order.symbol,
        "side": order.side,
        "quantity": order.quantity,
        "price": order.price,
        "order_type": order.order_type,
    }
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()
    return hashlib.sha256(encoded).hexdigest()


class IdempotencyStore:
    def __init__(self, path: str | Path = ":memory:") -> None:
        database = str(path)
        if database != ":memory:":
            resolved = Path(path).expanduser()
            resolved.parent.mkdir(parents=True, exist_ok=True)
            database = str(resolved)
        self._connection = sqlite3.connect(database, timeout=5, check_same_thread=False)
        self._lock = RLock()
        with self._connection:
            self._connection.execute(
                """
                CREATE TABLE IF NOT EXISTS order_idempotency (
                    client_order_id TEXT PRIMARY KEY,
                    fingerprint TEXT NOT NULL,
                    state TEXT NOT NULL,
                    order_id TEXT,
                    status TEXT,
                    submitted INTEGER,
                    updated_at REAL NOT NULL
                )
                """
            )

    def reserve(self, order: OrderRequest) -> OrderResult | None:
        fingerprint = order_fingerprint(order)
        now = time.time()
        with self._lock, self._connection:
            cursor = self._connection.execute(
                """
                INSERT OR IGNORE INTO order_idempotency
                    (client_order_id, fingerprint, state, updated_at)
                VALUES (?, ?, 'pending', ?)
                """,
                (order.client_order_id, fingerprint, now),
            )
            if cursor.rowcount == 1:
                return None
            row = self._connection.execute(
                """
                SELECT fingerprint, state, order_id, status, submitted
                FROM order_idempotency WHERE client_order_id = ?
                """,
                (order.client_order_id,),
            ).fetchone()

        if row is None:  # pragma: no cover - defensive against external database mutation
            raise QMTLinkError("IDEMPOTENCY_STORE_ERROR", "idempotency record disappeared")
        stored_fingerprint, state, order_id, status, submitted = row
        if stored_fingerprint != fingerprint:
            raise QMTLinkError(
                "IDEMPOTENCY_CONFLICT",
                "client_order_id was already used for a different order",
                status_code=409,
            )
        if state == "completed":
            return OrderResult(
                client_order_id=order.client_order_id,
                order_id=str(order_id),
                status=str(status),
                submitted=bool(submitted),
            )
        raise QMTLinkError(
            "ORDER_STATUS_UNCERTAIN",
            "this client_order_id has a pending or uncertain submission; "
            "query orders before retrying",
            status_code=409,
        )

    def complete(self, result: OrderResult) -> None:
        with self._lock, self._connection:
            self._connection.execute(
                """
                UPDATE order_idempotency
                SET state = 'completed', order_id = ?, status = ?, submitted = ?, updated_at = ?
                WHERE client_order_id = ?
                """,
                (
                    result.order_id,
                    result.status,
                    int(result.submitted),
                    time.time(),
                    result.client_order_id,
                ),
            )

    def mark_uncertain(self, client_order_id: str) -> None:
        with self._lock, self._connection:
            self._connection.execute(
                """
                UPDATE order_idempotency SET state = 'uncertain', updated_at = ?
                WHERE client_order_id = ?
                """,
                (time.time(), client_order_id),
            )

    def release(self, client_order_id: str) -> None:
        with self._lock, self._connection:
            self._connection.execute(
                "DELETE FROM order_idempotency WHERE client_order_id = ?",
                (client_order_id,),
            )

    def close(self) -> None:
        with self._lock:
            self._connection.close()
