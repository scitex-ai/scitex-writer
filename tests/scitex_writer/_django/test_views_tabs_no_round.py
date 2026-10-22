#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# File: tests/scitex_writer/_django/test_views_tabs_no_round.py

"""Tab active states are straight underlines, never filled pills.

Same direction as the CCT4700 annot-button fix and FigRecipe #442:
`.preview-tab.active` (PDF/Bibliography/Claims) and `.insert-bar-btn.active`
(Cite/Fig/Table/Collab/History) draw their indicator with `border-bottom` —
no accent-fill background, no `box-shadow`, no `border-radius`.

STX-TQ007: one assertion per test (see 3af127ed).
"""

from __future__ import annotations

import re
from pathlib import Path

_DJANGO_DIR = Path(__file__).resolve().parents[3] / "src" / "scitex_writer" / "_django"
_EDITOR_CSS = _DJANGO_DIR / "static" / "writer" / "css" / "editor.css"


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
