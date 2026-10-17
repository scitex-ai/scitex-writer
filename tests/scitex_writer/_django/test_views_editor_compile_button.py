#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# File: tests/scitex_writer/_django/test_views_editor_compile_button.py

"""Compile button is monochrome (operator 2026-10-17, mono-unification).

The desktop (#btn-compile) and mobile (#btn-mobile-compile) Compile buttons
must not pick up the gold/navy accent: each theme defines --compile-*
tokens in grayscale, and the button rule resolves only through them.
"""

import re
from pathlib import Path

_DJANGO_DIR = Path(__file__).resolve().parents[3] / "src" / "scitex_writer" / "_django"
_EDITOR_CSS = _DJANGO_DIR / "static" / "writer" / "css" / "editor.css"


def _css() -> str:
    # Arrange
    return _EDITOR_CSS.read_text(encoding="utf-8")


def _compile_rules(css: str) -> str:
    # Arrange
    blocks = re.findall(r"#btn-compile(?!-mode)[^{]*\{([^}]*)\}", css)
    # Act
    return "\n".join(blocks)


def _theme_sections(css: str) -> tuple[str, str]:
    # Arrange
    light_start = css.index('[data-theme="light"]')
    dark_start = css.index('[data-theme="dark"]')
    # Act
    return css[light_start:dark_start], css[dark_start:]


def test_compile_button_rule_uses_no_accent():
    # Arrange
    rules = _compile_rules(_css())
    # Act
    # Assert
    assert (
        ("accent" not in rules)
        and ("#d4a87a" not in rules)
        and ("#e0bb93" not in rules)
    )


def test_compile_tokens_defined_for_both_themes():
    # Arrange
    light, dark = _theme_sections(_css())
    # Act
    # Assert
    assert (
        ("--compile-bg:" in light)
        and ("--compile-hover:" in light)
        and ("--compile-text:" in light)
        and ("--compile-bg:" in dark)
        and ("--compile-hover:" in dark)
        and ("--compile-text:" in dark)
    )


def test_compile_token_values_are_monochrome():
    # Arrange
    css = _css()
    # Act
    grays = re.findall(r"--compile-(?:bg|hover):\s*#([0-9a-fA-F]{6})", css)
    # Assert
    assert (len(grays) == 4) and all(
        (len(set((h[0:2], h[2:4], h[4:6]))) == 1) for h in grays
    )
