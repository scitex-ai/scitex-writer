#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# File: tests/scitex_writer/_django/test_editor_narrow_and_dock.py

"""Editor-v2 at phone width, under the hub dock, and on file open.

Site audit D5: at 390px the toolbar ran off-screen (Compile unreachable) and
the shell's floating "Back to Store" link covered the document picker.
Site audit D6: opening a section re-saved it, because Monaco reports the
programmatic setValue as a content change and the autosave took it as an edit.
"""

import json
import re
import tempfile
from pathlib import Path

import pytest
from django.test import RequestFactory

from scitex_writer._django import views

_DJANGO_DIR = Path(__file__).resolve().parents[3] / "src" / "scitex_writer" / "_django"
_NARROW_CSS = _DJANGO_DIR / "static" / "writer" / "css" / "editor-narrow-and-dock.css"
_INDEX_TS = _DJANGO_DIR / "frontend" / "src" / "index.ts"
_INDEX_JS = _DJANGO_DIR / "static" / "writer" / "assets" / "index.js"


def _media_block(css: str, query: str) -> str:
    start = css.index(query)
    depth = 0
    for position in range(css.index("{", start), len(css)):
        depth += {"{": 1, "}": -1}.get(css[position], 0)
        if depth == 0:
            return css[start : position + 1]
    raise ValueError(f"unterminated block for {query}")


@pytest.fixture
def project_dir():
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        (root / "01_manuscript" / "contents").mkdir(parents=True)
        (root / "01_manuscript" / "contents" / "abstract.tex").write_text(
            "\\begin{abstract}「x」\\end{abstract}\n", encoding="utf-8"
        )
        (root / "00_shared").mkdir()
        yield root


def test_toolbar_wraps_at_narrow_widths():
    # Arrange
    css = _NARROW_CSS.read_text(encoding="utf-8")
    # Act
    narrow = _media_block(css, "@media (max-width: 768px)")
    # Assert
    assert re.search(r"\.writer-toolbar\s*\{[^}]*flex-wrap:\s*wrap", narrow)


def test_editor_page_loads_the_narrow_and_dock_stylesheet(project_dir):
    # Arrange
    request = RequestFactory().get(f"/?working_dir={project_dir}")
    # Act
    body = views.editor_page(request).content.decode()
    # Assert
    assert "writer/css/editor-narrow-and-dock.css" in body


def test_launcher_link_yields_to_the_hub_site_dock():
    # Arrange
    css = _NARROW_CSS.read_text(encoding="utf-8")
    # Act
    rule = re.search(
        r"body:has\(> \.site-dock\) > \.stx-shell-launcher-link\s*\{([^}]*)\}", css
    )
    # Assert
    assert "display: none" in rule.group(1)


def test_log_panel_clears_the_hub_site_dock():
    # Arrange
    css = _NARROW_CSS.read_text(encoding="utf-8")
    # Act
    rule = re.search(r"\.log-panel\s*\{([^}]*)\}", css).group(1)
    # Assert
    assert "var(\n    --site-dock-clearance," in rule


def test_reading_a_file_does_not_rewrite_it(project_dir):
    # Arrange
    tex = project_dir / "01_manuscript" / "contents" / "abstract.tex"
    before = tex.stat().st_mtime_ns
    request = RequestFactory().get(
        f"/api/file?path=01_manuscript/contents/abstract.tex&working_dir={project_dir}"
    )
    # Act
    views.api_dispatch(request, "api/file")
    # Assert
    assert tex.stat().st_mtime_ns == before


def test_reading_a_file_returns_cjk_content_intact(project_dir):
    # Arrange
    request = RequestFactory().get(
        f"/api/file?path=01_manuscript/contents/abstract.tex&working_dir={project_dir}"
    )
    # Act
    response = views.api_dispatch(request, "api/file")
    # Assert
    assert "「x」" in json.loads(response.content)["content"]


def test_autosave_ignores_the_change_event_of_loading_a_file():
    # Arrange
    source = _INDEX_TS.read_text(encoding="utf-8")
    # Act
    handler = source[source.index("onDidChangeModelContent(") :]
    # Assert
    assert handler.index("if (isLoadingFile) return;") < handler.index("flushSave")


def test_loading_a_file_raises_the_loading_flag_around_set_value():
    # Arrange
    source = _INDEX_TS.read_text(encoding="utf-8")
    # Act
    guarded = re.search(
        r"isLoadingFile = true;\s*try \{\s*editor\.setValue\(file\.content\);"
        r"\s*\} finally \{\s*isLoadingFile = false;",
        source,
    )
    # Assert
    assert guarded is not None


def test_shipped_bundle_was_rebuilt_with_the_autosave_guard():
    # Arrange
    bundle = _INDEX_JS.read_text(encoding="utf-8")
    # Act
    guarded = re.search(
        r"try\{[\w$]+\.setValue\([\w$]+\.content\)\}finally\{", bundle
    )
    # Assert
    assert guarded is not None


# EOF
