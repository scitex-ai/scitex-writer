#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# File: tests/scitex_writer/_compile/_diagnostics/test__model.py

"""LatexDiagnostic and hint filling."""

from scitex_writer._compile._diagnostics._model import LatexDiagnostic, fill_hint


def test_location_joins_file_and_line():
    # Arrange
    diagnostic = LatexDiagnostic(
        cause="unknown", severity="error", message="m", hint="h", file="a.tex", line=3
    )
    # Act
    location = diagnostic.location
    # Assert
    assert location == "a.tex:3"


def test_fill_hint_falls_back_when_the_command_is_unknown():
    # Arrange
    template = "{command} is not defined"
    # Act
    hint = fill_hint(template, {"command": None})
    # Assert
    assert hint == "This command is not defined"


# EOF
