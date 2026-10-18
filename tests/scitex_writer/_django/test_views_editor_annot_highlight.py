#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# File: tests/scitex_writer/_django/test_views_editor_annot_highlight.py

"""Highlight annotation cards are square (operator CCT4372).

Same direction as Cards CCT4368: the highlight variant goes
straight/square corners while the base card keeps its rounding.
"""

import re
from pathlib import Path

_DJANGO_DIR = Path(__file__).resolve().parents[3] / "src" / "scitex_writer" / "_django"
_ANNOT_CSS = _DJANGO_DIR / "static" / "writer" / "css" / "annotations.css"


def _css() -> str:
    # Arrange
    return _ANNOT_CSS.read_text(encoding="utf-8")


def _rule_block(css: str, selector: str) -> str:
    # Arrange
    match = re.search(re.escape(selector) + r"\s*\{([^}]*)\}", css)
    # Act
    return match.group(1) if match else ""


def test_highlight_category_rule_has_square_corners():
    # Arrange
    block = _rule_block(_css(), '.annot-row[data-category="highlight"]')
    # Act
    # Assert
    assert re.search(r"border-radius:\s*0(px)?;", block) is not None


def test_base_annot_row_keeps_rounded_corners():
    # Arrange
    block = _rule_block(_css(), ".annot-row")
    # Act
    # Assert
    assert "border-radius: 4px;" in block
