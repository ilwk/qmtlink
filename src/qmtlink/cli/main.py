from __future__ import annotations

import importlib.util
import platform
import shutil
import subprocess
import sys
from typing import Annotated

import typer

from qmtlink.client import QMTClient
from qmtlink.config import (
    ClientSettings,
    ServerSettings,
    create_default_config,
    resolve_config_path,
)
from qmtlink.errors import QMTLinkError
from qmtlink.models import OrderRequest, OrderSide, OrderType

from .output import emit

app = typer.Typer(help="CLI, SDK, and bridge for miniQMT/xtquant", no_args_is_help=True)
bridge_app = typer.Typer(help="Manage the local Windows Bridge", no_args_is_help=True)
market_app = typer.Typer(help="Query market data", no_args_is_help=True)
order_app = typer.Typer(help="Preview and submit orders", no_args_is_help=True)
account_app = typer.Typer(help="Query account state", no_args_is_help=True)
app.add_typer(bridge_app, name="bridge")
app.add_typer(market_app, name="market")
app.add_typer(account_app, name="account")
app.add_typer(order_app, name="order")


def _client() -> QMTClient:
    settings = ClientSettings.from_env()
    return QMTClient(settings.base_url, api_key=settings.api_key, timeout=settings.timeout)


def _handle_error(exc: Exception) -> None:
    if isinstance(exc, QMTLinkError):
        emit(exc.as_dict(), ok=False)
        raise typer.Exit(code=4 if exc.retryable else 5)
    emit({"code": type(exc).__name__.upper(), "message": str(exc), "retryable": False}, ok=False)
    raise typer.Exit(code=1)


@bridge_app.command("doctor")
def bridge_doctor(pretty: bool = typer.Option(False, "--pretty")) -> None:
    try:
        config_path = resolve_config_path()
        xtquant_available = importlib.util.find_spec("xtquant") is not None
        server_dependencies = all(
            importlib.util.find_spec(package) is not None for package in ("fastapi", "uvicorn")
        )
        python_supported = (3, 11) <= sys.version_info[:2] < (3, 14)
        settings = ServerSettings.from_env()
        qmt_configured = bool(settings.qmt_path and settings.account_id)
        emit(
            {
                "config_path": str(config_path),
                "config_exists": config_path.is_file(),
                "platform": platform.system().lower(),
                "python": platform.python_version(),
                "python_supported_for_real": python_supported,
                "server_dependencies_installed": server_dependencies,
                "xtquant_importable": xtquant_available,
                "api_key_configured": bool(settings.api_key),
                "qmt_path_configured": bool(settings.qmt_path),
                "account_configured": bool(settings.account_id),
                "ready_for_mock": server_dependencies,
                "ready_for_real": (
                    sys.platform == "win32"
                    and python_supported
                    and server_dependencies
                    and xtquant_available
                    and qmt_configured
                ),
            },
            pretty=pretty,
        )
    except Exception as exc:
        _handle_error(exc)


@bridge_app.command("run")
def bridge_run(
    mock: bool = typer.Option(False, "--mock", help="Run without miniQMT"),
    host: str | None = typer.Option(None, "--host"),
    port: int | None = typer.Option(None, "--port", min=1, max=65535),
    json_output: bool = typer.Option(False, "--json", help="输出 JSON，便于脚本调用"),
) -> None:
    try:
        config_path, created = create_default_config()
        base = ServerSettings.from_env()
        qmt_path_configured = bool(base.qmt_path)
        account_configured = bool(base.account_id)
        if not mock and qmt_path_configured != account_configured:
            raise QMTLinkError(
                "QMT_CONFIG_REQUIRED",
                f"配置不完整：{config_path}；qmt_path 和 account_id 必须同时填写",
            )
        mode = "mock" if mock or not qmt_path_configured else "real"
        settings = ServerSettings(
            host=host or base.host,
            port=port or base.port,
            mode=mode,
            api_key=base.api_key,
            allow_trading=base.allow_trading,
            qmt_path=base.qmt_path,
            account_id=base.account_id,
            account_type=base.account_type,
            strategy_name=base.strategy_name,
        )
        startup = {
            "mode": settings.mode,
            "host": settings.host,
            "port": settings.port,
            "config_path": str(config_path),
            "config_created": created,
        }
        if json_output or not sys.stdout.isatty():
            emit(startup)
        else:
            config_state = "已创建" if created else "已存在"
            print("QmtLink Bridge 配置已加载")
            print(f"  模式：{settings.mode}")
            print(f"  配置文件：{config_path}（{config_state}）")

        from qmtlink.server.runner import run_server

        run_server(settings)
    except Exception as exc:
        _handle_error(exc)


@app.command("update")
def update() -> None:
    """Update the installed QmtLink tool with uv."""
    try:
        uv = shutil.which("uv")
        if uv is None:
            raise QMTLinkError(
                "UPDATE_TOOL_NOT_FOUND",
                "未找到 uv，请先安装 uv 后再执行 qmt update",
            )

        result = subprocess.run(
            [uv, "tool", "upgrade", "qmtlink"],
            capture_output=True,
            text=True,
            check=False,
        )
        if result.returncode != 0:
            detail = (result.stderr or result.stdout).strip()
            suffix = f": {detail}" if detail else ""
            raise QMTLinkError(
                "UPDATE_FAILED",
                f"更新 qmtlink 失败（退出码 {result.returncode}）{suffix}",
                retryable=True,
            )
        emit(
            {
                "package": "qmtlink",
                "updated": True,
                "output": (result.stdout or result.stderr).strip(),
            }
        )
    except Exception as exc:
        _handle_error(exc)


