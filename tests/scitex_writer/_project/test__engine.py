#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# File: tests/scitex_writer/_project/test__engine.py

"""Installing the writer engine into a workspace that already holds content.

The template here is built from THIS repository's own workspace trees (the
same files a fresh ``ensure_workspace`` clone carries), copied with their
links, so the engine under test is the real one and no network is needed.
"""

from __future__ import annotations

import os
import shutil
from pathlib import Path

import pytest

from scitex_writer._project._engine import (
    EngineInstallError,
    _link_stays_inside,
    has_engine,
    holds_content,
    install_engine,
)
from scitex_writer.workspace_layout import compile_script_relpath

REPO = Path(__file__).resolve().parents[3]
TEMPLATE_ENTRIES = (
    "00_shared",
    "01_manuscript",
    "02_supplementary",
    "03_revision",
    "config",
    "scripts",
    "compile.sh",
)
RESULTS_TEXT = "% the author's results\nAccuracy was \\vclaim{acc}.\n"
TITLE_TEXT = "\\title{A research template paper}\n"


@pytest.fixture
def template(tmp_path: Path) -> Path:
    root = tmp_path / "template"
    root.mkdir()
    for name in TEMPLATE_ENTRIES:
        source = REPO / name
        if source.is_dir():
            shutil.copytree(source, root / name, symlinks=True)
        else:
            shutil.copy2(source, root / name)
    return root


def _content_workspace(project: Path) -> Path:
    """What a research template ships: manuscript text and nothing else."""
    workspace = project / ".scitex" / "writer"
    contents = workspace / "01_manuscript" / "contents"
    (contents / "figures" / "caption_and_media").mkdir(parents=True)
    (workspace / "00_shared").mkdir(parents=True)
    (contents / "results.tex").write_text(RESULTS_TEXT, encoding="utf-8")
    (workspace / "00_shared" / "title.tex").write_text(TITLE_TEXT, encoding="utf-8")
    (contents / "figures" / "caption_and_media" / "01_overview.tex").write_text(
        "\\caption{Overview}\n", encoding="utf-8"
    )
    return workspace


def test_a_content_only_workspace_is_recognised_as_missing_its_engine(tmp_path):
    # Arrange
    workspace = _content_workspace(tmp_path)
    # Act
    state = (holds_content(workspace), has_engine(workspace))
    # Assert
    assert state == (True, False)


def test_install_adds_the_compile_script(tmp_path, template):
    # Arrange
    workspace = _content_workspace(tmp_path / "project")
    # Act
    install_engine(workspace, template)
    # Assert
    assert (workspace / compile_script_relpath("manuscript")).is_file()


def test_install_leaves_the_authors_text_byte_identical(tmp_path, template):
    # Arrange
    workspace = _content_workspace(tmp_path / "project")
    # Act
    install_engine(workspace, template)
    # Assert
    assert (
        (workspace / "01_manuscript/contents/results.tex").read_text(encoding="utf-8"),
        (workspace / "00_shared/title.tex").read_text(encoding="utf-8"),
    ) == (RESULTS_TEXT, TITLE_TEXT)


def test_install_does_not_add_the_template_example_figures(tmp_path, template):
    # Arrange
    workspace = _content_workspace(tmp_path / "project")
    media = workspace / "01_manuscript/contents/figures/caption_and_media"
    # Act
    install_engine(workspace, template)
    # Assert
    assert sorted(p.name for p in media.iterdir() if p.is_file()) == ["01_overview.tex"]


def test_install_keeps_the_compile_scaffold_directories(tmp_path, template):
    # Arrange
    workspace = _content_workspace(tmp_path / "project")
    # Act
    install_engine(workspace, template)
    # Assert
    assert (
        workspace
        / "01_manuscript/contents/figures/caption_and_media/jpg_for_compilation/.gitkeep"
    ).is_file()


def test_install_fills_in_sections_the_template_ships_and_the_author_did_not(
    tmp_path, template
):
    # Arrange
    workspace = _content_workspace(tmp_path / "project")
    # Act
    install_engine(workspace, template)
    # Assert
    assert (workspace / "01_manuscript/contents/highlights.tex").is_file()


