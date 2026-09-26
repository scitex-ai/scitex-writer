#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# File: tests/scitex_writer/_compile/_diagnostics/test__rules.py

"""The rule tables: ordering and coverage of the closed cause set."""

from scitex_writer._compile._diagnostics._model import CAUSE_CLASSES
from scitex_writer._compile._diagnostics._rules import (
    BIBLIOGRAPHY_RULES,
    ERROR_RULES,
    WARNING_RULES,
    classify,
)


def test_a_missing_sty_is_a_package_not_a_file():
    # Arrange
    message = "LaTeX Error: File `soul.sty' not found."
    # Act
    rule, _ = classify(message, ERROR_RULES)
    # Assert
    assert rule.cause == "missing-package"


def test_biber_error_line_is_classified():
    # Arrange
    line = "[42] Utils.pm:465> ERROR - BibTeX subsystem: refs.bib, line 7, syntax error"
    # Act
    rule, _ = classify(line, BIBLIOGRAPHY_RULES)
    # Assert
    assert rule.cause == "biber-error"


def test_every_rule_cause_belongs_to_the_closed_set():
    # Arrange
    rules = ERROR_RULES + WARNING_RULES + BIBLIOGRAPHY_RULES
    # Act
    outside = {rule.cause for rule in rules} - set(CAUSE_CLASSES)
    # Assert
    assert outside == set()


def test_unmatched_text_classifies_as_nothing():
    # Arrange
    message = "Something custom went wrong."
    # Act
    classified = classify(message, ERROR_RULES)
    # Assert
    assert classified is None


# EOF