@app.command("health")
def health(pretty: bool = typer.Option(False, "--pretty")) -> None:
    try:
        with _client() as client:
            emit(client.health(), pretty=pretty)
    except Exception as exc:
        _handle_error(exc)


@app.command("capabilities")
def capabilities(pretty: bool = typer.Option(False, "--pretty")) -> None:
    try:
        with _client() as client:
            emit(client.capabilities(), pretty=pretty)
    except Exception as exc:
        _handle_error(exc)


@market_app.command("quote")
def market_quote(
    symbols: Annotated[list[str], typer.Option("--symbol", help="Repeat for multiple symbols")],
    pretty: bool = typer.Option(False, "--pretty"),
) -> None:
    try:
        with _client() as client:
            emit(client.get_quotes(symbols), pretty=pretty)
    except Exception as exc:
        _handle_error(exc)


@account_app.command("asset")
def account_asset(pretty: bool = typer.Option(False, "--pretty")) -> None:
    try:
        with _client() as client:
            emit(client.get_asset(), pretty=pretty)
    except Exception as exc:
        _handle_error(exc)


@account_app.command("positions")
def account_positions(pretty: bool = typer.Option(False, "--pretty")) -> None:
    try:
        with _client() as client:
            emit(client.get_positions(), pretty=pretty)
    except Exception as exc:
        _handle_error(exc)


@account_app.command("orders")
def account_orders(
    cancelable_only: bool = typer.Option(False, "--cancelable-only"),
    pretty: bool = typer.Option(False, "--pretty"),
) -> None:
    try:
        with _client() as client:
            emit(client.get_orders(cancelable_only=cancelable_only), pretty=pretty)
    except Exception as exc:
        _handle_error(exc)


@account_app.command("trades")
def account_trades(pretty: bool = typer.Option(False, "--pretty")) -> None:
    try:
        with _client() as client:
            emit(client.get_trades(), pretty=pretty)
    except Exception as exc:
        _handle_error(exc)


def _order_request(
    symbol: str,
    side: OrderSide,
    quantity: int,
    price: float | None,
    order_type: OrderType,
    client_order_id: str | None,
    live: bool,
) -> OrderRequest:
    values: dict[str, object] = {
        "symbol": symbol,
        "side": side,
        "quantity": quantity,
        "price": price,
        "order_type": order_type,
        "live": live,
    }
    if client_order_id:
        values["client_order_id"] = client_order_id
    return OrderRequest.model_validate(values)


@order_app.command("preview")
def order_preview(
    symbol: Annotated[str, typer.Option("--symbol")],
    side: Annotated[OrderSide, typer.Option("--side")],
    quantity: Annotated[int, typer.Option("--quantity", min=1)],
    price: Annotated[float | None, typer.Option("--price", min=0)] = None,
    order_type: Annotated[OrderType, typer.Option("--order-type")] = OrderType.LIMIT,
    client_order_id: Annotated[str | None, typer.Option("--client-order-id")] = None,
    pretty: Annotated[bool, typer.Option("--pretty")] = False,
) -> None:
    try:
        request = _order_request(symbol, side, quantity, price, order_type, client_order_id, False)
        with _client() as client:
            emit(client.preview_order(request), pretty=pretty)
    except Exception as exc:
        _handle_error(exc)


@order_app.command("place")
def order_place(
    symbol: Annotated[str, typer.Option("--symbol")],
    side: Annotated[OrderSide, typer.Option("--side")],
    quantity: Annotated[int, typer.Option("--quantity", min=1)],
    price: Annotated[float | None, typer.Option("--price", min=0)] = None,
    order_type: Annotated[OrderType, typer.Option("--order-type")] = OrderType.LIMIT,
    client_order_id: Annotated[str | None, typer.Option("--client-order-id")] = None,
    live: Annotated[bool, typer.Option("--live", help="Submit instead of preview")] = False,
    pretty: Annotated[bool, typer.Option("--pretty")] = False,
) -> None:
    try:
        request = _order_request(symbol, side, quantity, price, order_type, client_order_id, live)
        with _client() as client:
            result = client.place_order(request) if live else client.preview_order(request)
            emit(result, pretty=pretty)
    except Exception as exc:
        _handle_error(exc)


@order_app.command("get")
def order_get(
    order_id: Annotated[str, typer.Option("--order-id")],
    pretty: Annotated[bool, typer.Option("--pretty")] = False,
) -> None:
    try:
        with _client() as client:
            emit(client.get_order(order_id), pretty=pretty)
    except Exception as exc:
        _handle_error(exc)


@order_app.command("cancel")
def order_cancel(
    order_id: Annotated[str, typer.Option("--order-id")],
    live: Annotated[bool, typer.Option("--live", help="Submit the cancellation")] = False,
    pretty: Annotated[bool, typer.Option("--pretty")] = False,
) -> None:
    try:
        with _client() as client:
            emit(client.cancel_order(order_id, live=live), pretty=pretty)
    except Exception as exc:
        _handle_error(exc)


def main() -> None:
    app()
