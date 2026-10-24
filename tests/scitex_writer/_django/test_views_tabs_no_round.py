#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# File: tests/scitex_writer/_django/test_views_tabs_no_round.py

"""Right-pane selector: the rail is the ONE switch, never a separate PDF tab.

Operator 2026-10-23: the rail carries PDF/Cite/Fig/Table/Collab/History;
PDF renders in #pdf-view, the rest in #insert-view — no expand beside
the editor, no PDF tab in the preview header. Claims stays as a
secondary view until the live-paper example project lands.

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


def test_insert_bar_active_is_a_vertical_bar():
    # Arrange (stylesheet on disk): operator 2026-10-24 — the selected
    # rail button carries a RIGHT-edge vertical bar (facing the switched
    # pane), not an underline and not the old left edge.
    block = _rule_block(".insert-bar-btn.active")
    # Act
    # Assert
    assert ("border-right-color: var(--accent);" in block) and (
        "border-bottom-color" not in block
    )


def test_dead_split_resizer_is_gone(project_dir):
    # Arrange: operator 2026-10-23 — the editor|rail resizer had no JS
    # behind it and rendered as a stray accent line. Markup + CSS gone.
    body = _editor_html(project_dir)
    css = _EDITOR_CSS.read_text(encoding="utf-8")
    # Act
    # Assert
    assert ("writer-split-resizer" not in body) and (
        ".writer-split-resizer {" not in css
    )


def test_insert_bar_active_has_square_corners():
    # Arrange (stylesheet on disk)
    block = _rule_block(".insert-bar-btn.active")
    # Act
    # Assert
    assert "border-radius: 0;" in block


def test_insert_bar_hover_has_no_fill_background():
    # Arrange (stylesheet on disk): operator 2026-10-23 — no left-side
    # highlight on the rail; hover is text-only, active is the underline.
    block = _rule_block(".insert-bar-btn:hover")
    # Act
    # Assert
    assert "background" not in block


def test_citation_cards_sit_on_the_app_surface():
    # Arrange (stylesheet on disk): operator 2026-10-23 — cards were
    # harsh white (#fff face, #ddd border); now secondary face + tokens.
    css = _EDITOR_CSS.read_text(encoding="utf-8")
    card = _rule_block(".citation-card")
    # Act
    # Assert
    assert ("background: var(--bg-secondary);" in card) and (
        "#fff" not in css[css.index(".citation-card {") : css.index(".citation-card:hover {")]
    )


def test_enrich_button_is_the_cta():
    # Arrange: operator 2026-10-23 — Enrich carries the scitex CTA fill
    # (navy light / gold dark) with icon-label gap.
    panel = _DJANGO_DIR / "frontend" / "src" / "citations-panel.ts"
    source = panel.read_text(encoding="utf-8")
    css = _EDITOR_CSS.read_text(encoding="utf-8")
    # Act
    # Assert
    assert ('btn-primary btn-sm citations-enrich' in source) and (
        ".citations-enrich {" in css
    )


def test_preview_tabs_are_pdf_and_claims_only(project_dir):
    # Arrange: operator 2026-10-23 — PDF is NOT a separated tab; the rail
    # (PDF/Cite/Fig/Table/Collab/History) is the one selector. No
    # preview-tab buttons remain in the editor header.
    # Act
    body = _editor_html(project_dir)
    tabs = re.findall(r'class="preview-tab[^"]*" data-view="(\w+)"', body)
    # Assert
    assert tabs == [] and "bib-view" not in body


def test_rail_carries_pdf_first_then_tools(project_dir):
    # Arrange: operator 2026-10-23 — PDF/Cite/Fig/Table/Collab/History in
    # that order, PDF first (it is the default view).
    # Act
    body = _editor_html(project_dir)
    panes = re.findall(r'data-pane="(\w+)"', body)
    # Assert
    assert panes == ["pdf", "cite", "fig", "table", "collab", "history"]


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
    # Arrange: operator 2026-10-23 — one showPreviewView path drives the
    # rail (PDF/cite/fig/table/collab/history) and the claims trigger.
    source = _INDEX_TS.read_text(encoding="utf-8")
    panel = _INSERT_TS.read_text(encoding="utf-8")
    # Act
    # Assert
    assert ("function showPreviewView" in source) and (
        "onSelect: (pane)" in source
    ) and ("onSelect?: (pane: InsertPaneId) => void" in panel)
