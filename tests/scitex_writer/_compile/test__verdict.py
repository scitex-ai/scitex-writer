#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# File: tests/scitex_writer/_compile/test__verdict.py

"""One verdict, two compile paths — and proof that they are ONE thing.

The two paths disagreed for real: a clean exit that produced nothing was
`exit-zero-no-pdf` to the runner and `"success": True` with `output_pdf: None`
to `run_compile_script`. The fix is deliberately not "make them agree" — two
verdicts that agree today are one local edit away from disagreeing tomorrow.
Neither path judges anything any more; both call this module, and the guards at
the bottom of this file are about THAT relationship rather than about two
implementations happening to match
(card ``scitex-writer-standalone-readiness-measured-blockers-20260902``, the
2026-09-06 14:00Z note).
"""

from pathlib import Path

import pytest

from scitex_writer._compile._artifacts import EXIT_PROMOTED_WITH_WARNINGS
from scitex_writer._compile._event_log import FAILURE_REASONS
from scitex_writer._compile._verdict import (
    REASON_ENGINE_NONZERO,
    REASON_EXIT_ZERO_NO_PDF,
    REASON_PROMOTED_WITHOUT_PDF,
    compile_verdict,
    engine_finished,
)

_PACKAGE = Path(__file__).resolve().parents[3] / "src" / "scitex_writer"
_RUNNER = _PACKAGE / "_compile" / "_runner.py"
_MCP_UTILS = _PACKAGE / "_mcp" / "utils.py"


def _pdf_with_pages(path: Path, pages: int) -> Path:
    """A PDF carrying ``pages`` page objects (what pages_in_pdf counts)."""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(b"%PDF-1.5\n" + b"/Type /Page\n" * pages + b"%%EOF\n")
    return path


def _log_naming_pages(path: Path, pages: int) -> Path:
    """pdfTeX's per-run 'I finalized a PDF' line."""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        f"Output written on {path.parent}/manuscript.pdf ({pages} pages, 129061 bytes).\n"
    )
    return path


# ---------------------------------------------------------------------------
# the artifact decides
# ---------------------------------------------------------------------------


def test_a_clean_exit_with_a_real_pdf_is_a_success(tmp_path: Path):
    # Arrange
    pdf = _pdf_with_pages(tmp_path / "manuscript.pdf", 1)
    # Act
    verdict = compile_verdict(0, pdf)
    # Assert
    assert verdict.success is True


def test_a_clean_exit_without_a_pdf_is_a_failure(tmp_path: Path):
    # Arrange
    # This is the case the MCP path used to call "compiled successfully": no
    # artifact at all, exit 0, and a response with output_pdf None.
    missing = tmp_path / "manuscript.pdf"
    # Act
    verdict = compile_verdict(0, missing)
    # Assert
    assert verdict.success is False


def test_a_clean_exit_over_a_zero_page_husk_is_a_failure(tmp_path: Path):
    # Arrange: the file exists and is a PDF, with no pages in it — the shape the
    # June 2026 false-success incident was about.
    husk = _pdf_with_pages(tmp_path / "manuscript.pdf", 0)
    # Act
    verdict = compile_verdict(0, husk)
    # Assert
    assert verdict.success is False


def test_a_clean_exit_without_a_pdf_but_a_log_claiming_pages_still_fails(
    tmp_path: Path,
):
    # Arrange: a log is not an artifact. produced_page_count already refuses to
    # take one's word; this pins the verdict above it.
    missing = tmp_path / "manuscript.pdf"
    _log_naming_pages(tmp_path / "logs" / "manuscript.log", 7)
    # Act
    verdict = compile_verdict(0, missing)
    # Assert
    assert verdict.pages == 0


def test_the_log_names_the_page_count_when_it_can(tmp_path: Path):
    # Arrange: one page object on disk, a log that says seven — the log is this
    # run's evidence, the PDF may be a leftover.
    pdf = _pdf_with_pages(tmp_path / "manuscript.pdf", 1)
    log = _log_naming_pages(tmp_path / "logs" / "manuscript.log", 7)
    # Act
    verdict = compile_verdict(0, pdf, log)
    # Assert
    assert verdict.pages == 7


# ---------------------------------------------------------------------------
# the promoted exit is a success that is not clean
# ---------------------------------------------------------------------------


def test_a_promoted_exit_with_a_real_pdf_is_a_success(tmp_path: Path):
    # Arrange
    pdf = _pdf_with_pages(tmp_path / "manuscript.pdf", 7)
    # Act
    verdict = compile_verdict(EXIT_PROMOTED_WITH_WARNINGS, pdf)
    # Assert
    assert verdict.success is True


