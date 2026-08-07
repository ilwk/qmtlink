import tomllib

from typer.testing import CliRunner

from qmtlink.cli.main import app

runner = CliRunner()


def test_bridge_doctor_outputs_json(monkeypatch, tmp_path) -> None:
    config_path = tmp_path / "config.toml"
    monkeypatch.setenv("QMTLINK_CONFIG", str(config_path))
    result = runner.invoke(app, ["bridge", "doctor"])
    assert result.exit_code == 0
    assert '"ok": true' in result.stdout
    assert f'"config_path": "{config_path}"' in result.stdout
    assert '"config_exists": false' in result.stdout
    assert '"server_dependencies_installed": true' in result.stdout
    assert '"ready_for_mock": true' in result.stdout


def test_bridge_run_without_account_starts_mock(monkeypatch, tmp_path) -> None:
    config_path = tmp_path / "config.toml"
    captured = {}
    monkeypatch.setenv("QMTLINK_CONFIG", str(config_path))
    monkeypatch.delenv("QMTLINK_QMT_PATH", raising=False)
    monkeypatch.delenv("QMTLINK_ACCOUNT_ID", raising=False)
    monkeypatch.setattr(
        "qmtlink.server.runner.run_server",
        lambda settings: captured.update(settings=settings),
    )

    result = runner.invoke(app, ["bridge", "run"])

    assert result.exit_code == 0
    assert config_path.is_file()
    assert '"mode": "mock"' in result.stdout
    assert '"config_created": true' in result.stdout
    assert captured["settings"].mode == "mock"
    assert set(tomllib.loads(config_path.read_text(encoding="utf-8"))) == {
        "api_key",
        "qmt_path",
        "account_id",
    }


def test_bridge_mock_starts_with_generated_config(monkeypatch, tmp_path) -> None:
    config_path = tmp_path / "config.toml"
    captured = {}
    monkeypatch.setenv("QMTLINK_CONFIG", str(config_path))
    monkeypatch.setattr(
        "qmtlink.server.runner.run_server",
        lambda settings: captured.update(settings=settings),
    )

    result = runner.invoke(app, ["bridge", "run", "--mock"])

    assert result.exit_code == 0
    assert config_path.is_file()
    assert captured["settings"].mode == "mock"
    assert captured["settings"].api_key


def test_bridge_run_rejects_partially_configured_account(monkeypatch, tmp_path) -> None:
    config_path = tmp_path / "config.toml"
    config_path.write_text(
        'api_key = "secret"\nqmt_path = \'C:\\miniQMT\\userdata_mini\'\naccount_id = ""\n',
        encoding="utf-8",
    )
    monkeypatch.setenv("QMTLINK_CONFIG", str(config_path))
    monkeypatch.delenv("QMTLINK_QMT_PATH", raising=False)
    monkeypatch.delenv("QMTLINK_ACCOUNT_ID", raising=False)

    result = runner.invoke(app, ["bridge", "run"])

    assert result.exit_code == 5
    assert '"code": "QMT_CONFIG_REQUIRED"' in result.stdout
    assert "必须同时填写" in result.stdout


def test_bridge_run_with_account_starts_real_mode(monkeypatch, tmp_path) -> None:
    config_path = tmp_path / "config.toml"
    captured = {}
    config_path.write_text(
        'api_key = "secret"\nqmt_path = \'C:\\miniQMT\\userdata_mini\'\naccount_id = "123456"\n',
        encoding="utf-8",
    )
    monkeypatch.setenv("QMTLINK_CONFIG", str(config_path))
    monkeypatch.delenv("QMTLINK_QMT_PATH", raising=False)
    monkeypatch.delenv("QMTLINK_ACCOUNT_ID", raising=False)
    monkeypatch.setattr(
        "qmtlink.server.runner.run_server",
        lambda settings: captured.update(settings=settings),
    )

    result = runner.invoke(app, ["bridge", "run"])

    assert result.exit_code == 0
    assert '"mode": "real"' in result.stdout
    assert captured["settings"].mode == "real"
