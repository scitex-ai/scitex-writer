#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# File: tests/scitex_writer/_django/test_views_pdf_menu.py

"""PDF ops live in a hamburger menu with shortcuts (operator CCT4485).

The six small PDF op icons collapse into one ``#btn-pdf-menu`` hamburger;
every op keeps its button ID (existing action wiring untouched) and gains a
keyboard shortcut, listed both on the menu item (``<kbd>``) and in
Details > Shortcuts. The viewer carries the three zoom/fit ops only.
"""

from __future__ import annotations

import tempfile
from pathlib import Path

from django.test import RequestFactory

from scitex_writer._django import views

_DJANGO_DIR = Path(__file__).resolve().parents[3] / "src" / "scitex_writer" / "_django"
_TEMPLATES = _DJANGO_DIR / "templates" / "writer"
_FRONTEND_SRC = _DJANGO_DIR / "frontend" / "src"
_EDITOR_CSS = _DJANGO_DIR / "static" / "writer" / "css" / "editor.css"

_EDITOR_OPS = [
    "btn-pdf-zoom-out",
    "btn-pdf-fit",
    "btn-pdf-zoom-in",
    "btn-refresh-pdf",
    "btn-pdf-theme",
    "btn-pdf-download",
]
_VIEWER_OPS = ["btn-pdf-zoom-out", "btn-pdf-fit", "btn-pdf-zoom-in"]


def _template(name: str) -> str:
    # Arrange
    return (_TEMPLATES / name).read_text(encoding="utf-8")


def test_editor_preview_actions_have_one_hamburger_not_six_icons():
    # Arrange
    markup = _template("editor.html")
    # Act
    # Assert
    assert 'id="btn-pdf-menu"' in markup
    assert 'id="pdf-menu-list"' in markup
    for op in _EDITOR_OPS:
        assert f'id="{op}"' in markup, f"menu must keep #{op}"


def test_editor_menu_items_carry_shortcut_hints():
    # Arrange
    markup = _template("editor.html")
    # Act
    # Assert
    for hint in ("Ctrl+-", "Ctrl+0", "Ctrl+=", "Ctrl+Shift+R", "Alt+T", "Alt+D"):
        assert hint in markup, f"menu must show {hint}"


def test_viewer_menu_has_zoom_ops_only():
    # Arrange
    markup = _template("viewer.html")
    # Act
    # Assert
    assert 'id="btn-pdf-menu"' in markup
    for op in _VIEWER_OPS:
        assert f'id="{op}"' in markup, f"viewer menu must keep #{op}"
    for op in ("btn-refresh-pdf", "btn-pdf-theme", "btn-pdf-download"):
        assert f'id="{op}"' not in markup


def test_pdf_menu_styles_exist():
    # Arrange
    css = _EDITOR_CSS.read_text(encoding="utf-8")
    # Act
    # Assert
    assert ".pdf-menu-list" in css
    assert ".pdf-menu-item" in css


def test_pdf_menu_module_is_shared_by_editor_and_viewer():
    # Arrange
    module = (_FRONTEND_SRC / "pdf-menu.ts").read_text(encoding="utf-8")
    index = (_FRONTEND_SRC / "index.ts").read_text(encoding="utf-8")
    viewer = (_FRONTEND_SRC / "viewer.ts").read_text(encoding="utf-8")
    details = (_FRONTEND_SRC / "details-panel.ts").read_text(encoding="utf-8")
    # Act
    # Assert
    assert "export function mountPdfMenu" in module
    assert "mountPdfMenu(root)" in index
    assert "mountPdfMenu(root)" in viewer
    for hint in ("PDF zoom in", "PDF fit width", "Refresh PDF", "Cycle PDF theme", "Download PDF"):
        assert hint in details, f"Shortcuts must list {hint}"


def _editor_html(project_dir) -> str:
    request = RequestFactory().get(f"/?working_dir={project_dir}")
    return views.editor_page(request).content.decode()


def test_served_editor_page_renders_the_hamburger():
    # Arrange
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        (root / "01_manuscript" / "contents").mkdir(parents=True)
        (root / "01_manuscript" / "contents" / "abstract.tex").write_text(
            "\\begin{abstract}x\\end{abstract}\n", encoding="utf-8"
        )
        (root / "00_shared").mkdir()
        # Act
        html = _editor_html(root)
    # Assert
    assert 'id="btn-pdf-menu"' in html
    assert 'id="pdf-menu-list"' in html
