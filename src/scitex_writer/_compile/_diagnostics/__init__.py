#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# File: src/scitex_writer/_compile/_diagnostics/__init__.py

"""Compile diagnostics: every failed compile explains itself.

A table-driven LaTeX log analyser (:mod:`._rules`, :mod:`._tex_log`,
:mod:`._analyse`) whose result is published in the ``scitex_dev.status``
shape (:mod:`._report`).
"""

from ._analyse import analyse_latex_output
from ._model import CAUSE_CLASSES, SEVERITY_ERROR, SEVERITY_WARNING, LatexDiagnostic
from ._report import diagnose_compile, diagnose_exception, diagnostics_report

__all__ = [
    "CAUSE_CLASSES",
    "LatexDiagnostic",
    "SEVERITY_ERROR",
    "SEVERITY_WARNING",
    "analyse_latex_output",
    "diagnose_compile",
    "diagnose_exception",
    "diagnostics_report",
]

# EOF
