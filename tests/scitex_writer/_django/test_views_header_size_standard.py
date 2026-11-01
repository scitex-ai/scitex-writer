#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# File: tests/scitex_writer/_django/test_views_header_size_standard.py

"""Legacy separate project-bar appearance; shared header styles belong to SDK."""

from __future__ import annotations

import re
from pathlib import Path

_DJANGO_DIR = Path(__file__).resolve().parents[3] / "src" / "scitex_writer" / "_django"
_PICKER_CSS = _DJANGO_DIR / "static" / "writer" / "css" / "project-picker.css"


def _rule_block(css_path: Path, selector: str) -> str:
    # Arrange: the stylesheet on disk.
    css = css_path.read_text(encoding="utf-8")
    # Act: exercise the real rule.
    match = re.search(re.escape(selector) + r"\s*\{([^}]*)\}", css)
    # Assert (presence is asserted by callers via non-empty use).
    return match.group(1) if match else ""




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
