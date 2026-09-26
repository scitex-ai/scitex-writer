#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# File: src/scitex_writer/_compile/_artifacts.py

"""
Where a compile's inputs and outputs live -- the part of running a compile
that never runs anything.

Extracted from ``_runner.py`` so the runner is only the orchestration:
build the command, execute it, judge the outcome, record it. Everything
here answers a WHERE question (which script, which log, which PDF) and is
shared by the runner and its tests.
"""

from __future__ import annotations

from pathlib import Path
from typing import Optional

from .._dataclasses.config import DOC_TYPE_DIRS
from ..workspace_layout import compile_script_relpath

EXIT_PROMOTED_WITH_WARNINGS = 3
"""The compile scripts' exit code for "a valid PDF was produced and promoted,
but the engine exited non-zero" -- in practice a non-fatal bibtex error on a
stub/duplicate bib entry, which makes latexmk exit 12 even though pdfTeX
finalized a complete PDF. Set by
modules/compilation_compiled_tex_to_compiled_pdf.sh and propagated by
compile_{manuscript,supplementary,revision}.sh.

It is a DISTINCT code, not 0, precisely so the state stays distinguishable from
a clean compile: the PDF is kept (destroying a usable manuscript over a
warning-grade bib problem is the bug being fixed here), but no one -- human or
caller -- is told the run was clean."""

_PROMOTED_WARNING = (
    "PDF PROMOTED despite a non-zero engine exit: the document compiled to "
    "{pages} page(s), but the engine reported an error -- usually a non-fatal "
    "bibtex problem such as a stub or duplicate bib entry. The PDF is usable; "
    "FIX THE BIBLIOGRAPHY BEFORE SUBMISSION (see the .log / .blg)."
)


def _doc_latex_log(project_dir: Path, doc_type: str) -> Path:
    """The document's OWN LaTeX log -- where pdfTeX writes "Output written on".

    Deliberately not `_find_output_files`'s "newest *.log", which can be the
    tee'd global.log rather than the document's own log.
    """
    return project_dir / DOC_TYPE_DIRS[doc_type] / "logs" / f"{doc_type}.log"


def _get_compile_script(project_dir: Path, doc_type: str) -> Optional[Path]:
    """
    Get compile script path for document type.

    Delegates to :mod:`scitex_writer.workspace_layout`, which is the published
    single source of truth for where writer keeps things. It used to spell the
    ``scripts/shell/compile_<doc_type>.sh`` tail out here, three times; that
    private copy is what a downstream caller had to guess at, and guessing it
    wrong is what made full compilation fail with a bare rc=127.

    Parameters
    ----------
    project_dir : Path
        Path to the writer WORKSPACE -- the directory holding ``scripts/``,
        ``config/`` and ``01_manuscript/``. For a project root that is
        ``scitex_writer.workspace_layout.workspace_dir(project_root)``, not the
        root itself.
    doc_type : str
        Document type ('manuscript', 'supplementary', 'revision')

    Returns
    -------
    Optional[Path]
        Path to the compilation script, or ``None`` for an unknown
        ``doc_type`` -- the shape ``run_compile`` already handles.
    """
    try:
        return project_dir / compile_script_relpath(doc_type)
    except ValueError:
        return None


def _find_output_files(
    project_dir: Path,
    doc_type: str,
) -> tuple:
    """
    Find generated output files after compilation.

    Parameters
    ----------
    project_dir : Path
        Path to project directory
    doc_type : str
        Document type

    Returns
    -------
    tuple
        (output_pdf, diff_pdf, log_file)
    """
    doc_dir = project_dir / DOC_TYPE_DIRS[doc_type]

    # Find generated PDF
    pdf_name = f"{doc_type}.pdf"
    potential_pdf = doc_dir / pdf_name
    output_pdf = potential_pdf if potential_pdf.exists() else None

    # Check for diff PDF
    diff_name = f"{doc_type}_diff.pdf"
    potential_diff = doc_dir / diff_name
    diff_pdf = potential_diff if potential_diff.exists() else None

    # Find log file
    log_dir = doc_dir / "logs"
    log_file = None
    if log_dir.exists():
        log_files = list(log_dir.glob("*.log"))
        if log_files:
            log_file = max(log_files, key=lambda p: p.stat().st_mtime)

    return output_pdf, diff_pdf, log_file


__all__ = [
    "EXIT_PROMOTED_WITH_WARNINGS",
    "_PROMOTED_WARNING",
    "_doc_latex_log",
    "_find_output_files",
    "_get_compile_script",
]

# EOF
