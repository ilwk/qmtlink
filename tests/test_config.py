import tomllib

from qmtlink.config import ClientSettings, ServerSettings, create_default_config


def test_default_client_settings(monkeypatch, tmp_path) -> None:
    monkeypatch.setenv("QMTLINK_CONFIG", str(tmp_path / "missing.toml"))
    monkeypatch.delenv("QMTLINK_URL", raising=False)
    monkeypatch.delenv("QMTLINK_API_KEY", raising=False)
    monkeypatch.delenv("QMTLINK_TIMEOUT", raising=False)
    settings = ClientSettings.from_env()
    assert settings.base_url == "http://127.0.0.1:8000"
    assert settings.timeout == 30.0


def test_default_server_settings(monkeypatch, tmp_path) -> None:
    monkeypatch.setenv("QMTLINK_CONFIG", str(tmp_path / "missing.toml"))
    monkeypatch.delenv("QMTLINK_HOST", raising=False)
    monkeypatch.delenv("QMTLINK_PORT", raising=False)
    monkeypatch.delenv("QMTLINK_MODE", raising=False)
    settings = ServerSettings.from_env()
    assert settings.host == "127.0.0.1"
    assert settings.port == 8000
    assert settings.mode == "real"


def test_create_default_config_is_minimal_and_stable(tmp_path) -> None:
    config_path = tmp_path / "qmtlink" / "config.toml"

    path, created = create_default_config(config_path)
    first_content = path.read_bytes()
    data = tomllib.loads(first_content.decode())

    assert created is True
    assert set(data) == {"api_key", "qmt_path", "account_id"}
    assert len(data["api_key"]) >= 32
    assert data["qmt_path"] == ""
    assert data["account_id"] == ""

    _, created_again = create_default_config(config_path)
    assert created_again is False
    assert path.read_bytes() == first_content


def test_settings_are_loaded_from_flat_config(monkeypatch, tmp_path) -> None:
    config_path = tmp_path / "config.toml"
    config_path.write_text(
        """api_key = "secret"
host = "0.0.0.0"
port = 9000
qmt_path = 'C:\\miniQMT\\userdata_mini'
account_id = "123456"
allow_live_orders = true
""",
        encoding="utf-8",
    )
    for name in (
        "QMTLINK_URL",
        "QMTLINK_API_KEY",
        "QMTLINK_HOST",
        "QMTLINK_PORT",
        "QMTLINK_QMT_PATH",
        "QMTLINK_ACCOUNT_ID",
        "QMTLINK_ALLOW_LIVE_ORDERS",
    ):
        monkeypatch.delenv(name, raising=False)

    client = ClientSettings.from_env(config_path)
    server = ServerSettings.from_env(config_path)

    assert client.base_url == "http://127.0.0.1:9000"
    assert client.api_key == "secret"
    assert server.host == "0.0.0.0"
    assert server.port == 9000
    assert server.qmt_path == r"C:\miniQMT\userdata_mini"
    assert server.account_id == "123456"
    assert server.allow_live_orders is True
