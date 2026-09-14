#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# File: tests/scitex_writer/_compile/_diagnostics/test__tex_log.py

"""Low-level TeX log reading: wrapping, byte escapes, the open-file stack."""

from scitex_writer._compile._diagnostics._tex_log import (
    FileStack,
    decode_caret_bytes,
    meaningful_tail,
    unwrap_tex_log,
)


def test_unwrap_rejoins_a_line_wrapped_at_79_bytes():
    # Arrange
    wrapped = "x" * 79 + "\nrest of it\nnext"
    # Act
    lines = unwrap_tex_log(wrapped)
    # Assert
    assert lines == ["x" * 79 + "rest of it", "next"]


def test_caret_escapes_decode_to_the_utf8_character():
    # Arrange
    escaped = "bracket ^^e3^^80^^8d here"
    # Act
    decoded = decode_caret_bytes(escaped)
    # Assert
    assert decoded == "bracket 」 here"


def test_file_stack_tracks_the_innermost_open_tex_file():
    # Arrange
    stack = FileStack()
    # Act
    stack.feed("(./main.tex (/usr/share/article.cls) (./contents/intro.tex")
    # Assert
    assert stack.current_tex_file == "contents/intro.tex"


def test_file_stack_ignores_parentheses_in_plain_text():
    # Arrange
    stack = FileStack()
    # Act
    stack.feed("(./main.tex (see the transcript file) [1]")
    # Assert
    assert stack.current_tex_file == "main.tex"


def test_meaningful_tail_drops_engine_bookkeeping():
    # Arrange
    log = "LaTeX Font Info: noise\n\\c@part=\\count196\nreal line\n\n"
    # Act
    tail = meaningful_tail(log)
    # Assert
    assert tail == "real line"


# EOF
