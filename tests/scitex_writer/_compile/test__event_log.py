#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
The compile event log: every attempt leaves a record, and a REFUSAL (engine
never started) is never written in the same shape as a FAILURE (engine ran,
no PDF). Exercised through the real entry points -- the runner and the MCP
compile.sh path -- on real scaffolds, with the command executor as the only
seam (so no 2-minute LaTeX build), exactly as test__runner does.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from scitex_writer._compile._event_log import (
    EVENT_ATTEMPT,
    EVENT_FAILURE,
    EVENT_REFUSAL,
    EVENT_SUCCESS,
    FAILURE_REASONS,
    LOG_RELPATH,
    REFUSAL_REASONS,
    events_log_path,
    read_events,
    record_event,
    workspace_for,
)


def _kinds(project) -> list[str]:
    return [e["kind"] for e in read_events(project)]


def _last(project) -> dict:
    return read_events(project)[-1]


class TestVocabulary:
    def test_refusal_and_failure_reasons_never_overlap(self):
        # Arrange
        overlap = REFUSAL_REASONS & FAILURE_REASONS
        # Act
        count = len(overlap)
        # Assert
        assert count == 0

    def test_refusal_with_a_failure_reason_is_rejected(self, tmp_path):
        # Arrange
        kind, reason = EVENT_REFUSAL, "engine-nonzero"
        # Act
        # Assert
        with pytest.raises(ValueError):
            record_event(tmp_path, kind, reason=reason, doc_type="m", entry_point="t")

    def test_failure_with_a_refusal_reason_is_rejected(self, tmp_path):
        # Arrange
        kind, reason = EVENT_FAILURE, "busy"
        # Act
        # Assert
        with pytest.raises(ValueError):
            record_event(tmp_path, kind, reason=reason, doc_type="m", entry_point="t")

    def test_attempt_with_any_reason_is_rejected(self, tmp_path):
        # Arrange
        kind, reason = EVENT_ATTEMPT, "busy"
        # Act
        # Assert
        with pytest.raises(ValueError):
            record_event(tmp_path, kind, reason=reason, doc_type="m", entry_point="t")

    def test_rejected_record_writes_nothing(self, tmp_path):
        # Arrange
        try:
            record_event(
                tmp_path, EVENT_REFUSAL, reason="nope", doc_type="m", entry_point="t"
            )
        except ValueError:
            pass
        # Act
        exists = events_log_path(tmp_path).exists()
        # Assert
        assert exists is False


class TestLocation:
    def test_project_root_resolves_to_nested_workspace(self, tmp_path):
        # Arrange
        nested = tmp_path / ".scitex" / "writer"
        nested.mkdir(parents=True)
        # Act
        resolved = workspace_for(tmp_path)
        # Assert
        assert resolved == nested

    def test_workspace_path_resolves_to_itself(self, tmp_path):
        # Arrange
        workspace = tmp_path
        # Act
        resolved = workspace_for(workspace)
        # Assert
        assert resolved == workspace

    def test_workspace_carrying_the_templates_nested_dir_resolves_to_itself(
        self, tmp_path
    ):
        # Arrange: a real workspace (01_manuscript/) that ALSO ships the
        # template's own .scitex/writer -- the shape that doubled the path
        (tmp_path / "01_manuscript").mkdir()
        (tmp_path / ".scitex" / "writer").mkdir(parents=True)
        # Act
        resolved = workspace_for(tmp_path)
        # Assert
        assert resolved == tmp_path

    def test_project_root_and_workspace_share_one_log(self, tmp_path):
        # Arrange
        nested = tmp_path / ".scitex" / "writer"
        nested.mkdir(parents=True)
        # Act
        record_event(tmp_path, EVENT_ATTEMPT, doc_type="manuscript", entry_point="a")
        record_event(nested, EVENT_ATTEMPT, doc_type="manuscript", entry_point="b")
        # Assert
        assert [e["entry_point"] for e in read_events(nested)] == ["a", "b"]

    def test_log_lives_under_logs_in_the_workspace(self, tmp_path):
        # Arrange
        expected = tmp_path / LOG_RELPATH
        # Act
        path = events_log_path(tmp_path)
        # Assert
        assert path == expected

    def test_each_record_is_one_json_line(self, tmp_path):
        # Arrange
        record_event(tmp_path, EVENT_ATTEMPT, doc_type="manuscript", entry_point="t")
        record_event(
            tmp_path,
            EVENT_FAILURE,
            reason="timeout",
            doc_type="manuscript",
            entry_point="t",
        )
        # Act
        lines = events_log_path(tmp_path).read_text().splitlines()
        # Assert
        assert [json.loads(line)["kind"] for line in lines] == ["attempt", "failure"]

    def test_stderr_is_tailed_not_dumped(self, tmp_path):
        # Arrange
        stderr = "x" * 5_000
        # Act
        rec = record_event(
            tmp_path,
            EVENT_FAILURE,
            reason="engine-nonzero",
            doc_type="manuscript",
            entry_point="t",
            stderr=stderr,
        )
        # Assert
        assert len(rec["stderr_tail"]) == 2_000

    def test_unwritable_log_is_reported_not_raised(self, tmp_path):
        # Arrange: put a FILE where the logs directory must go
        (tmp_path / "logs").write_text("not a directory")
        # Act
        rec = record_event(
            tmp_path, EVENT_ATTEMPT, doc_type="manuscript", entry_point="t"
        )
        # Assert
        assert "log_write_error" in rec

    def test_unwritable_log_reaches_stderr(self, tmp_path, capsys):
        # Arrange
        (tmp_path / "logs").write_text("not a directory")
        # Act
        record_event(tmp_path, EVENT_ATTEMPT, doc_type="manuscript", entry_point="t")
        # Assert
        assert "could not append event log" in capsys.readouterr().err


