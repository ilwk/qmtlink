from io import StringIO
from pathlib import Path

from rich.console import Console

from qmtlink.config import ServerSettings
from qmtlink.errors import QMTLinkError
from qmtlink.server.console import ConsolePresenter, DoctorCheck


def presenter_output(*, terminal: bool = False) -> tuple[ConsolePresenter, StringIO]:
    output = StringIO()
    console = Console(
        file=output,
        force_terminal=terminal,
        color_system=None,
        width=100,
    )
    return ConsolePresenter(console), output


def test_startup_summary_is_safe_and_useful_when_redirected() -> None:
    presenter, output = presenter_output()
    settings = ServerSettings(
        host="0.0.0.0",
        port=8000,
        api_key="never-print-this-secret",
        allow_trading=False,
        qmt_path=r"C:\miniQMT\userdata_mini",
        account_id="12345678",
    )

    presenter.show_startup(Path(r"C:\Users\ilwk\.config\qmtlink\config.toml"), settings)

    rendered = output.getvalue()
    assert "QmtLink Bridge" in rendered
    assert "******5678" in rendered
    assert "never-print-this-secret" not in rendered
    assert "Bind: 0.0.0.0:8000" in rendered
    assert "OpenAPI: http://127.0.0.1:8000/docs" in rendered
    assert "Trading: LOCKED" in rendered


def test_setup_required_explains_the_next_action() -> None:
    presenter, output = presenter_output()
    config_path = Path(r"C:\Users\ilwk\.config\qmtlink\config.toml")

    presenter.show_setup_required(config_path)

    rendered = output.getvalue()
    assert "QmtLink needs configuration" in rendered
    assert str(config_path) in rendered
    assert "server.qmt_path" in rendered
    assert "server.account_id" in rendered
    assert "qmtlink" in rendered


def test_expected_error_has_code_and_action_without_traceback() -> None:
    presenter, output = presenter_output()
    error = QMTLinkError(
        "QMT_CONNECT_FAILED",
        "XtQuantTrader.connect returned -1",
        retryable=True,
    )

    presenter.show_error(error)

    rendered = output.getvalue()
    assert "miniQMT connection failed" in rendered
    assert "QMT_CONNECT_FAILED" in rendered
    assert "miniQMT is running" in rendered
    assert "Traceback" not in rendered


def test_doctor_summary_reports_each_check_and_result() -> None:
    presenter, output = presenter_output()

    presenter.show_doctor(
        [
            DoctorCheck("Python", True, "3.13.5"),
            DoctorCheck("xtquant", False, "not importable"),
        ]
    )

    rendered = output.getvalue()
    assert "QmtLink Doctor" in rendered
    assert "PASS Python: 3.13.5" in rendered
    assert "FAIL xtquant: not importable" in rendered
    assert "Result: not ready" in rendered
