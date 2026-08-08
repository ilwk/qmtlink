import subprocess
import tomllib
from types import SimpleNamespace

from typer.testing import CliRunner

from qmtlink.cli.main import app

runner = CliRunner()


def test_update_uses_uv_tool_upgrade(monkeypatch) -> None:
    command = {}
    monkeypatch.setattr("qmtlink.cli.main.shutil.which", lambda name: "/usr/bin/uv")

    def run(args, **kwargs):
        command["args"] = args
        command["kwargs"] = kwargs
        return subprocess.CompletedProcess(args, 0, stdout="Updated qmtlink", stderr="")

    monkeypatch.setattr("qmtlink.cli.main.subprocess.run", run)

    result = runner.invoke(app, ["update"])

    assert result.exit_code == 0
    assert command["args"] == ["/usr/bin/uv", "tool", "upgrade", "qmtlink"]
    assert command["kwargs"] == {"capture_output": True, "text": True, "check": False}
    assert '"updated": true' in result.stdout
    assert '"output": "Updated qmtlink"' in result.stdout


def test_update_requires_uv(monkeypatch) -> None:
    monkeypatch.setattr("qmtlink.cli.main.shutil.which", lambda name: None)

    result = runner.invoke(app, ["update"])

    assert result.exit_code == 5
    assert '"code": "UPDATE_TOOL_NOT_FOUND"' in result.stdout


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
        "server",
        "client",
    }


def test_bridge_run_uses_human_output_in_a_terminal(monkeypatch, tmp_path) -> None:
    config_path = tmp_path / "config.toml"
    monkeypatch.setenv("QMTLINK_CONFIG", str(config_path))
    monkeypatch.setattr(
        "qmtlink.cli.main.sys",
        SimpleNamespace(stdout=SimpleNamespace(isatty=lambda: True)),
    )
    monkeypatch.setattr("qmtlink.server.runner.run_server", lambda settings: None)

    result = runner.invoke(app, ["bridge", "run", "--mock"])

    assert result.exit_code == 0
    assert "QmtLink Bridge 配置已加载" in result.stdout
    assert "模式：mock" in result.stdout
    assert "监听地址" not in result.stdout
    assert '"ok"' not in result.stdout


def test_bridge_run_json_output_can_be_forced(monkeypatch, tmp_path) -> None:
    config_path = tmp_path / "config.toml"
    monkeypatch.setenv("QMTLINK_CONFIG", str(config_path))
    monkeypatch.setattr(
        "qmtlink.cli.main.sys",
        SimpleNamespace(stdout=SimpleNamespace(isatty=lambda: True)),
    )
    monkeypatch.setattr("qmtlink.server.runner.run_server", lambda settings: None)

    result = runner.invoke(app, ["bridge", "run", "--mock", "--json"])

    assert result.exit_code == 0
    assert '"ok": true' in result.stdout
    assert '"mode": "mock"' in result.stdout


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
        'api_key = "secret"\n\n[server]\n'
        'qmt_path = \'C:\\miniQMT\\userdata_mini\'\naccount_id = ""\n',
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
        'api_key = "secret"\n\n[server]\n'
        'qmt_path = \'C:\\miniQMT\\userdata_mini\'\naccount_id = "123456"\n',
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
