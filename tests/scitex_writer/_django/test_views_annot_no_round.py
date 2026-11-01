#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# File: tests/scitex_writer/_django/test_views_annot_no_round.py

"""Annot-button active state is a straight underline, never rounded (CCT4700).

Operator HARD NO: rounded highlight on annot buttons is FORBIDDEN.
`.annot-btn.active` draws its indicator with `border-bottom` — `box-shadow`
is forbidden (a shadowed box reads as a rounded pill) and `border-radius`
is forbidden on any active annot button. The ghost base keeps
`border-radius: 0` so the inherited `.btn-icon:hover` 4px rounding cannot
leak into the toolbar either.

STX-TQ007: one assertion per test (see 3af127ed).
"""

from __future__ import annotations

import re
from pathlib import Path

_DJANGO_DIR = Path(__file__).resolve().parents[3] / "src" / "scitex_writer" / "_django"
_ANNOT_CSS = _DJANGO_DIR / "static" / "writer" / "css" / "annotations.css"
_ANNOT_UI_TS = _DJANGO_DIR / "frontend" / "src" / "annotation-ui.ts"


def _rule_block(selector: str) -> str:
    # Arrange: the full annot stylesheet on disk.
    css = _ANNOT_CSS.read_text(encoding="utf-8")
    # Act: exercise the real rule.
    match = re.search(re.escape(selector) + r"\s*\{([^}]*)\}", css)
    # Assert (presence is asserted by callers via non-empty use).
    return match.group(1) if match else ""


def test_active_annot_button_has_no_box_shadow():
    # Arrange (stylesheet on disk)
    block = _rule_block(".annot-btn.active")
    # Act
    # Assert
    assert "box-shadow" not in block


def test_active_annot_button_is_a_straight_underline():
    # Arrange (stylesheet on disk)
    block = _rule_block(".annot-btn.active")
    # Act
    # Assert
    assert "border-bottom-color: var(--accent);" in block


def test_active_annot_button_has_square_corners():
    # Arrange (stylesheet on disk)
    block = _rule_block(".annot-btn.active")
    # Act
    # Assert
    assert "border-radius: 0;" in block


def test_annot_button_base_has_square_corners():
    # Arrange (stylesheet on disk)
    block = _rule_block(".annot-toolbar .annot-btn")
    # Act
    # Assert
    assert "border-radius: 0;" in block


def test_annot_button_base_layout_does_not_shift_on_activate():
    # Arrange (stylesheet on disk)
    block = _rule_block(".annot-toolbar .annot-btn")
    # Act
    # Assert
    assert "border-bottom: 2px solid transparent;" in block


def test_annot_menu_list_is_a_positioned_popup():
    # Arrange (stylesheet on disk): operator 2026-10-23 — the annot
    # hamburger opens a popup menu, not an inline row.
    block = _rule_block(".annot-menu-list")
    # Act
    # Assert
    assert ("position: absolute;" in block) and ("z-index: 60;" in block)


def test_annot_toolbar_builds_hamburger_menu_with_shortcuts():
    # Arrange: operator 2026-10-23 — modes (Alt+1-3) and tools (Alt+4-8)
    # live in the hamburger menu; shortcuts delegate to the buttons.
    source = _ANNOT_UI_TS.read_text(encoding="utf-8")
    # Act
    # Assert
    assert (
        ('id = "btn-annot-menu"' in source)
        and ('id = "annot-menu-list"' in source)
        and ('"1": modeButtons.get("read")' in source)
        and ('"4": toolButtons.get("highlight")' in source)
        and ("target.click()" in source)
    )
