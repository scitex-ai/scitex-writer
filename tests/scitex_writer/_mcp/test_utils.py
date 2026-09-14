#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# File: tests/scitex_writer/_mcp/test_utils.py

"""run_compile_script: exit 3 ("PDF promoted with warnings") is a success."""

from pathlib import Path

from scitex_writer._compile._event_log import EVENT_SUCCESS, read_events
from scitex_writer._mcp.utils import run_compile_script

ONE_PAGE_PDF = b"%PDF-1.4\n1 0 obj << /Type /Page >> endobj\n%%EOF\n"


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


# EOF
