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


def test_new_render_format_does_not_reuse_the_legacy_preview_pdf(tmp_path, monkeypatch):
    # Arrange: an old, valid artifact remains in place under the old cache key.
    import hashlib
    from types import SimpleNamespace
    import scitex_writer
    from scitex_writer import compile as writer_compile
    root = tmp_path / "owned"
    (root / ".preview").mkdir(parents=True)
    (root / "abstract.tex").write_text("Finding verified.")
    values = ["abstract.tex", "Finding verified.", "light", scitex_writer.__version__]
    old_id = hashlib.sha256(json.dumps(values, ensure_ascii=False).encode()).hexdigest()[:32]
    old_pdf = root / ".preview" / f"section-{old_id}.pdf"
    old_pdf.write_bytes(b"owned legacy artifact")
    calls = []

    def own_compiler(content, **kwargs):
        calls.append(kwargs["name"])
        (root / ".preview" / (kwargs["name"] + ".pdf")).write_bytes(b"owned new artifact")
        return SimpleNamespace(success=True, message="", stdout="", stderr="", temp_dir=None)

    monkeypatch.setattr(writer_compile, "content", own_compiler)
    payload = json.dumps({"section_path": values[0], "content": values[1]})
    # Act: repeat the same request; only the new-format artifact is cached.
    responses = [handle_section_preview(RequestFactory().post(
        "/api/preview", data=payload, content_type="application/json",
    ), ProjectState(root)) for _ in range(2)]
    result = [json.loads(response.content) for response in responses]
    # Assert
    assert (len(calls), result[0]["cached"], result[1]["cached"],
            result[0]["preview_id"] != old_id, old_pdf.read_bytes()) == (
                1, False, True, True, b"owned legacy artifact",
            )
