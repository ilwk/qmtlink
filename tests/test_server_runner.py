import builtins

import pytest

from qmtlink.config import ServerSettings
from qmtlink.errors import QMTLinkError
from qmtlink.server.runner import run_server


def test_run_server_explains_missing_extra(monkeypatch) -> None:
    real_import = builtins.__import__

    def import_without_uvicorn(name, *args, **kwargs):
        if name == "uvicorn":
            error = ModuleNotFoundError("No module named 'uvicorn'")
            error.name = "uvicorn"
            raise error
        return real_import(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", import_without_uvicorn)

    with pytest.raises(QMTLinkError) as error:
        run_server(ServerSettings(mode="mock"))

    assert error.value.code == "SERVER_DEPENDENCIES_MISSING"
    assert "qmtlink[server]" in error.value.message
