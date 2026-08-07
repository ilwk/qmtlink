from __future__ import annotations

from qmtlink.config import ServerSettings


def run_server(settings: ServerSettings) -> None:
    import uvicorn

    from .app import create_app

    uvicorn.run(create_app(settings=settings), host=settings.host, port=settings.port, workers=1)
