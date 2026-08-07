from qmtlink.config import ClientSettings, ServerSettings


def test_default_client_settings(monkeypatch) -> None:
    monkeypatch.delenv("QMTLINK_URL", raising=False)
    monkeypatch.delenv("QMTLINK_TIMEOUT", raising=False)
    settings = ClientSettings.from_env()
    assert settings.base_url == "http://127.0.0.1:8000"
    assert settings.timeout == 30.0


def test_default_server_settings(monkeypatch) -> None:
    monkeypatch.delenv("QMTLINK_HOST", raising=False)
    monkeypatch.delenv("QMTLINK_PORT", raising=False)
    monkeypatch.delenv("QMTLINK_MODE", raising=False)
    settings = ServerSettings.from_env()
    assert settings.host == "127.0.0.1"
    assert settings.port == 8000
    assert settings.mode == "real"