def test_install_recreates_relative_template_links(tmp_path, template):
    # Arrange
    workspace = _content_workspace(tmp_path / "project")
    expected = os.readlink(template / "01_manuscript/contents/latex_styles")
    # Act
    install_engine(workspace, template)
    # Assert
    assert os.readlink(workspace / "01_manuscript/contents/latex_styles") == expected


def test_install_skips_a_template_link_that_leaves_the_workspace(tmp_path, template):
    # Arrange: a template link pointing outside, as the repository's own
    # 00_shared/scholar/library does (into the installer's home).
    escaping = template / "00_shared" / "escaping-link"
    escaping.symlink_to(tmp_path / "outside", target_is_directory=True)
    workspace = _content_workspace(tmp_path / "project")
    # Act
    install_engine(workspace, template)
    # Assert
    assert not os.path.lexists(workspace / "00_shared" / "escaping-link")


def test_every_written_path_is_inside_the_workspace(tmp_path, template):
    # Arrange
    workspace = _content_workspace(tmp_path / "project")
    # Act
    written = install_engine(workspace, template)
    # Assert
    assert written and all(workspace in p.parents for p in written)


def test_a_second_install_writes_nothing(tmp_path, template):
    # Arrange
    workspace = _content_workspace(tmp_path / "project")
    install_engine(workspace, template)
    # Act
    again = install_engine(workspace, template)
    # Assert
    assert again == []


def test_reinstall_restores_a_missing_engine_file_and_keeps_an_edit(tmp_path, template):
    # Arrange
    workspace = _content_workspace(tmp_path / "project")
    install_engine(workspace, template)
    edited = "% edited in the Hub editor\n"
    (workspace / "01_manuscript/contents/results.tex").write_text(
        edited, encoding="utf-8"
    )
    (workspace / "01_manuscript/base.tex").unlink()
    # Act
    written = install_engine(workspace, template)
    # Assert
    assert (
        written,
        (workspace / "01_manuscript/contents/results.tex").read_text(encoding="utf-8"),
    ) == ([workspace / "01_manuscript/base.tex"], edited)


def test_install_keeps_executable_compile_scripts_executable(tmp_path, template):
    # Arrange
    workspace = _content_workspace(tmp_path / "project")
    # Act
    install_engine(workspace, template)
    # Assert
    assert os.access(workspace / compile_script_relpath("manuscript"), os.X_OK)


def test_install_refuses_a_workspace_reached_through_a_link(tmp_path, template):
    # Arrange
    real = _content_workspace(tmp_path / "elsewhere")
    project = tmp_path / "project"
    (project / ".scitex").mkdir(parents=True)
    (project / ".scitex" / "writer").symlink_to(real, target_is_directory=True)
    linked = project / ".scitex" / "writer"
    # Act
    attempt = lambda: install_engine(linked, template)  # noqa: E731
    # Assert
    with pytest.raises(EngineInstallError, match="symlink"):
        attempt()


def test_install_writes_nothing_through_a_refused_link(tmp_path, template):
    # Arrange
    real = _content_workspace(tmp_path / "elsewhere")
    project = tmp_path / "project"
    (project / ".scitex").mkdir(parents=True)
    (project / ".scitex" / "writer").symlink_to(real, target_is_directory=True)
    # Act
    try:
        install_engine(project / ".scitex" / "writer", template)
    except EngineInstallError:
        pass
    # Assert
    assert not has_engine(real)


@pytest.mark.parametrize(
    ("rel", "target", "inside"),
    [
        ("01_manuscript/contents/latex_styles", "../../00_shared/latex_styles", True),
        ("00_shared/scholar/library", "/home/someone/.scitex/scholar/library", False),
        ("00_shared/x", "../../outside", False),
        ("a/b/c", "../d", True),
    ],
)
def test_link_containment_is_decided_lexically(rel, target, inside):
    # Arrange
    from pathlib import PurePosixPath

    # Act
    decided = _link_stays_inside(PurePosixPath(rel), target)
    # Assert
    assert decided is inside


# EOF
