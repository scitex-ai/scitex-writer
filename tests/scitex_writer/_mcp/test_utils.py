#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# File: tests/scitex_writer/_mcp/test_utils.py

"""run_compile_script: exit 3 ("PDF promoted with warnings") is a success,
and every outcome carries `diagnostics` explaining it."""

import shutil
from pathlib import Path

from scitex_writer._compile._event_log import EVENT_SUCCESS, read_events
from scitex_writer._mcp.utils import run_compile_script

ONE_PAGE_PDF = b"%PDF-1.4\n1 0 obj << /Type /Page >> endobj\n%%EOF\n"
LATEX_LOGS = (
    Path(__file__).parents[1] / "_compile" / "_diagnostics" / "fixtures" / "latex_logs"
)


def _compile_sh_that_fails_with_log(workspace: Path, fixture: str) -> None:
    shutil.copy(LATEX_LOGS / fixture, workspace / "fixture.log")
    script = workspace / "compile.sh"
    script.write_text(
        "#!/bin/bash\n"
        "mkdir -p 01_manuscript/logs\n"
        "cp fixture.log 01_manuscript/logs/manuscript.log\n"
        "echo 'LaTeX compilation failed' >&2\n"
        "exit 1\n"
    )
    script.chmod(0o755)


def _compile_sh_that_promotes_a_pdf(workspace: Path, pdf: bytes | None) -> None:
    body = "exit 3"
    if pdf is not None:
        (workspace / "fixture.pdf").write_bytes(pdf)
        body = (
            "mkdir -p 01_manuscript && "
            "cp fixture.pdf 01_manuscript/manuscript.pdf && exit 3"
        )
    script = workspace / "compile.sh"
    script.write_text("#!/bin/bash\n" + body + "\n")
    script.chmod(0o755)


def _compile_sh_that_exits(workspace: Path, code: int, pdf: bytes | None) -> None:
    """compile.sh that exits ``code``, optionally leaving a PDF where the run
    expects it. Unlike the exit-3 helper above, the code is the parameter — this
    is what lets a test ask about exit 0 with nothing to show for it."""
    body = f"exit {code}"
    if pdf is not None:
        (workspace / "fixture.pdf").write_bytes(pdf)
        body = (
            "mkdir -p 01_manuscript && "
            f"cp fixture.pdf 01_manuscript/manuscript.pdf && exit {code}"
        )
    script = workspace / "compile.sh"
    script.write_text("#!/bin/bash\n" + body + "\n")
    script.chmod(0o755)


def test_exit_0_without_a_pdf_is_a_failure(tmp_path):
    # Arrange: the divergence this path carried for weeks — the runner recorded
    # `exit-zero-no-pdf` while this one answered "compiled successfully" with
    # output_pdf None. Both read the same verdict now, so this cannot come back
    # on one side only.
    _compile_sh_that_exits(tmp_path, 0, None)
    # Act
    result = run_compile_script(tmp_path, "manuscript")
    # Assert
    assert result["success"] is False


def test_exit_0_without_a_pdf_records_the_shared_reason(tmp_path):
    # Arrange
    _compile_sh_that_exits(tmp_path, 0, None)
    # Act
    run_compile_script(tmp_path, "manuscript")
    # Assert
    assert read_events(tmp_path)[-1]["reason"] == "exit-zero-no-pdf"


def test_exit_0_with_a_real_pdf_is_a_success(tmp_path):
    # Arrange: the other half of the same pair — the fix must not turn a good
    # clean compile into a failure.
    _compile_sh_that_exits(tmp_path, 0, ONE_PAGE_PDF)
    # Act
    result = run_compile_script(tmp_path, "manuscript")
    # Assert
    assert result["success"] is True


def test_exit_0_success_records_the_page_count(tmp_path):
    # Arrange
    _compile_sh_that_exits(tmp_path, 0, ONE_PAGE_PDF)
    # Act
    run_compile_script(tmp_path, "manuscript")
    # Assert
    assert read_events(tmp_path)[-1]["pages"] == 1


def test_exit_3_with_a_produced_pdf_counts_as_success(tmp_path):
    # Arrange
    _compile_sh_that_promotes_a_pdf(tmp_path, ONE_PAGE_PDF)
    # Act
    result = run_compile_script(tmp_path, "manuscript")
    # Assert
    assert result["success"] is True


def test_exit_3_with_a_produced_pdf_reports_a_warning(tmp_path):
    # Arrange
    _compile_sh_that_promotes_a_pdf(tmp_path, ONE_PAGE_PDF)
    # Act
    result = run_compile_script(tmp_path, "manuscript")
    # Assert
    assert "PROMOTED" in result["warnings"][0]


def test_exit_3_with_a_produced_pdf_is_recorded_as_a_success(tmp_path):
    # Arrange
    _compile_sh_that_promotes_a_pdf(tmp_path, ONE_PAGE_PDF)
    # Act
    run_compile_script(tmp_path, "manuscript")
    # Assert
    assert read_events(tmp_path)[-1]["kind"] == EVENT_SUCCESS


def test_exit_3_without_a_pdf_is_still_a_failure(tmp_path):
    # Arrange
    _compile_sh_that_promotes_a_pdf(tmp_path, None)
    # Act
    result = run_compile_script(tmp_path, "manuscript")
    # Assert
    assert result["success"] is False


def test_exit_3_with_a_zero_page_pdf_is_still_a_failure(tmp_path):
    # Arrange
    _compile_sh_that_promotes_a_pdf(tmp_path, b"%PDF-1.4\n%%EOF\n")
    # Act
    result = run_compile_script(tmp_path, "manuscript")
    # Assert
    assert result["success"] is False


def test_failed_compile_returns_diagnostics_with_the_cause(tmp_path):
    # Arrange
    _compile_sh_that_fails_with_log(tmp_path, "unicode_char_not_set_up.log")
    # Act
    result = run_compile_script(tmp_path, "manuscript")
    # Assert
    assert result["diagnostics"]["items"][0]["cause"] == "unicode-char-not-set-up"


def test_failed_compile_keeps_the_existing_error_field(tmp_path):
    # Arrange
    _compile_sh_that_fails_with_log(tmp_path, "unicode_char_not_set_up.log")
    # Act
    result = run_compile_script(tmp_path, "manuscript")
    # Assert
    assert result["error"] == "Compilation failed with exit code 1"


def test_failed_compile_diagnostics_status_is_the_exit_code(tmp_path):
    # Arrange
    _compile_sh_that_fails_with_log(tmp_path, "undefined_control_sequence.log")
    # Act
    result = run_compile_script(tmp_path, "manuscript")
    # Assert
    assert result["diagnostics"]["status"]["code"] == 1


def test_timed_out_compile_returns_a_timeout_diagnostic(tmp_path):
    # Arrange
    script = tmp_path / "compile.sh"
    script.write_text("#!/bin/bash\nsleep 5\n")
    script.chmod(0o755)
    # Act
    result = run_compile_script(tmp_path, "manuscript", timeout=1)
    # Assert
    assert result["diagnostics"]["items"][0]["cause"] == "timeout"


def test_missing_compile_script_still_returns_diagnostics(tmp_path):
    # Arrange
    empty_workspace = tmp_path
    # Act
    result = run_compile_script(empty_workspace, "manuscript")
    # Assert
    assert result["diagnostics"]["items"][0]["cause"] == "missing-file"


# EOF
