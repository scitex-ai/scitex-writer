#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# File: tests/scitex_writer/_django/handlers/test_compile.py

"""The editor's compile status carries diagnostics and the full log."""

from __future__ import annotations

import json

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


# EOF
