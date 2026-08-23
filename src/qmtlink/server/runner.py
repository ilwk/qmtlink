from __future__ import annotations

import argparse
import importlib.util
import logging
import platform
import sys
from collections.abc import Sequence
from pathlib import Path

from qmtlink import __version__
from qmtlink.config import (
    ServerSettings,
    create_default_config,
    resolve_config_path,
)
from qmtlink.errors import QMTLinkError

from .console import ConsolePresenter, DoctorCheck, configure_logging

logger = logging.getLogger(__name__)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="qmtlink",
        description="miniQMT/xtquant HTTP bridge",
    )
    parser.add_argument("--version", action="version", version=f"qmtlink {__version__}")
    commands = parser.add_subparsers(dest="command")
    commands.add_parser("doctor", help="check the bridge environment without starting it")
    return parser


def load_server_settings() -> tuple[Path, bool, ServerSettings]:
    config_path, created = create_default_config()
    settings = ServerSettings.from_env(config_path)
    if not settings.qmt_path or not settings.account_id:
        raise QMTLinkError(
            "QMT_CONFIG_REQUIRED",
            f"请在 {config_path} 中同时配置 server.qmt_path 和 server.account_id",
        )
    return config_path, created, settings


def run_server(settings: ServerSettings) -> None:
    import uvicorn

    from .app import create_app

    logger.info("Starting XtQuantTrader")
    app = create_app(settings=settings)
    logger.info("Starting HTTP bridge on %s:%s", settings.host, settings.port)
    uvicorn.run(
        app,
        host=settings.host,
        port=settings.port,
        workers=1,
        access_log=settings.access_log,
        log_level=settings.log_level.lower(),
        log_config=None,
    )
    logger.info("QmtLink stopped cleanly")


def doctor_checks() -> list[DoctorCheck]:
    config_path = resolve_config_path()
    xtquant_available = importlib.util.find_spec("xtquant") is not None
    checks = [
        DoctorCheck("Windows", platform.system() == "Windows", platform.system()),
        DoctorCheck(
            "Python",
            (3, 11) <= sys.version_info[:2] < (3, 14),
            platform.python_version(),
        ),
        DoctorCheck("Configuration", config_path.is_file(), str(config_path)),
        DoctorCheck(
            "xtquant",
            xtquant_available,
            "importable" if xtquant_available else "not importable",
        ),
    ]
    try:
        settings = ServerSettings.from_env(config_path)
    except QMTLinkError as exc:
        checks.append(DoctorCheck("Configuration values", False, exc.message))
        return checks

    qmt_path = Path(settings.qmt_path) if settings.qmt_path else None
    checks.extend(
        [
            DoctorCheck(
                "API key",
                bool(settings.api_key),
                "configured" if settings.api_key else "not configured",
            ),
            DoctorCheck(
                "miniQMT path",
                bool(qmt_path and qmt_path.is_dir()),
                str(qmt_path) if qmt_path else "not configured",
            ),
            DoctorCheck(
                "Account",
                bool(settings.account_id),
                "configured" if settings.account_id else "not configured",
            ),
        ]
    )
    return checks


def run_doctor(presenter: ConsolePresenter) -> bool:
    checks = doctor_checks()
    presenter.show_doctor(checks)
    return all(check.ok for check in checks)


def main(argv: Sequence[str] | None = None) -> None:
    args = build_parser().parse_args(argv)
    presenter = ConsolePresenter()
    if args.command == "doctor":
        if not run_doctor(presenter):
            raise SystemExit(1)
        return

    try:
        config_path, _created, settings = load_server_settings()
        presenter.show_startup(config_path, settings)
        configure_logging(presenter, settings.log_level)
        run_server(settings)
    except QMTLinkError as exc:
        if exc.code == "QMT_CONFIG_REQUIRED":
            presenter.show_setup_required(resolve_config_path())
        else:
            presenter.show_error(exc)
        raise SystemExit(2) from exc
