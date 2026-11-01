#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# File: tests/scitex_writer/_django/handlers/test_compile.py

"""The editor's compile status carries diagnostics and the full log."""

from __future__ import annotations

import json
import sys

import pytest

pytest.importorskip("django")
from django.test import RequestFactory  # noqa: E402

from scitex_writer._django.handlers.compile import (  # noqa: E402
    _do_compile,
    _full_log_text,
    handle_compile_status,
)
from scitex_writer._django.services import ProjectState  # noqa: E402


@pytest.fixture
def project(tmp_path):
    return ProjectState(project_dir=tmp_path)


def _status_payload(project) -> dict:
    response = handle_compile_status(
        RequestFactory().get("/api/compile/status"), project
    )
    return json.loads(response.content)


def test_refused_compile_status_carries_diagnostics(project):
    # Arrange
    _do_compile(project, "not-a-doc-type", draft=False, dark_mode=False)
    # Act
    payload = _status_payload(project)
    # Assert
    assert payload["result"]["diagnostics"]["report"]["ok"] is False


def test_refused_compile_status_log_is_never_empty(project):
    # Arrange
    _do_compile(project, "not-a-doc-type", draft=False, dark_mode=False)
    # Act
    payload = _status_payload(project)
    # Assert
    assert "Unknown doc_type" in payload["log"]


def test_full_log_includes_the_latex_log_named_by_diagnostics(project):
    # Arrange
    logs = project.project_dir / "01_manuscript" / "logs"
    logs.mkdir(parents=True)
    (logs / "manuscript.log").write_text("! Undefined control sequence.\n")
    result = {
        "stdout": "compile.sh output",
        "diagnostics": {"log_path": "01_manuscript/logs/manuscript.log"},
    }
    # Act
    text = _full_log_text(project, result)
    # Assert
    assert "! Undefined control sequence." in text


class _CompileBoundaryReached(BaseException):
    """Stop the real call before the compile-script body runs."""


@pytest.fixture
def compile_workspace(project):
    for name in ("00_shared", "01_manuscript", "02_supplementary", "03_revision"):
        (project.project_dir / name).mkdir()
    (project.project_dir / "00_shared/synthetic-interface-input.txt").write_text(
        "Synthetic input.\n"
    )
    return project


def _capture_editor_compile(project, doc_type, draft, dark_mode):
    from scitex_writer._mcp.utils import run_compile_script

    calls = []
    previous = sys.gettrace()

    def observe(frame, event, arg):
        if event == "call" and frame.f_code is run_compile_script.__code__:
            calls.append(dict(frame.f_locals))
            raise _CompileBoundaryReached
        return observe

    project._compiling = True
    sys.settrace(observe)
    try:
        _do_compile(project, doc_type, draft, dark_mode)
    except _CompileBoundaryReached:
        pass
    finally:
        sys.settrace(previous)
    return calls


@pytest.mark.parametrize("doc_type", ["supplementary", "revision"])
@pytest.mark.parametrize("draft", [False, True])
@pytest.mark.parametrize("dark_mode", [False, True])
def test_editor_document_compile_forwards_selected_theme(
    compile_workspace, doc_type, draft, dark_mode
):
    # Arrange
    project = compile_workspace
    # Act
    calls = _capture_editor_compile(project, doc_type, draft, dark_mode)
    # Assert
    assert calls[0]["dark_mode"] is dark_mode


@pytest.mark.parametrize("doc_type", ["supplementary", "revision"])
@pytest.mark.parametrize("draft", [False, True])
@pytest.mark.parametrize("dark_mode", [False, True])
def test_editor_document_compile_forwards_selected_draft(
    compile_workspace, doc_type, draft, dark_mode
):
    # Arrange
    project = compile_workspace
    # Act
    calls = _capture_editor_compile(project, doc_type, draft, dark_mode)
    # Assert
    assert calls[0]["draft"] is draft


@pytest.mark.parametrize("doc_type", ["supplementary", "revision"])
@pytest.mark.parametrize("draft", [False, True])
@pytest.mark.parametrize("dark_mode", [False, True])
def test_editor_document_compile_forwards_selected_document(
    compile_workspace, doc_type, draft, dark_mode
):
    # Arrange
    project = compile_workspace
    # Act
    calls = _capture_editor_compile(project, doc_type, draft, dark_mode)
    # Assert
    assert calls[0]["doc_type"] == doc_type


@pytest.mark.parametrize("doc_type", ["supplementary", "revision"])
@pytest.mark.parametrize("draft", [False, True])
@pytest.mark.parametrize("dark_mode", [False, True])
def test_editor_document_compile_keeps_engine_quiet(
    compile_workspace, doc_type, draft, dark_mode
):
    # Arrange
    project = compile_workspace
    # Act
    calls = _capture_editor_compile(project, doc_type, draft, dark_mode)
    # Assert
    assert calls[0]["quiet"] is True


# EOF
