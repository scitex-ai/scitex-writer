#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Tests for compilation output parser.

Tests parse_output function for extracting errors and warnings.
"""

from pathlib import Path

import pytest

from scitex_writer._compile._parser import parse_output


class TestParseOutput:
    """Test suite for parse_output function."""

    def test_import_callable_parse_output(self):
        """Test that parse_output can be imported."""
        # Arrange
        # Act
        # Assert
        assert callable(parse_output)

    def test_parse_empty_output(self):
        """Test parsing empty output returns empty lists."""
        # Arrange
        # Act
        errors, warnings = parse_output("", "")
        # Assert
        assert (errors == []) and (warnings == [])

    def test_parse_output_with_no_log_file(self):
        """Test parsing without log file."""
        # Arrange
        stdout = "Compilation successful"
        stderr = ""
        # Act
        errors, warnings = parse_output(stdout, stderr, log_file=None)
        # Assert
        assert (isinstance(errors, list)) and (isinstance(warnings, list))

    def test_parse_output_with_log_file(self):
        """Test parsing with log file path."""
        # Arrange
        stdout = "Compilation successful"
        stderr = ""
        log_file = Path("/tmp/test.log")
        # Act
        errors, warnings = parse_output(stdout, stderr, log_file=log_file)
        # Assert
        assert (isinstance(errors, list)) and (isinstance(warnings, list))


# EOF

if __name__ == "__main__":
    import os

    import pytest

    pytest.main([os.path.abspath(__file__)])
