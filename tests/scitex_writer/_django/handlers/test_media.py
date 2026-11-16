"""Real media lists retain mount and authorized project on thumbnail requests."""

from __future__ import annotations

import json
from urllib.parse import parse_qs, urlsplit

import pytest
from django.test import RequestFactory
from PIL import Image
from scitex_sdk.host import ProjectAccess

from scitex_writer._django.handlers.media import (
    handle_figures,
    handle_tables,
    handle_thumbnail,
)
from scitex_writer._django.services import ProjectState


@pytest.fixture
def media_project(tmp_path):
    for kind in ("figures", "tables"):
        root = tmp_path / "01_manuscript/contents" / kind / "caption_and_media"
        root.mkdir(parents=True)
        (root / "mnist_demo.tex").write_text("\\caption{Demo}\\label{demo:mnist}")
        Image.new("RGB", (8, 8), "navy").save(root / "mnist_demo.png")
    return ProjectState(project_dir=tmp_path)


@pytest.mark.parametrize(
    "kind,handler", [("figures", handle_figures), ("tables", handle_tables)]
)
def test_mounted_thumbnail_uses_authorized_project(media_project, kind, handler):
    # Arrange
    request = RequestFactory().get(f"/custom/writer/api/{kind}?project=untrusted")
    request.writer_project_access = ProjectAccess(
        id="owner/mnist", name="mnist", root=media_project.project_dir
    )
    # Act
    response = handler(request, media_project)
    url = urlsplit(json.loads(response.content)[kind][0]["thumbnail_url"])
    query = parse_qs(url.query)
    # Assert
    assert (url.path, query["project"], query["kind"], query["path"]) == (
        "/custom/writer/api/thumbnail",
        ["owner/mnist"],
        [kind],
        [f"01_manuscript/contents/{kind}/caption_and_media/mnist_demo.png"],
    )


@pytest.mark.parametrize(
    "kind,handler", [("figures", handle_figures), ("tables", handle_tables)]
)
def test_standalone_thumbnail_retains_working_directory(media_project, kind, handler):
    # Arrange
    request = RequestFactory().get(f"/api/{kind}")
    # Act
    response = handler(request, media_project)
    query = parse_qs(
        urlsplit(json.loads(response.content)[kind][0]["thumbnail_url"]).query
    )
    # Assert
    assert query["working_dir"] == [str(media_project.project_dir)]


def test_listed_thumbnail_serves_real_png(media_project):
    # Arrange
    request = RequestFactory().get("/custom/writer/api/figures")
    request.writer_project_access = ProjectAccess(
        id="owner/mnist", name="mnist", root=media_project.project_dir
    )
    # Act
    listed = handle_figures(request, media_project)
    url = json.loads(listed.content)["figures"][0]["thumbnail_url"]
    response = handle_thumbnail(RequestFactory().get(url), media_project)
    try:
        payload = b"".join(response.streaming_content)
    finally:
        response.close()
    # Assert
    assert response.status_code == 200 and payload.startswith(b"\x89PNG\r\n\x1a\n")


def test_empty_document_has_no_figure_entries(tmp_path):
    # Arrange
    project = ProjectState(project_dir=tmp_path)
    # Act
    response = handle_figures(RequestFactory().get("/api/figures"), project)
    # Assert
    assert json.loads(response.content)["figures"] == []


def test_caption_without_matching_image_has_explicit_missing_media(tmp_path):
    # Arrange
    folder = tmp_path / "01_manuscript/contents/figures/caption_and_media"
    folder.mkdir(parents=True)
    (folder / "caption_only.tex").write_text(
        r"\caption{Missing image}\label{fig:missing}"
    )
    project = ProjectState(project_dir=tmp_path)
    # Act
    response = handle_figures(RequestFactory().get("/api/figures"), project)
    figure = json.loads(response.content)["figures"][0]
    # Assert
    assert (figure["label"], figure["media_path"], figure["thumbnail_url"]) == (
        "fig:missing",
        None,
        None,
    )


def test_image_without_caption_is_not_a_figure_entry(tmp_path):
    # Arrange
    folder = tmp_path / "01_manuscript/contents/figures/caption_and_media"
    folder.mkdir(parents=True)
    Image.new("RGB", (8, 8), "navy").save(folder / "orphan.png")
    project = ProjectState(project_dir=tmp_path)
    # Act
    response = handle_figures(RequestFactory().get("/api/figures"), project)
    # Assert
    assert json.loads(response.content)["figures"] == []
