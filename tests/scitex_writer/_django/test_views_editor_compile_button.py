#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# File: tests/scitex_writer/_django/test_views_editor_compile_button.py

"""Compile button carries the scitex CTA (operator 2026-10-23).

The desktop (#btn-compile) Compile button uses the gold/navy accent
like every other primary button: the rule resolves only through the
--accent/--accent-hover tokens, and the text stays on the contrast-safe
--compile-text token (white on navy light, near-black on gold dark).
(Supersedes the 2026-10-17 mono-unification direction.)"""

import re
from pathlib import Path

_DJANGO_DIR = Path(__file__).resolve().parents[3] / "src" / "scitex_writer" / "_django"
_EDITOR_CSS = _DJANGO_DIR / "static" / "writer" / "css" / "editor.css"
_INDEX_TS = _DJANGO_DIR / "frontend" / "src" / "index.ts"


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


def test_compile_button_rule_uses_the_accent_cta():
    # Arrange
    rules = _compile_rules(_css())
    # Act
    # Assert
    assert (
        ("var(--accent)" in rules)
        and ("var(--accent-hover)" in rules)
        and ("var(--compile-text)" in rules)
    )


def test_compile_tokens_defined_for_both_themes():
    # Arrange — accent tokens per theme (navy light / gold dark) plus the
    # contrast-safe text token the CTA face reads.
    light, dark = _theme_sections(_css())
    # Act
    # Assert
    assert (
        ("--accent:" in light)
        and ("--accent:" in dark)
        and ("--compile-text:" in light)
        and ("--compile-text:" in dark)
    )


def test_compile_token_values_are_monochrome():
    # Arrange — superseded 2026-10-23: Compile is the CTA now; the text
    # token stays grayscale for contrast on both accent faces.
    css = _css()
    # Act
    grays = re.findall(r"--compile-text:\s*#([0-9a-fA-F]{6})", css)
    # Assert
    assert (len(grays) == 2) and all(
        (len(set((h[0:2], h[2:4], h[4:6]))) == 1) for h in grays
    )


def test_compile_mode_options_follow_the_open_section():
    # Arrange: operator 2026-10-23 — Draft names the open section (e.g.
    # "Abstract"), Full names the document (e.g. "Manuscript"). The option
    # text is set at runtime on every section load; pinned here at the wire.
    source = _INDEX_TS.read_text(encoding="utf-8")
    # Act
    # Assert
    assert (
        ("updateCompileModeLabels(section)" in source)
        and ("humanize(section.name)" in source)
        and ('option[value="preview"]' in source)
        and ('option[value="full"]' in source)
    )
