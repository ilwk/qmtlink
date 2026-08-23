import pytest

from qmtlink.errors import QMTLinkError
from qmtlink.server.runner import load_server_settings, main


def test_load_server_settings_creates_config_and_requires_qmt(monkeypatch, tmp_path) -> None:
    config_path = tmp_path / "config.toml"
    monkeypatch.setenv("QMTLINK_CONFIG", str(config_path))
    monkeypatch.delenv("QMTLINK_QMT_PATH", raising=False)
    monkeypatch.delenv("QMTLINK_ACCOUNT_ID", raising=False)

    with pytest.raises(QMTLinkError) as error:
        load_server_settings()

    assert error.value.code == "QMT_CONFIG_REQUIRED"
    assert str(config_path) in error.value.message
    assert config_path.is_file()


def test_main_starts_bridge_from_server_environment(monkeypatch, tmp_path) -> None:
    config_path = tmp_path / "config.toml"
    monkeypatch.setenv("QMTLINK_CONFIG", str(config_path))
    monkeypatch.setenv("QMTLINK_QMT_PATH", r"C:\miniQMT\userdata_mini")
    monkeypatch.setenv("QMTLINK_ACCOUNT_ID", "123456")
    captured = {}

    def capture(settings) -> None:
        captured["settings"] = settings

    monkeypatch.setattr("qmtlink.server.runner.run_server", capture)

    main()

    assert captured["settings"].qmt_path == r"C:\miniQMT\userdata_mini"
    assert captured["settings"].account_id == "123456"
