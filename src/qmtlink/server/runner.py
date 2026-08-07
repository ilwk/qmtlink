from __future__ import annotations

from qmtlink.config import ServerSettings
from qmtlink.errors import QMTLinkError


def run_server(settings: ServerSettings) -> None:
    try:
        import uvicorn

        from .app import create_app
    except ImportError as exc:
        if exc.name in {"fastapi", "starlette", "uvicorn"}:
            raise QMTLinkError(
                "SERVER_DEPENDENCIES_MISSING",
                '缺少 Bridge 依赖，请执行：uv tool install "qmtlink[server]" --python 3.13',
            ) from exc
        raise

    uvicorn.run(create_app(settings=settings), host=settings.host, port=settings.port, workers=1)
