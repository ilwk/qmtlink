from typer.testing import CliRunner

from qmtlink.cli.main import app

runner = CliRunner()


def test_bridge_doctor_outputs_json() -> None:
    result = runner.invoke(app, ["bridge", "doctor"])
    assert result.exit_code == 0
    assert '"ok": true' in result.stdout
    assert '"ready_for_mock": true' in result.stdout
