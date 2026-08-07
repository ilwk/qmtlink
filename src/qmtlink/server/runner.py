from __future__ import annotations

from qmtlink.config import ServerSettings


def run_server(settings: ServerSettings) -> None:
    try:
        import uvicorn
    except ImportError as exc:  # pragma: no cover - depends on installation extras
        raise RuntimeError('server dependencies are missing; install "qmtlink[server]"') from exc

    from .app import create_app

    uvicorn.run(create_app(settings=settings), host=settings.host, port=settings.port, workers=1)
