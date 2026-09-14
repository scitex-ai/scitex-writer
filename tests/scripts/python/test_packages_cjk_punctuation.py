#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# File: tests/scripts/python/test_packages_cjk_punctuation.py

"""CJK punctuation in a .tex must not be a fatal pdfLaTeX error.

A stray Japanese corner bracket (U+300D, typed by an IME) broke every
auto-compile with "Unicode character not set up for use with LaTeX".
packages.tex now maps CJK punctuation for pdfTeX; the compile tests run that
exact block through a real pdflatex and are skipped where none is installed.
"""

import shutil
import subprocess
from pathlib import Path

import pytest

_REPO_ROOT = Path(__file__).resolve().parents[3]
_PACKAGES_TEX = _REPO_ROOT / "00_shared" / "latex_styles" / "packages.tex"
_ABSTRACT_TEX = _REPO_ROOT / "01_manuscript" / "contents" / "abstract.tex"

needs_pdflatex = pytest.mark.skipif(
    shutil.which("pdflatex") is None, reason="pdflatex not available"
)


def _cjk_mapping_block() -> str:
    source = _PACKAGES_TEX.read_text(encoding="utf-8")
    start = source.index(r"\usepackage{iftex}")
    end = source.index(r"\fi", start) + len(r"\fi")
    return source[start:end]


def _compile(tmp_path: Path, preamble_extra: str) -> Path:
    doc = (
        "\\documentclass{article}\n"
        "\\usepackage[T1]{fontenc}\n"
        "\\usepackage[utf8]{inputenc}\n"
        f"{preamble_extra}\n"
        "\\begin{document}\n"
        "He said 「quoted」 and 『double』.\n"
        "\\end{document}\n"
    )
    (tmp_path / "doc.tex").write_text(doc, encoding="utf-8")
    subprocess.run(
        ["pdflatex", "-interaction=nonstopmode", "-halt-on-error", "doc.tex"],
        cwd=str(tmp_path),
        capture_output=True,
        timeout=120,
    )
    return tmp_path / "doc.pdf"


def test_packages_tex_maps_the_japanese_closing_corner_bracket():
    # Arrange
    declaration = r"\DeclareUnicodeCharacter{300D}"
    # Act
    block = _cjk_mapping_block()
    # Assert
    assert declaration in block


def test_template_abstract_carries_no_stray_corner_bracket():
    # Arrange
    stray = "」"
    # Act
    abstract = _ABSTRACT_TEX.read_text(encoding="utf-8")
    # Assert
    assert stray not in abstract


@needs_pdflatex
def test_corner_brackets_compile_with_the_packages_tex_mapping(tmp_path):
    # Arrange
    mapping = _cjk_mapping_block()
    # Act
    pdf = _compile(tmp_path, mapping)
    # Assert
    assert pdf.exists()


@needs_pdflatex
def test_corner_brackets_are_fatal_without_the_mapping(tmp_path):
    """Positive control: proves the compile test above can fail."""
    # Arrange
    no_mapping = ""
    # Act
    pdf = _compile(tmp_path, no_mapping)
    # Assert
    assert not pdf.exists()


# EOF
