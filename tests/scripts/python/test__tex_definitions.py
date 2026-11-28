#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# Test file for: scripts/python/_tex_definitions.py
#
# A macro DEFINITION that contains \includegraphics is not an inclusion. The
# compile-artifacts gate counts \includegraphics in the compiled .tex and
# fails when the PDF embeds none, so a definition counted as a use makes a
# figure-free document fail the gate (seen on a supplement whose only
# \includegraphics sat in an optional colophon-icon macro).

import sys
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parent.parent.parent.parent
sys.path.insert(0, str(ROOT_DIR / "scripts" / "python"))

from _tex_definitions import strip_macro_definitions  # noqa: E402
from check_compile_artifacts import count_includegraphics  # noqa: E402

_COLOPHON = (
    "\\newcommand{\\clewColophonIcon}{%\n"
    "  \\begingroup\\edef\\clew@sigiconpath{\\clewSigIcon}%\n"
    "  \\expandafter\\IfFileExists\\expandafter{\\clew@sigiconpath}%\n"
    "    {\\raisebox{-0.25em}{\\includegraphics[height=1em]{\\clew@sigiconpath}}\\,}{}%\n"
    "  \\endgroup}\n"
)


def _count(tmp_path, text):
    tex = tmp_path / "compiled.tex"
    tex.write_text(text, encoding="utf-8")
    return count_includegraphics(tex)


def test_newcommand_body_is_removed():
    # Arrange
    text = "a\\newcommand{\\x}[1]{\\includegraphics{#1}}b"
    # Act
    out = strip_macro_definitions(text)
    # Assert
    assert out == "ab"


def test_newcommand_with_optional_default_is_removed():
    # Arrange
    text = "\\newcommand*{\\x}[2][w]{\\includegraphics[width=#1]{#2}}after"
    # Act
    out = strip_macro_definitions(text)
    # Assert
    assert out == "after"


def test_def_with_parameter_text_is_removed():
    # Arrange
    text = "\\def\\fig#1{\\includegraphics{#1}}keep"
    # Act
    out = strip_macro_definitions(text)
    # Assert
    assert out == "keep"


def test_gdef_of_at_macro_is_removed():
    # Arrange
    text = "\\long\\gdef\\my@fig{\\includegraphics{a.jpg}}keep"
    # Act
    out = strip_macro_definitions(text)
    # Assert
    assert out == "keep"


def test_newenvironment_both_bodies_are_removed():
    # Arrange
    text = "\\newenvironment{pic}{\\includegraphics{a}}{\\includegraphics{b}}x"
    # Act
    out = strip_macro_definitions(text)
    # Assert
    assert out == "x"


def test_nested_braces_inside_body_are_balanced():
    # Arrange
    text = "\\newcommand{\\x}{{\\bf{y}}\\includegraphics{z}}tail"
    # Act
    out = strip_macro_definitions(text)
    # Assert
    assert out == "tail"


def test_text_without_definitions_is_unchanged():
    # Arrange
    text = "\\begin{figure}\\includegraphics{a.jpg}\\end{figure}"
    # Act
    out = strip_macro_definitions(text)
    # Assert
    assert out == text


def test_defined_but_unused_graphics_macro_counts_zero(tmp_path):
    # Arrange
    text = (
        "\\documentclass{article}\n" + _COLOPHON + "\\begin{document}x\\end{document}\n"
    )
    # Act
    n = _count(tmp_path, text)
    # Assert
    assert n == 0


def test_real_inclusions_still_count_next_to_a_definition(tmp_path):
    # Arrange
    text = (
        "\\documentclass{article}\n"
        + _COLOPHON
        + "\\begin{document}\\includegraphics{01.jpg}\\includegraphics{02.jpg}"
        "\\end{document}\n"
    )
    # Act
    n = _count(tmp_path, text)
    # Assert
    assert n == 2


def test_def_keyword_prefix_does_not_match_other_macros():
    # Arrange: \default and \defined are not \def
    text = "\\default{\\includegraphics{a}}\\defined{b}"
    # Act
    out = strip_macro_definitions(text)
    # Assert
    assert out == text
