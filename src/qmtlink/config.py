"""TOML and environment-backed settings shared by the CLI and server."""

from __future__ import annotations

import os
import secrets
import tomllib
from dataclasses import dataclass
from importlib.resources import files
from pathlib import Path
from typing import Any

from qmtlink.errors import QMTLinkError


def default_config_path() -> Path:
    root = Path(os.getenv("XDG_CONFIG_HOME", Path.home() / ".config"))
    return root / "qmtlink" / "config.toml"


def resolve_config_path(path: str | Path | None = None) -> Path:
    configured = path or os.getenv("QMTLINK_CONFIG")
    return Path(configured).expanduser() if configured else default_config_path()


def load_config(path: str | Path | None = None) -> tuple[Path, dict[str, Any]]:
    target = resolve_config_path(path)
    if not target.is_file():
        return target, {}
    try:
        with target.open("rb") as file:
            data = tomllib.load(file)
    except (OSError, tomllib.TOMLDecodeError) as exc:
        raise QMTLinkError(
            "INVALID_CONFIG",
            f"cannot read config {target}: {exc}",
            status_code=400,
        ) from exc
    return target, data


def create_default_config(path: str | Path | None = None) -> tuple[Path, bool]:
    target = resolve_config_path(path)
    if target.exists():
        return target, False
    api_key = secrets.token_urlsafe(32)
    template = files("qmtlink").joinpath("config.template.toml").read_text(encoding="utf-8")
    content = template.replace("{{API_KEY}}", api_key)
    try:
        target.parent.mkdir(parents=True, exist_ok=True)
        with target.open("x", encoding="utf-8", newline="\n") as file:
            file.write(content)
        try:
            target.chmod(0o600)
        except OSError:
            pass
    except FileExistsError:
        return target, False
    except OSError as exc:
        raise QMTLinkError(
            "CONFIG_CREATE_FAILED",
            f"cannot create config {target}: {exc}",
            status_code=500,
        ) from exc
    return target, True


def _env_bool(name: str, default: bool = False) -> bool:
    value = os.getenv(name)
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


def _config_section(data: dict[str, Any], name: str) -> dict[str, Any]:
    value = data.get(name, {})
    if not isinstance(value, dict):
        raise QMTLinkError(
            "INVALID_CONFIG",
            f"config section [{name}] must be a table",
            status_code=400,
        )
    return value


def _config_bool(data: dict[str, Any], name: str, default: bool) -> bool:
    value = data.get(name, default)
    if not isinstance(value, bool):
        raise QMTLinkError(
            "INVALID_CONFIG",
            f"config field {name} must be true or false",
            status_code=400,
        )
    return value


@dataclass(frozen=True, slots=True)
class ClientSettings:
    base_url: str = "http://127.0.0.1:8000"
    api_key: str | None = None
    timeout: float = 30.0

    @classmethod
    def from_env(cls, config_path: str | Path | None = None) -> ClientSettings:
        defaults = cls()
        _, data = load_config(config_path)
        server = _config_section(data, "server")
        client = _config_section(data, "client")
        bridge_host = str(server.get("host", "0.0.0.0"))
        if bridge_host in {"0.0.0.0", "::"}:
            bridge_host = "127.0.0.1"
        derived_url = f"http://{bridge_host}:{int(server.get('port', 8000))}"
        return cls(
            base_url=os.getenv("QMTLINK_URL", str(client.get("url", derived_url))),
            api_key=(os.getenv("QMTLINK_API_KEY") or data.get("api_key") or None),
            timeout=float(
                os.getenv("QMTLINK_TIMEOUT", str(client.get("timeout", defaults.timeout)))
            ),
        )


@dataclass(frozen=True, slots=True)
class ServerSettings:
    host: str = "0.0.0.0"
    port: int = 8000
    mode: str = "real"
    api_key: str | None = None
    allow_trading: bool = False
    qmt_path: str | None = None
    account_id: str | None = None
    account_type: str = "STOCK"
    strategy_name: str = "qmtlink"

    @classmethod
    def from_env(cls, config_path: str | Path | None = None) -> ServerSettings:
        defaults = cls()
        _, data = load_config(config_path)
        server = _config_section(data, "server")
        configured_allow_trading = _config_bool(
            server, "allow_trading", defaults.allow_trading
        )
        return cls(
            host=os.getenv("QMTLINK_HOST", str(server.get("host", defaults.host))),
            port=int(os.getenv("QMTLINK_PORT", str(server.get("port", defaults.port)))),
            mode=defaults.mode,
            api_key=(os.getenv("QMTLINK_API_KEY") or data.get("api_key") or None),
            allow_trading=_env_bool("QMTLINK_ALLOW_TRADING", configured_allow_trading),
            qmt_path=os.getenv("QMTLINK_QMT_PATH") or server.get("qmt_path") or None,
            account_id=(os.getenv("QMTLINK_ACCOUNT_ID") or server.get("account_id") or None),
            account_type=os.getenv(
                "QMTLINK_ACCOUNT_TYPE", str(server.get("account_type", defaults.account_type))
            ).upper(),
            strategy_name=os.getenv(
                "QMTLINK_STRATEGY_NAME",
                str(server.get("strategy_name", defaults.strategy_name)),
            ),
        )
