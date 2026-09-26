#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# File: src/scitex_writer/_compile/_diagnostics/_report.py

"""Diagnostics in the fleet's ``scitex_dev.status`` shape, from a real compile.

Wire form (JSON)::

    {"status": {"kind": "process", "code": 1, "message": "..."},
     "report": {"package": "scitex-writer", "ok": false,
                "checks": [{"name", "ok", "detail", "hint"}], "summary": "..."},
     "items": [{"cause", "severity", "message", "hint", "context",
                "file", "line"}],
     "log_path": "01_manuscript/logs/manuscript.log"}
"""

from __future__ import annotations

from pathlib import Path
from typing import Optional

from ._analyse import analyse_latex_output
from ._model import SEVERITY_ERROR, UNKNOWN, LatexDiagnostic
from ._rules import FULL_LOG_HINT
from ._tex_log import meaningful_tail

REPORT_PACKAGE = "scitex-writer"


def diagnostics_report(
    diagnostics: list[LatexDiagnostic],
    *,
    exit_code: Optional[int],
    timed_out_after_seconds: Optional[float] = None,
    log_path: Optional[str] = None,
) -> dict:
    """One not-ok Check per diagnostic, plus the engine exit as a StatusCode."""
    from scitex_dev.status import Check, StatusCode, UnknownPolicy, rollup

    errors = sum(1 for d in diagnostics if d.is_error)
    warnings = len(diagnostics) - errors
    found = f"{errors} error(s), {warnings} warning(s) found"
    found += f" in {log_path}" if log_path else ""
    if timed_out_after_seconds is not None:
        status = StatusCode(
            kind="errno",
            code="ETIMEDOUT",
            message=f"compile stopped after {timed_out_after_seconds:g} s; {found}",
        )
    elif exit_code is None:
        status = StatusCode(
            kind="process",
            code=1,
            message=f"compile did not return an exit status; {found}",
        )
    else:
        status = StatusCode(
            kind="process",
            code=exit_code,
            message=f"compile.sh exited {exit_code}; {found}",
        )

    checks = [
        Check.not_ok(
            f"{d.severity}:{d.cause}" + (f"@{d.location}" if d.location else ""),
            f"{d.message} at {d.location}" if d.location else d.message,
            d.hint,
        )
        for d in diagnostics
    ]
    report = rollup(REPORT_PACKAGE, checks, unknown_policy=UnknownPolicy.PROPAGATE)
    return {
        "status": status.to_dict(),
        "report": report.to_dict(),
        "items": [d.to_dict() for d in diagnostics],
        "log_path": log_path,
    }


def _read_if_written_since(path: Path, started_at: Optional[float]) -> str:
    # A log older than this run belongs to a previous compile and would mislead.
    try:
        if started_at is not None and path.stat().st_mtime < started_at:
            return ""
        return path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return ""


def diagnose_compile(
    project_dir: Path,
    doc_type: str,
    *,
    exit_code: Optional[int],
    compile_failed: bool,
    stdout: str = "",
    stderr: str = "",
    started_at: Optional[float] = None,
    timed_out_after_seconds: Optional[float] = None,
) -> dict:
    """Diagnose one compile.sh run from its console output and the doc's logs."""
    from .._artifacts import _doc_latex_log

    log_path = (
        _doc_latex_log(project_dir, doc_type) if doc_type in _doc_types() else None
    )
    log_text = _read_if_written_since(log_path, started_at) if log_path else ""
    blg_text = (
        _read_if_written_since(log_path.with_suffix(".blg"), started_at)
        if log_path
        else ""
    )
    console_text = "\n".join(filter(None, [stdout, stderr]))
    try:
        diagnostics = analyse_latex_output(
            compile_failed=compile_failed,
            log_text=log_text,
            console_text=console_text,
            bibliography_log_text=blg_text,
            timed_out_after_seconds=timed_out_after_seconds,
            project_dir=project_dir,
        )
    except Exception as exc:  # an analyser bug must not hide the compile outcome
        diagnostics = [
            LatexDiagnostic(
                cause=UNKNOWN,
                severity=SEVERITY_ERROR,
                message=f"Log analysis failed ({type(exc).__name__}: {exc})",
                hint=FULL_LOG_HINT,
                context=meaningful_tail(
                    "\n".join(filter(None, [log_text, console_text]))
                ),
            )
        ]
    return diagnostics_report(
        diagnostics,
        exit_code=exit_code,
        timed_out_after_seconds=timed_out_after_seconds,
        log_path=str(log_path.relative_to(project_dir)) if log_text else None,
    )


def diagnose_exception(
    error: BaseException | str,
    *,
    cause: str = UNKNOWN,
    hint: str = FULL_LOG_HINT,
) -> dict:
    """Diagnostics for a compile that could not run the engine at all."""
    text = error if isinstance(error, str) else f"{type(error).__name__}: {error}"
    diagnostic = LatexDiagnostic(
        cause=cause,
        severity=SEVERITY_ERROR,
        message=text,
        hint=hint,
        context=text,
    )
    return diagnostics_report([diagnostic], exit_code=None)


def _doc_types() -> tuple[str, ...]:
    from ..._dataclasses.config import DOC_TYPE_DIRS

    return tuple(DOC_TYPE_DIRS)


__all__ = ["diagnose_compile", "diagnose_exception", "diagnostics_report"]

# EOF
