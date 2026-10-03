#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# File: src/scitex_writer/_compile/_parser.py

"""
Compilation output parsing.

Parses LaTeX compilation output and log files for errors and warnings.
"""

from __future__ import annotations

from pathlib import Path
from typing import List, Optional, Tuple

from scitex_logging import getLogger

from .._utils._parse_latex_logs import parse_compilation_output

logger = getLogger(__name__)


def parse_output(
    stdout: str,
    stderr: str,
    log_file: Optional[Path] = None,
) -> Tuple[List[str], List[str]]:
    """
    Parse compilation output for errors and warnings.

    Parameters
    ----------
    stdout : str
        Standard output from compilation
    stderr : str
        Standard error from compilation
    log_file : Path, optional
        Path to LaTeX log file

    Returns
    -------
    tuple
        (errors, warnings) as lists of strings
    """
    error_issues, warning_issues = parse_compilation_output(
        stdout + stderr, log_file=log_file
    )

    # Convert LaTeXIssue objects to strings for backward compatibility
    errors = [str(issue) for issue in error_issues]
    warnings = [str(issue) for issue in warning_issues]

    return errors, warnings


__all__ = ["parse_output"]

# EOF
