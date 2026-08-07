from __future__ import annotations

import json
import sys
from typing import Any

from pydantic import BaseModel


def _jsonable(value: Any) -> Any:
    if isinstance(value, BaseModel):
        return value.model_dump(mode="json")
    if isinstance(value, list):
        return [_jsonable(item) for item in value]
    if isinstance(value, dict):
        return {key: _jsonable(item) for key, item in value.items()}
    return value


def emit(data: Any, *, ok: bool = True, pretty: bool = False) -> None:
    payload = {"ok": ok, "data": _jsonable(data)} if ok else {"ok": False, "error": data}
    json.dump(payload, sys.stdout, ensure_ascii=False, indent=2 if pretty else None)
    sys.stdout.write("\n")
