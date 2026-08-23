from __future__ import annotations

import sys
from pathlib import Path

from qmtlink.config import ServerSettings, create_default_config
from qmtlink.errors import QMTLinkError


def load_server_settings() -> tuple[Path, bool, ServerSettings]:
    config_path, created = create_default_config()
    settings = ServerSettings.from_env(config_path)
    if not settings.qmt_path or not settings.account_id:
        raise QMTLinkError(
            "QMT_CONFIG_REQUIRED",
            f"请在 {config_path} 中同时配置 server.qmt_path 和 server.account_id",
        )
    return config_path, created, settings


def run_server(settings: ServerSettings) -> None:
    import uvicorn

    from .app import create_app

    uvicorn.run(create_app(settings=settings), host=settings.host, port=settings.port, workers=1)


def main() -> None:
    try:
        config_path, created, settings = load_server_settings()
        config_state = "已创建" if created else "已加载"
        print(f"QmtLink bridge 配置{config_state}：{config_path}")
        print(f"监听：http://{settings.host}:{settings.port}")
        run_server(settings)
    except QMTLinkError as exc:
        print(f"{exc.code}: {exc.message}", file=sys.stderr)
        raise SystemExit(2) from exc