# ---------------------------------------------------------------------------
# Through the runner (Writer-class path): <workspace>/scripts/shell/compile_*.sh
# ---------------------------------------------------------------------------

pytest.importorskip("git")
from scitex_writer._compile._runner import run_compile  # noqa: E402


class _ExitCode:
    """command_runner seam of run_compile, returning a chosen exit code."""

    def __init__(self, exit_code: int, stderr: str = ""):
        self.exit_code = exit_code
        self.stderr = stderr

    def __call__(self, cmd, verbose=True, timeout=300, stream_output=True):
        return {
            "exit_code": self.exit_code,
            "stdout": "",
            "stderr": self.stderr,
            "success": self.exit_code == 0,
        }


def _write_real_pdf(workspace: Path, pages: int = 3) -> None:
    doc_dir = workspace / "01_manuscript"
    logs = doc_dir / "logs"
    logs.mkdir(parents=True, exist_ok=True)
    body = b"".join(b"/Type /Page\n" for _ in range(pages))
    (doc_dir / "manuscript.pdf").write_bytes(b"%PDF-1.5\n" + body + b"%%EOF\n")
    (logs / "manuscript.log").write_text(
        f"Output written on 01_manuscript/logs/manuscript.pdf ({pages} pages, 1 bytes).\n"
    )


@pytest.fixture
def workspace(valid_project):
    """The shared REAL workspace from conftest (built locally, no clone)."""
    return valid_project


class TestRunnerRecords:
    def test_empty_dir_is_a_validation_refusal(self, tmp_path):
        # Arrange
        runner = _ExitCode(0)
        # Act
        run_compile("manuscript", tmp_path, command_runner=runner)
        # Assert
        assert _kinds(tmp_path) == [EVENT_ATTEMPT, EVENT_REFUSAL]

    def test_validation_refusal_names_its_reason(self, tmp_path):
        # Arrange
        runner = _ExitCode(0)
        # Act
        run_compile("manuscript", tmp_path, command_runner=runner)
        # Assert
        assert _last(tmp_path)["reason"] == "validation"

    def test_unknown_doc_type_is_a_refusal(self, workspace):
        # Arrange
        runner = _ExitCode(0)
        # Act
        run_compile("poster", workspace, command_runner=runner)
        # Assert
        assert _last(workspace)["reason"] == "unknown-doc-type"

    def test_nonzero_exit_is_an_engine_failure(self, workspace):
        # Arrange
        runner = _ExitCode(1, "! Undefined")
        # Act
        run_compile("manuscript", workspace, command_runner=runner)
        # Assert
        assert _kinds(workspace) == [EVENT_ATTEMPT, EVENT_FAILURE]

    def test_engine_failure_names_its_reason_and_exit_code(self, workspace):
        # Arrange
        runner = _ExitCode(1)
        # Act
        run_compile("manuscript", workspace, command_runner=runner)
        # Assert
        rec = _last(workspace)
        assert (rec["reason"], rec["exit_code"]) == ("engine-nonzero", 1)

    def test_engine_failure_keeps_the_stderr_tail(self, workspace):
        # Arrange
        runner = _ExitCode(1, "! Undefined")
        # Act
        run_compile("manuscript", workspace, command_runner=runner)
        # Assert
        assert "! Undefined" in _last(workspace)["stderr_tail"]

    def test_exit_zero_without_a_pdf_is_named_as_such(self, workspace):
        # Arrange
        runner = _ExitCode(0)
        # Act
        run_compile("manuscript", workspace, command_runner=runner)
        # Assert
        assert _last(workspace)["reason"] == "exit-zero-no-pdf"

    def test_promoted_exit_without_a_pdf_is_named_as_such(self, workspace):
        # Arrange
        runner = _ExitCode(3)
        # Act
        run_compile("manuscript", workspace, command_runner=runner)
        # Assert
        assert _last(workspace)["reason"] == "promoted-without-pdf"

    def test_real_pdf_is_a_success_with_pages(self, workspace):
        # Arrange
        _write_real_pdf(workspace, pages=3)
        # Act
        run_compile("manuscript", workspace, command_runner=_ExitCode(0))
        # Assert
        rec = _last(workspace)
        assert (rec["kind"], rec["pages"]) == (EVENT_SUCCESS, 3)

    def test_attempt_and_outcome_share_an_attempt_id(self, workspace):
        # Arrange
        runner = _ExitCode(1)
        # Act
        run_compile("manuscript", workspace, command_runner=runner)
        # Assert
        first, last = read_events(workspace)
        assert first["attempt_id"] == last["attempt_id"]

    def test_records_name_the_runner_entry_point(self, workspace):
        # Arrange
        runner = _ExitCode(1)
        # Act
        run_compile("manuscript", workspace, command_runner=runner)
        # Assert
        assert {e["entry_point"] for e in read_events(workspace)} == {"runner"}


