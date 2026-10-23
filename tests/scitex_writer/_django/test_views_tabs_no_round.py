#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# File: tests/scitex_writer/_django/test_views_tabs_no_round.py

"""Tab active states are straight underlines, never filled pills.

Same direction as the CCT4700 annot-button fix and FigRecipe #442:
`.preview-tab.active` (PDF/Claims) and `.insert-bar-btn.active`
(Cite/Fig/Table/Collab/History) draw their indicator with `border-bottom` —
no accent-fill background, no `box-shadow`, or `border-radius`.

Operator 2026-10-23: the rail switches the large preview pane instead of
expanding beside it — cite/fig/table/collab/history render into the
#insert-view pane; the header tabs switch PDF/Claims through the same
showPreviewView path.

STX-TQ007: one assertion per test (see 3af127ed).
"""

from __future__ import annotations

import re
import tempfile
from pathlib import Path

import pytest
from django.test import RequestFactory

from scitex_writer._django import views

_DJANGO_DIR = Path(__file__).resolve().parents[3] / "src" / "scitex_writer" / "_django"
_EDITOR_CSS = _DJANGO_DIR / "static" / "writer" / "css" / "editor.css"
_INDEX_TS = _DJANGO_DIR / "frontend" / "src" / "index.ts"
_INSERT_TS = _DJANGO_DIR / "frontend" / "src" / "insert-panel.ts"


@pytest.fixture
def project_dir():
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        (root / "01_manuscript" / "contents").mkdir(parents=True)
        (root / "01_manuscript" / "contents" / "abstract.tex").write_text(
            "\\begin{abstract}x\\end{abstract}\n", encoding="utf-8"
        )
        (root / "00_shared").mkdir()
        yield root


def _editor_html(project_dir) -> str:
    request = RequestFactory().get(f"/?working_dir={project_dir}")
    return views.editor_page(request).content.decode()


def _rule_block(selector: str) -> str:
    # Arrange: the full editor stylesheet on disk.
    css = _EDITOR_CSS.read_text(encoding="utf-8")
    # Act: exercise the real rule.
    match = re.search(re.escape(selector) + r"\s*\{([^}]*)\}", css)
    # Assert (presence is asserted by callers via non-empty use).
    return match.group(1) if match else ""


def test_preview_tab_active_has_no_fill_background():
    # Arrange (stylesheet on disk)
    block = _rule_block(".preview-tab.active")
    # Act
    # Assert
    assert "background: transparent;" in block


def test_preview_tab_active_is_a_straight_underline():
    # Arrange (stylesheet on disk)
    block = _rule_block(".preview-tab.active")
    # Act
    # Assert
    assert "border-bottom-color: var(--accent);" in block


def test_preview_tab_active_has_square_corners():
    # Arrange (stylesheet on disk)
    block = _rule_block(".preview-tab.active")
    # Act
    # Assert
    assert "border-radius: 0;" in block


def test_insert_bar_active_has_no_fill_background():
    # Arrange (stylesheet on disk)
    block = _rule_block(".insert-bar-btn.active")
    # Act
    # Assert
    assert "background: transparent;" in block


def test_insert_bar_active_is_a_straight_underline():
    # Arrange (stylesheet on disk)
    block = _rule_block(".insert-bar-btn.active")
    # Act
    # Assert
    assert "border-bottom-color: var(--accent);" in block


def test_insert_bar_active_has_square_corners():
    # Arrange (stylesheet on disk)
    block = _rule_block(".insert-bar-btn.active")
    # Act
    # Assert
    assert "border-radius: 0;" in block


def test_preview_tabs_are_pdf_and_claims_only(project_dir):
    # Arrange: operator 2026-10-22 — the dead Bibliography tab is gone
    # (never populated, never wired); the pane switches PDF vs Claims.
    # Act
    body = _editor_html(project_dir)
    tabs = re.findall(r'class="preview-tab[^"]*" data-view="(\w+)"', body)
    # Assert
    assert tabs == ["pdf", "claims"] and "bib-view" not in body


def test_insert_panel_lives_in_the_switched_preview_pane(project_dir):
    # Arrange: operator 2026-10-23 — cite/fig/table/collab/history render
    # into #insert-view in the large pane, not expanding beside the editor.
    # Act
    body = _editor_html(project_dir)
    # Assert
    assert ('id="insert-view"' in body) and (
        body.index('id="insert-view"') < body.index('id="insert-panel"')
    ) and ('id="preview-content"' in body) and (
        body.index('id="preview-content"') < body.index('id="insert-view"')
    )


def test_rail_and_header_tabs_share_one_preview_switcher():
    # Arrange: operator 2026-10-23 — one showPreviewView path drives both
    # the rail (cite/fig/table/collab/history) and the header tabs.
    source = _INDEX_TS.read_text(encoding="utf-8")
    panel = _INSERT_TS.read_text(encoding="utf-8")
    # Act
    # Assert
    assert ("function showPreviewView" in source) and (
        "onSelect: (pane)" in source
    ) and ("onSelect?: (pane: InsertPaneId) => void" in panel)
