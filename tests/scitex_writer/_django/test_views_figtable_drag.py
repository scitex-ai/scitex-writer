#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# File: tests/scitex_writer/_django/test_views_figtable_drag.py

"""Fig/Table panes: thumbnails, drag-instead-of-click, quiet surfaces.

Operator 2026-10-24: figure/table items show thumbnails (backend serves
/api/thumbnail), and must NOT surprise-insert on click — drag carries the
\\ref payload through the shared insert MIME into Monaco. Thumb cards use
the same quiet app-surface language as citation cards.

STX-TQ007: one assertion per test (see 3af127ed).
"""

from __future__ import annotations

import re
from pathlib import Path

_DJANGO_DIR = Path(__file__).resolve().parents[3] / "src" / "scitex_writer" / "_django"
_EDITOR_CSS = _DJANGO_DIR / "static" / "writer" / "css" / "editor.css"
_INSERT_TS = _DJANGO_DIR / "frontend" / "src" / "insert-panel.ts"
_INDEX_TS = _DJANGO_DIR / "frontend" / "src" / "index.ts"


def _rule_block(selector: str) -> str:
    # Arrange: the full editor stylesheet on disk.
    css = _EDITOR_CSS.read_text(encoding="utf-8")
    # Act: exercise the real rule.
    match = re.search(re.escape(selector) + r"\s*\{([^}]*)\}", css)
    # Assert (presence is asserted by callers via non-empty use).
    return match.group(1) if match else ""


def test_figtable_items_are_draggable():
    # Arrange: the panel markup source.
    source = _INSERT_TS.read_text(encoding="utf-8")
    # Act
    # Assert
    assert 'draggable="true"' in source


def test_figtable_drag_carries_the_shared_insert_mime():
    # Arrange
    source = _INSERT_TS.read_text(encoding="utf-8")
    # Act
    # Assert
    assert "setData(INSERT_MIME, snippet)" in source


def test_figtable_click_does_not_insert():
    # Arrange: renderList wires dragstart/dragend only — no click handler
    # may call insertAtCursor for items (cite parity: click only selects).
    source = _INSERT_TS.read_text(encoding="utf-8")
    listed = source[source.index("private renderList(") :]
    # Act
    # Assert
    assert ('addEventListener("click"' not in listed) and (
        "insertAtCursor" not in listed
    )


def test_monaco_accepts_ref_payloads_on_drop():
    # Arrange: the drop gate in the entry point.
    source = _INDEX_TS.read_text(encoding="utf-8")
    # Act
    # Assert
    assert 'payload.startsWith("\\\\ref")' in source


def test_thumb_cards_sit_on_the_app_surface():
    # Arrange (stylesheet on disk)
    block = _rule_block(".insert-item--thumb")
    # Act
    # Assert
    assert "background: var(--bg-secondary);" in block


def test_thumb_images_render_on_the_tertiary_face():
    # Arrange (stylesheet on disk): no white thumbnail wells in dark mode.
    block = _rule_block(".insert-item-thumb")
    # Act
    # Assert
    assert ("background: var(--bg-tertiary);" in block) and (
        "#fff" not in block
    )


def test_drag_hint_names_the_gesture():
    # Arrange
    source = _INSERT_TS.read_text(encoding="utf-8")
    # Act
    # Assert
    assert "insert-panel-drag-hint" in source
