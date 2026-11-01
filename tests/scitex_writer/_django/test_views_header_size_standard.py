#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# File: tests/scitex_writer/_django/test_views_header_size_standard.py

"""Writer header size standard: 45px row, no picker underline (CCT4715/CCT4713).

FigRecipe 45px header is the reference. Writer pins its own row to the 45px
standard leaf-side (min-height on .writer-app-header) instead of waiting on
the shared sheet's 40px. The picker bar carries no bottom border — separation
comes from background contrast only.

STX-TQ007: one assertion per test (see 3af127ed).
"""

from __future__ import annotations

import re
from pathlib import Path

_DJANGO_DIR = Path(__file__).resolve().parents[3] / "src" / "scitex_writer" / "_django"
_APP_HEADER_CSS = _DJANGO_DIR / "static" / "writer" / "css" / "app-header.css"
_PICKER_CSS = _DJANGO_DIR / "static" / "writer" / "css" / "project-picker.css"


def _rule_block(css_path: Path, selector: str) -> str:
    # Arrange: the stylesheet on disk.
    css = css_path.read_text(encoding="utf-8")
    # Act: exercise the real rule.
    match = re.search(re.escape(selector) + r"\s*\{([^}]*)\}", css)
    # Assert (presence is asserted by callers via non-empty use).
    return match.group(1) if match else ""


def test_writer_header_row_pins_the_45px_standard():
    # Arrange (stylesheet on disk): id selector beats the shared class
    # regardless of stylesheet order.
    block = _rule_block(_APP_HEADER_CSS, "#writer-app-header")
    # Act
    # Assert
    assert "min-height: 45px;" in block


def test_writer_picker_bar_carries_no_underline():
    # Arrange (stylesheet on disk)
    block = _rule_block(_PICKER_CSS, ".writer-project-scope")
    # Act
    # Assert
    assert "border-bottom: none;" in block


def test_writer_picker_trigger_sits_on_the_app_surface():
    # Arrange (stylesheet on disk): operator 2026-10-23 — the picker must
    # follow the writer bluish-gray chrome, not SDK light defaults.
    css = _PICKER_CSS.read_text(encoding="utf-8")
    # Act
    # Assert
    assert "background: var(--bg-secondary);" in css
