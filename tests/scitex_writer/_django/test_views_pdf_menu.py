#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# File: tests/scitex_writer/_django/test_views_pdf_menu.py

"""PDF ops live in a hamburger menu with shortcuts (operator CCT4485).

The six small PDF op icons collapse into one ``#btn-pdf-menu`` hamburger;
every op keeps its button ID (existing action wiring untouched) and gains a
keyboard shortcut, listed both on the menu item (``<kbd>``) and in
Details > Shortcuts. The viewer carries the three zoom/fit ops only.

STX-TQ007: one assertion per test (see 3af127ed) — membership checks are
split into one test per op / hint rather than loops with asserts.
"""

from __future__ import annotations

import pytest

import tempfile
from pathlib import Path

from django.test import RequestFactory

from scitex_writer._django import views

_DJANGO_DIR = Path(__file__).resolve().parents[3] / "src" / "scitex_writer" / "_django"
_TEMPLATES = _DJANGO_DIR / "templates" / "writer"
_FRONTEND_SRC = _DJANGO_DIR / "frontend" / "src"
_EDITOR_CSS = _DJANGO_DIR / "static" / "writer" / "css" / "editor.css"


def _template(name: str) -> str:
    # Arrange
    return (_TEMPLATES / name).read_text(encoding="utf-8")


@pytest.fixture
def editor_markup() -> str:
    # Arrange: the editor template on disk.
    # Act: exercise the real markup.
    return _template("editor.html")


@pytest.fixture
def viewer_markup() -> str:
    # Arrange: the viewer template on disk.
    # Act: exercise the real markup.
    return _template("viewer.html")


def test_editor_preview_actions_have_the_hamburger(editor_markup):
    # Arrange (fixture builds the editor markup)
    # Act
    # Assert
    assert 'id="btn-pdf-menu"' in editor_markup


def test_editor_menu_has_the_menu_list(editor_markup):
    # Arrange (fixture builds the editor markup)
    # Act
    # Assert
    assert 'id="pdf-menu-list"' in editor_markup


@pytest.mark.parametrize("op", ["btn-pdf-zoom-out", "btn-pdf-fit", "btn-pdf-zoom-in", "btn-refresh-pdf", "btn-pdf-theme", "btn-pdf-download"])
def test_editor_menu_keeps_op_button_id(editor_markup, op):
    # Arrange (fixture builds the editor markup)
    # Act
    # Assert
    assert f'id="{op}"' in editor_markup


@pytest.mark.parametrize("hint", ["Ctrl+-", "Ctrl+0", "Ctrl+=", "Ctrl+Shift+R", "Alt+T", "Alt+D"])
def test_editor_menu_item_shows_shortcut_hint(editor_markup, hint):
    # Arrange (fixture builds the editor markup)
    # Act
    # Assert
    assert hint in editor_markup


def test_viewer_menu_has_the_hamburger(viewer_markup):
    # Arrange (fixture builds the viewer markup)
    # Act
    # Assert
    assert 'id="btn-pdf-menu"' in viewer_markup


@pytest.mark.parametrize("op", ["btn-pdf-zoom-out", "btn-pdf-fit", "btn-pdf-zoom-in"])
def test_viewer_menu_keeps_zoom_op_button_id(viewer_markup, op):
    # Arrange (fixture builds the viewer markup)
    # Act
    # Assert
    assert f'id="{op}"' in viewer_markup


@pytest.mark.parametrize("op", ["btn-refresh-pdf", "btn-pdf-theme", "btn-pdf-download"])
def test_viewer_menu_omits_editor_only_op(op, viewer_markup):
    # Arrange (fixture builds the viewer markup)
    # Act
    # Assert
    assert f'id="{op}"' not in viewer_markup


def test_pdf_menu_list_styles_exist():
    # Arrange
    css = _EDITOR_CSS.read_text(encoding="utf-8")
    # Act
    # Assert
    assert ".pdf-menu-list" in css


def test_pdf_menu_item_styles_exist():
    # Arrange
    css = _EDITOR_CSS.read_text(encoding="utf-8")
    # Act
    # Assert
    assert ".pdf-menu-item" in css


def test_pdf_menu_module_exports_mount():
    # Arrange
    module = (_FRONTEND_SRC / "pdf-menu.ts").read_text(encoding="utf-8")
    # Act
    # Assert
    assert "export function mountPdfMenu" in module


def test_editor_entry_mounts_pdf_menu():
    # Arrange
    index = (_FRONTEND_SRC / "index.ts").read_text(encoding="utf-8")
    # Act
    # Assert
    assert "mountPdfMenu(root)" in index


def test_viewer_entry_mounts_pdf_menu():
    # Arrange
    viewer = (_FRONTEND_SRC / "viewer.ts").read_text(encoding="utf-8")
    # Act
    # Assert
    assert "mountPdfMenu(root)" in viewer


@pytest.mark.parametrize("hint", ["PDF zoom in", "PDF fit width", "Refresh PDF", "Cycle PDF theme", "Download PDF"])
def test_details_shortcuts_list_pdf_shortcut(hint):
    # Arrange
    details = (_FRONTEND_SRC / "details-panel.ts").read_text(encoding="utf-8")
    # Act
    # Assert
    assert hint in details


def _editor_html(project_dir) -> str:
    request = RequestFactory().get(f"/?working_dir={project_dir}")
    return views.editor_page(request).content.decode()


def test_served_editor_page_renders_the_hamburger_trigger():
    # Arrange
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        (root / "01_manuscript" / "contents").mkdir(parents=True)
        (root / "01_manuscript" / "contents" / "abstract.tex").write_text(
            "\\\\begin{abstract}x\\\\end{abstract}\\n", encoding="utf-8"
        )
        (root / "00_shared").mkdir()
        # Act
        html = _editor_html(root)
    # Assert
    assert 'id="btn-pdf-menu"' in html


def test_served_editor_page_renders_the_menu_list():
    # Arrange
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        (root / "01_manuscript" / "contents").mkdir(parents=True)
        (root / "01_manuscript" / "contents" / "abstract.tex").write_text(
            "\\\\begin{abstract}x\\\\end{abstract}\\n", encoding="utf-8"
        )
        (root / "00_shared").mkdir()
        # Act
        html = _editor_html(root)
    # Assert
    assert 'id="pdf-menu-list"' in html
