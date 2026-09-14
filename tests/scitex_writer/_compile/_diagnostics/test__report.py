#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# File: tests/scitex_writer/_compile/_diagnostics/test__report.py

"""Diagnostics published in the scitex_dev.status Report/StatusCode shape."""

import os
from pathlib import Path

from scitex_dev.status import Check, StatusCode

from scitex_writer._compile._diagnostics import (
    analyse_latex_output,
    diagnose_compile,
    diagnose_exception,
    diagnostics_report,
)

LOGS = Path(__file__).parent / "fixtures" / "latex_logs"


def _unicode_report() -> dict:
    log = (LOGS / "unicode_char_not_set_up.log").read_text(encoding="utf-8")
    diagnostics = analyse_latex_output(compile_failed=True, log_text=log)
    return diagnostics_report(diagnostics, exit_code=1, log_path="main.log")


def test_report_has_one_not_ok_check_per_diagnostic():
    # Arrange
    report = _unicode_report()
    # Act
    verdicts = [check["ok"] for check in report["report"]["checks"]]
    # Assert
    assert verdicts == [False]


def test_report_check_detail_is_message_at_file_and_line():
    # Arrange
    report = _unicode_report()
    # Act
    detail = report["report"]["checks"][0]["detail"]
    # Assert
    assert detail.endswith(" at main.tex:4")


def test_report_checks_parse_as_scitex_dev_checks():
    # Arrange
    report = _unicode_report()
    # Act
    check = Check.from_dict(report["report"]["checks"][0])
    # Assert
    assert check.hint.startswith("U+300D")


def test_report_status_is_the_process_exit_code():
    # Arrange
    report = _unicode_report()
    # Act
    status = StatusCode.from_dict(report["status"])
    # Assert
    assert (status.kind, status.code) == ("process", 1)


def test_timeout_status_is_errno_etimedout():
    # Arrange
    diagnostics = analyse_latex_output(compile_failed=True, timed_out_after_seconds=5)
    # Act
    report = diagnostics_report(diagnostics, exit_code=None, timed_out_after_seconds=5)
    # Assert
    assert report["status"]["code"] == "ETIMEDOUT"


def test_diagnose_compile_reads_the_document_log(tmp_path):
    # Arrange
    logs = tmp_path / "01_manuscript" / "logs"
    logs.mkdir(parents=True)
    (logs / "manuscript.log").write_text((LOGS / "missing_file.log").read_text())
    # Act
    report = diagnose_compile(tmp_path, "manuscript", exit_code=1, compile_failed=True)
    # Assert
    assert report["items"][0]["cause"] == "missing-file"


def test_diagnose_compile_ignores_a_log_left_by_an_earlier_run(tmp_path):
    # Arrange
    logs = tmp_path / "01_manuscript" / "logs"
    logs.mkdir(parents=True)
    stale = logs / "manuscript.log"
    stale.write_text((LOGS / "missing_file.log").read_text())
    os.utime(stale, (1_000_000, 1_000_000))
    # Act
    report = diagnose_compile(
        tmp_path, "manuscript", exit_code=1, compile_failed=True, started_at=2_000_000
    )
    # Assert
    assert report["items"][0]["cause"] == "unknown"


def test_diagnose_exception_carries_the_error_text():
    # Arrange
    error = FileNotFoundError("compile.sh not found")
    # Act
    report = diagnose_exception(error)
    # Assert
    assert report["items"][0]["message"] == "FileNotFoundError: compile.sh not found"


# EOF
