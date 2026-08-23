from __future__ import annotations

import logging
from dataclasses import dataclass
from pathlib import Path

from rich.console import Console
from rich.logging import RichHandler
from rich.panel import Panel
from rich.table import Table
from rich.text import Text

from qmtlink import __version__
from qmtlink.config import ServerSettings
from qmtlink.errors import QMTLinkError


@dataclass(frozen=True, slots=True)
class DoctorCheck:
    name: str
    ok: bool
    detail: str


def _masked_account(account_id: str | None) -> str:
    if not account_id:
        return "not configured"
    return f"******{account_id[-4:]}"


def _local_host(host: str) -> str:
    return "127.0.0.1" if host in {"0.0.0.0", "::"} else host


class ConsolePresenter:
    def __init__(self, console: Console | None = None) -> None:
        self.console = console or Console()

    def show_startup(self, config_path: Path, settings: ServerSettings) -> None:
        local_url = f"http://{_local_host(settings.host)}:{settings.port}"
        values = (
            ("Config", str(config_path)),
            ("miniQMT", settings.qmt_path or "not configured"),
            ("Account", f"{_masked_account(settings.account_id)} · {settings.account_type}"),
            ("Trading", "ENABLED" if settings.allow_trading else "LOCKED"),
            ("Strategy", settings.strategy_name),
            ("Bind", f"{settings.host}:{settings.port}"),
            ("Local API", local_url),
            ("OpenAPI", f"{local_url}/docs"),
        )
        if not self.console.is_terminal:
            self.console.print(f"QmtLink Bridge {__version__}")
            for label, value in values:
                self.console.print(f"{label}: {value}")
            return

        table = Table.grid(padding=(0, 2))
        table.add_column(style="bold cyan", no_wrap=True)
        table.add_column()
        for label, value in values:
            style = None
            if label == "Trading":
                style = "bold red" if settings.allow_trading else "bold yellow"
            table.add_row(label, Text(value, style=style))
        self.console.print(
            Panel(
                table,
                title=f"[bold]QmtLink Bridge {__version__}[/bold]",
                border_style="cyan",
                padding=(1, 2),
            )
        )

    def show_setup_required(self, config_path: Path) -> None:
        lines = [
            "QmtLink needs configuration",
            f"Config: {config_path}",
            "Required: server.qmt_path",
            "Required: server.account_id",
            "Save the file, make sure miniQMT is running and logged in, then run: qmtlink",
        ]
        if not self.console.is_terminal:
            for line in lines:
                self.console.print(line)
            return
        body = Text()
        body.append(f"A configuration file is available at:\n\n  {config_path}\n\n")
        body.append("Configure both fields:\n\n", style="bold")
        body.append("  server.qmt_path\n  server.account_id\n\n", style="cyan")
        body.append("Then make sure miniQMT is running and logged in, and run:\n\n  ")
        body.append("qmtlink", style="bold green")
        self.console.print(
            Panel(body, title="[bold yellow]QmtLink needs configuration[/bold yellow]")
        )

    def show_error(self, error: QMTLinkError) -> None:
        title, actions = _error_guidance(error.code)
        lines = [
            title,
            error.message,
            f"Error code: {error.code}",
            *actions,
        ]
        if not self.console.is_terminal:
            for line in lines:
                self.console.print(line)
            return
        body = Text()
        body.append(f"{error.message}\n\n")
        if actions:
            body.append("Check that:\n", style="bold")
            for index, action in enumerate(actions, start=1):
                body.append(f"  {index}. {action}\n")
            body.append("\n")
        body.append(f"Error code: {error.code}", style="dim")
        self.console.print(Panel(body, title=f"[bold red]{title}[/bold red]", border_style="red"))

    def show_doctor(self, checks: list[DoctorCheck]) -> None:
        ready = all(check.ok for check in checks)
        if not self.console.is_terminal:
            self.console.print("QmtLink Doctor")
            for check in checks:
                self.console.print(f"{'PASS' if check.ok else 'FAIL'} {check.name}: {check.detail}")
            self.console.print(f"Result: {'ready' if ready else 'not ready'}")
            return
        table = Table(show_header=False, box=None, padding=(0, 1))
        table.add_column(width=2)
        table.add_column(style="bold")
        table.add_column()
        for check in checks:
            table.add_row(
                "✓" if check.ok else "✗",
                check.name,
                check.detail,
                style="green" if check.ok else "red",
            )
        result = Text(f"\nResult: {'ready' if ready else 'not ready'}")
        result.stylize("bold green" if ready else "bold red")
        self.console.print(Panel(table, title="[bold]QmtLink Doctor[/bold]"))
        self.console.print(result)


def configure_logging(presenter: ConsolePresenter, level: str) -> None:
    handler = RichHandler(
        console=presenter.console,
        show_time=True,
        omit_repeated_times=False,
        show_level=True,
        show_path=False,
        markup=False,
        rich_tracebacks=True,
        log_time_format="%H:%M:%S",
    )
    handler.setFormatter(logging.Formatter("%(message)s"))
    logging.basicConfig(
        level=getattr(logging, level),
        format="%(message)s",
        handlers=[handler],
        force=True,
    )
    for name in ("uvicorn", "uvicorn.error", "uvicorn.access"):
        logger = logging.getLogger(name)
        logger.handlers.clear()
        logger.propagate = True


def _error_guidance(code: str) -> tuple[str, list[str]]:
    guidance = {
        "QMT_CONNECT_FAILED": (
            "miniQMT connection failed",
            [
                "miniQMT is running",
                "the account is logged in",
                "server.qmt_path points to userdata_mini",
            ],
        ),
        "QMT_SUBSCRIBE_FAILED": (
            "miniQMT account subscription failed",
            ["the configured account is available in miniQMT", "the account type is correct"],
        ),
        "XTQUANT_NOT_INSTALLED": (
            "xtquant is unavailable",
            ["QmtLink is installed on Windows with Python 3.13"],
        ),
        "INVALID_CONFIG": ("QmtLink configuration is invalid", []),
    }
    return guidance.get(code, ("QmtLink failed to start", []))