def test_a_promoted_success_says_so_in_a_warning(tmp_path: Path):
    # Arrange
    pdf = _pdf_with_pages(tmp_path / "manuscript.pdf", 7)
    # Act
    verdict = compile_verdict(EXIT_PROMOTED_WITH_WARNINGS, pdf)
    # Assert
    assert "PROMOTED" in (verdict.warning or "")


def test_a_promoted_success_has_no_failure_reason(tmp_path: Path):
    # Arrange
    pdf = _pdf_with_pages(tmp_path / "manuscript.pdf", 7)
    # Act
    verdict = compile_verdict(EXIT_PROMOTED_WITH_WARNINGS, pdf)
    # Assert
    assert verdict.detail is None


def test_a_promoted_exit_without_a_pdf_is_a_failure(tmp_path: Path):
    # Arrange
    missing = tmp_path / "manuscript.pdf"
    # Act
    verdict = compile_verdict(EXIT_PROMOTED_WITH_WARNINGS, missing)
    # Assert
    assert verdict.detail == REASON_PROMOTED_WITHOUT_PDF


def test_a_promoted_failure_is_not_a_success_with_a_warning(tmp_path: Path):
    # Arrange: the warning belongs to a PROMOTED SUCCESS. Emitting it beside a
    # failure would tell the user a PDF exists when none does.
    missing = tmp_path / "manuscript.pdf"
    # Act
    verdict = compile_verdict(EXIT_PROMOTED_WITH_WARNINGS, missing)
    # Assert
    assert verdict.warning is None


# ---------------------------------------------------------------------------
# the engine died
# ---------------------------------------------------------------------------


def test_a_nonzero_exit_is_a_failure(tmp_path: Path):
    # Arrange
    pdf = _pdf_with_pages(tmp_path / "manuscript.pdf", 3)
    # Act
    verdict = compile_verdict(1, pdf)
    # Assert
    assert verdict.success is False


def test_a_nonzero_exit_does_not_look_for_an_artifact(tmp_path: Path):
    # Arrange: a PDF IS on disk, and the engine still died. A file left by an
    # earlier run must not be promoted into this run's success.
    pdf = _pdf_with_pages(tmp_path / "manuscript.pdf", 3)
    # Act
    verdict = compile_verdict(1, pdf)
    # Assert
    assert verdict.pages == 0


def test_a_nonzero_exit_names_itself_as_the_reason(tmp_path: Path):
    # Arrange
    # Act
    verdict = compile_verdict(2, None)
    # Assert
    assert verdict.detail == REASON_ENGINE_NONZERO


# ---------------------------------------------------------------------------
# the reasons are the event log's reasons
# ---------------------------------------------------------------------------


def test_every_failure_reason_belongs_to_the_event_log_vocabulary():
    # Arrange: the record a workspace keeps and the verdict a caller reads must
    # not be two different words for one run.
    reasons = {
        REASON_ENGINE_NONZERO,
        REASON_EXIT_ZERO_NO_PDF,
        REASON_PROMOTED_WITHOUT_PDF,
    }
    # Act
    unknown = reasons - FAILURE_REASONS
    # Assert
    assert unknown == set()


@pytest.mark.parametrize(
    ("exit_code", "finished"),
    [(0, True), (EXIT_PROMOTED_WITH_WARNINGS, True), (1, False), (12, False)],
)
def test_engine_finished_matches_the_verdict_rule(exit_code: int, finished: bool):
    # Arrange
    # Act
    result = engine_finished(exit_code)
    # Assert
    assert result is finished


# ---------------------------------------------------------------------------
# the two paths are ONE thing, not two that agree
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("path", [_RUNNER, _MCP_UTILS], ids=["runner", "mcp"])
def test_neither_path_spells_the_verdict_locally(path: Path):
    # Arrange: this is the guard that survives a later "simplification". A test
    # comparing two implementations' outputs keeps passing after someone
    # re-adds a local judgement, so long as the copy agrees today; forbidding
    # the local spelling fails the moment a second rule appears.
    forbidden = (
        "EXIT_PROMOTED_WITH_WARNINGS",
        "_PROMOTED_WARNING",
        "produced_page_count",
        "returncode == 0",
    )
    # Act
    body = path.read_text(encoding="utf-8")
    # Assert
    assert [token for token in forbidden if token in body] == []


@pytest.mark.parametrize("path", [_RUNNER, _MCP_UTILS], ids=["runner", "mcp"])
def test_both_paths_call_the_shared_verdict(path: Path):
    # Arrange
    call = "compile_verdict("
    # Act
    body = path.read_text(encoding="utf-8")
    # Assert
    assert call in body


# EOF
