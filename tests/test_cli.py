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
    assert '"ready_for_mock": true' in result.stdout


def test_bridge_run_creates_config_and_requests_two_values(monkeypatch, tmp_path) -> None:
    config_path = tmp_path / "config.toml"
    monkeypatch.setenv("QMTLINK_CONFIG", str(config_path))
    monkeypatch.delenv("QMTLINK_QMT_PATH", raising=False)
    monkeypatch.delenv("QMTLINK_ACCOUNT_ID", raising=False)

    result = runner.invoke(app, ["bridge", "run"])

    assert result.exit_code == 5
    assert config_path.is_file()
    assert '"code": "QMT_CONFIG_REQUIRED"' in result.stdout
    assert "qmt_path" in result.stdout
    assert "account_id" in result.stdout
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
