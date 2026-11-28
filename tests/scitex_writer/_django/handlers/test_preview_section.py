"""Preview validation stops confined-path failures before any compiler runs."""

import json

import pytest
from django.test import RequestFactory

from scitex_writer._django.handlers.preview import (
    handle_section_pdf,
    handle_section_preview,
)
from scitex_writer._django.services import ProjectState


@pytest.mark.parametrize("body", ["null", "[]", "not-json", '{}'])
def test_malformed_preview_requests_are_rejected(tmp_path, body):
    # Arrange
    project = ProjectState(tmp_path)
    request = RequestFactory().post("/api/preview", data=body, content_type="application/json")
    # Act
    response = handle_section_preview(request, project)
    # Assert
    assert response.status_code == 400


def test_section_outside_project_is_refused_before_compilation(tmp_path):
    # Arrange
    project = ProjectState(tmp_path / "owned")
    project.project_dir.mkdir()
    foreign = tmp_path / "foreign.tex"
    foreign.write_text("private")
    request = RequestFactory().post("/api/preview", data=json.dumps({"section_path": "../foreign.tex", "content": "ignored"}), content_type="application/json")
    # Act
    response = handle_section_preview(request, project)
    # Assert
    assert response.status_code == 403


def test_preview_directory_cannot_redirect_output_outside_project(tmp_path):
    # Arrange
    root = tmp_path / "owned"
    root.mkdir()
    foreign = tmp_path / "foreign"
    foreign.mkdir()
    (root / "abstract.tex").write_text("Abstract")
    (root / ".preview").symlink_to(foreign, target_is_directory=True)
    request = RequestFactory().post("/api/preview", data=json.dumps({"section_path": "abstract.tex", "content": "Abstract"}), content_type="application/json")
    # Act
    response = handle_section_preview(request, ProjectState(root))
    # Assert
    assert response.status_code == 403


@pytest.mark.parametrize("preview_id", ["../foreign", "", "/tmp/foreign.pdf"])
def test_preview_download_accepts_only_server_artifact_ids(tmp_path, preview_id):
    # Arrange
    request = RequestFactory().get("/api/preview/pdf", {"preview_id": preview_id})
    # Act
    response = handle_section_pdf(request, ProjectState(tmp_path))
    # Assert
    assert response.status_code == 403


def test_preview_download_cannot_follow_a_foreign_artifact_symlink(tmp_path):
    # Arrange
    root = tmp_path / "owned"
    (root / ".preview").mkdir(parents=True)
    foreign = tmp_path / "foreign.pdf"
    foreign.write_bytes(b"private")
    artifact_id = "a" * 32
    (root / ".preview" / f"section-{artifact_id}.pdf").symlink_to(foreign)
    request = RequestFactory().get("/api/preview/pdf", {"preview_id": artifact_id})
    # Act
    response = handle_section_pdf(request, ProjectState(root))
    # Assert
    assert response.status_code == 403


def test_engine_error_reaches_preview_diagnostics(tmp_path, monkeypatch):
    # Arrange
    from types import SimpleNamespace
    from scitex_writer import compile as writer_compile

    path = "abstract.tex"
    (tmp_path / path).write_text("Draft")
    log = "! Undefined control sequence.\nl.3 \\unknowncommand\n"
    result = SimpleNamespace(
        success=False, message="Compilation failed with exit code 12",
        stdout=log, stderr="", exit_code=12, temp_dir=None,
    )
    monkeypatch.setattr(writer_compile, "content", lambda *args, **kwargs: result)
    request = RequestFactory().post("/api/preview", {"section_path": path, "content": "Draft"}, content_type="application/json")
    # Act
    reply = json.loads(handle_section_preview(request, ProjectState(tmp_path)).content)
    # Assert
    assert (reply["success"], reply["diagnostics"]["items"][0]["cause"], reply["log"].strip()) == (
        False, "undefined-control-sequence", log.strip()
    )