# ---------------------------------------------------------------------------
# Through the MCP / CLI / Django path: <workspace>/compile.sh
# ---------------------------------------------------------------------------

from scitex_writer._mcp.utils import run_compile_script  # noqa: E402


def _compile_sh(workspace: Path, body: str) -> None:
    script = workspace / "compile.sh"
    script.write_text("#!/bin/bash\n" + body + "\n")
    script.chmod(0o755)


class TestMcpPathRecords:
    def test_missing_compile_sh_is_a_workspace_refusal(self, tmp_path):
        # Arrange: nothing on disk
        workspace = tmp_path
        # Act
        run_compile_script(workspace, "manuscript")
        # Assert
        assert _kinds(workspace) == [EVENT_ATTEMPT, EVENT_REFUSAL]

    def test_missing_compile_sh_names_its_reason(self, tmp_path):
        # Arrange
        workspace = tmp_path
        # Act
        run_compile_script(workspace, "manuscript")
        # Assert
        assert _last(workspace)["reason"] == "workspace-missing"

    def test_nonzero_exit_is_an_engine_failure(self, tmp_path):
        # Arrange
        _compile_sh(tmp_path, "echo 'boom' >&2; exit 2")
        # Act
        run_compile_script(tmp_path, "manuscript")
        # Assert
        rec = _last(tmp_path)
        assert (rec["kind"], rec["reason"], rec["exit_code"]) == (
            EVENT_FAILURE,
            "engine-nonzero",
            2,
        )

    def test_engine_failure_keeps_stderr(self, tmp_path):
        # Arrange
        _compile_sh(tmp_path, "echo 'boom' >&2; exit 2")
        # Act
        run_compile_script(tmp_path, "manuscript")
        # Assert
        assert "boom" in _last(tmp_path)["stderr_tail"]

    def test_exit_zero_is_a_success(self, tmp_path):
        # Arrange
        _compile_sh(tmp_path, "exit 0")
        # Act
        run_compile_script(tmp_path, "manuscript")
        # Assert
        assert _kinds(tmp_path) == [EVENT_ATTEMPT, EVENT_SUCCESS]

    def test_timeout_is_a_failure_named_timeout(self, tmp_path):
        # Arrange
        _compile_sh(tmp_path, "sleep 5")
        # Act
        run_compile_script(tmp_path, "manuscript", timeout=1)
        # Assert
        assert _last(tmp_path)["reason"] == "timeout"

    def test_records_name_the_mcp_entry_point(self, tmp_path):
        # Arrange
        _compile_sh(tmp_path, "exit 0")
        # Act
        run_compile_script(tmp_path, "manuscript")
        # Assert
        assert {e["entry_point"] for e in read_events(tmp_path)} == {"mcp"}


class TestRefusalAndFailureAreDistinguishable:
    """The lesson of 2026-09-05: a refusal shown as a compile error. The two
    records for the same doc_type must differ in KIND, not just in wording."""

    def test_refusal_and_failure_records_differ_in_kind(self, tmp_path):
        # Arrange: one refusal (no compile.sh) then one failure (compile.sh exits 1)
        run_compile_script(tmp_path, "manuscript")
        _compile_sh(tmp_path, "exit 1")
        run_compile_script(tmp_path, "manuscript")
        # Act
        outcomes = [e for e in read_events(tmp_path) if e["kind"] != EVENT_ATTEMPT]
        # Assert
        assert [e["kind"] for e in outcomes] == [EVENT_REFUSAL, EVENT_FAILURE]

    def test_refusal_carries_no_exit_code(self, tmp_path):
        # Arrange: no compile.sh
        workspace = tmp_path
        # Act
        run_compile_script(workspace, "manuscript")
        # Assert
        assert _last(workspace)["exit_code"] is None

    def test_failure_carries_an_exit_code(self, tmp_path):
        # Arrange
        _compile_sh(tmp_path, "exit 1")
        # Act
        run_compile_script(tmp_path, "manuscript")
        # Assert
        assert _last(tmp_path)["exit_code"] == 1


# EOF
