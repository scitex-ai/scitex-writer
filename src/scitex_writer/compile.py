#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# Timestamp: 2026-01-27
# File: src/scitex_writer/compile.py

"""Compilation functions for LaTeX manuscripts.

Usage::

    import scitex_writer as sw

    # Compile manuscript
    result = sw.compile.manuscript("./my-paper")

    # With options
    result = sw.compile.manuscript("./my-paper", draft=True, no_figs=True)

    # Compile other document types
    result = sw.compile.supplementary("./my-paper")
    result = sw.compile.revision("./my-paper", track_changes=True)

    # Compile raw LaTeX content with color mode support
    result = sw.compile.content(
        latex_content,
        project_dir="./my-paper",  # Optional, for .preview/ output
        color_mode="dark",         # 'light' or 'dark'
    )

    # Version-diff PDF (latexdiff markup vs the previous committed version)
    result = sw.compile.diff("./my-paper")

    # Snapshot the compiled outputs into the versions directory
    result = sw.compile.archive("./my-paper")
"""

from typing import Literal as _Literal
from typing import Optional as _Optional

from ._dataclasses import CompilationResult
from ._mcp.handlers import compile_manuscript as _compile_manuscript
from ._mcp.handlers import compile_revision as _compile_revision
from ._mcp.handlers import compile_supplementary as _compile_supplementary
from ._mcp.handlers import process_archive as _process_archive
from ._mcp.handlers import process_diff as _process_diff
from ._utils._latexmk import DEFAULT_TIMEOUT_SEC as _DIFF_TIMEOUT_SEC

try:
    from scitex_dev.decorators import supports_return_as as _supports_return_as
except ImportError:

    def _supports_return_as(fn):
        return fn


@_supports_return_as
def manuscript(
    project_dir: str,
    timeout: int = 300,
    no_figs: bool = False,
    no_tables: bool = False,
    no_diff: bool = False,
    draft: bool = False,
    dark_mode: bool = False,
    quiet: bool = False,
    verbose: bool = False,
    engine: str | None = None,
) -> dict:
    """Compile manuscript to PDF.

    Args:
        project_dir: Path to scitex-writer project directory.
        timeout: Compilation timeout in seconds.
        no_figs: Skip figure processing.
        no_tables: Skip table processing.
        no_diff: Skip diff generation.
        draft: Fast single-pass compilation.
        dark_mode: Enable dark mode output.
        quiet: Suppress output.
        verbose: Verbose output.
        engine: LaTeX engine override ('tectonic', 'latexmk', '3pass').

    Returns:
        Dict with success status, pdf_path, and any errors.
    """
    return _compile_manuscript(
        project_dir,
        timeout=timeout,
        no_figs=no_figs,
        no_tables=no_tables,
        no_diff=no_diff,
        draft=draft,
        dark_mode=dark_mode,
        quiet=quiet,
        verbose=verbose,
        engine=engine,
    )


@_supports_return_as
def supplementary(
    project_dir: str,
    timeout: int = 300,
    no_figs: bool = False,
    no_tables: bool = False,
    no_diff: bool = False,
    draft: bool = False,
    quiet: bool = False,
    engine: str | None = None,
    dark_mode: bool = False,
) -> dict:
    """Compile supplementary materials to PDF.

    Args:
        project_dir: Path to scitex-writer project directory.
        timeout: Compilation timeout in seconds.
        no_figs: Skip figure processing.
        no_tables: Skip table processing.
        no_diff: Skip diff generation.
        draft: Fast single-pass compilation.
        quiet: Suppress output.
        engine: LaTeX engine override ('tectonic', 'latexmk', '3pass').
        dark_mode: Enable dark mode output.

    Returns:
        Dict with success status, pdf_path, and any errors.
    """
    return _compile_supplementary(
        project_dir,
        timeout=timeout,
        no_figs=no_figs,
        no_tables=no_tables,
        no_diff=no_diff,
        draft=draft,
        quiet=quiet,
        engine=engine,
        dark_mode=dark_mode,
    )


@_supports_return_as
def revision(
    project_dir: str,
    track_changes: bool = False,
    timeout: int = 300,
    no_diff: bool = True,
    draft: bool = False,
    quiet: bool = False,
    engine: str | None = None,
    dark_mode: bool = False,
) -> dict:
    """Compile revision document to PDF.

    Args:
        project_dir: Path to scitex-writer project directory.
        track_changes: Enable change tracking.
        timeout: Compilation timeout in seconds.
        no_diff: Skip diff generation.
        draft: Fast single-pass compilation.
        quiet: Suppress output.
        engine: LaTeX engine override ('tectonic', 'latexmk', '3pass').
        dark_mode: Enable dark mode output.

    Returns:
        Dict with success status, pdf_path, and any errors.
    """
    return _compile_revision(
        project_dir,
        track_changes=track_changes,
        timeout=timeout,
        no_diff=no_diff,
        draft=draft,
        quiet=quiet,
        engine=engine,
        dark_mode=dark_mode,
    )


@_supports_return_as
def content(
    latex_content: str,
    project_dir: str | None = None,
    color_mode: str = "light",
    name: str = "content",
    timeout: int = 60,
    keep_aux: bool = False,
) -> CompilationResult:
    """Compile raw LaTeX content to PDF.

    Creates a standalone document from the provided LaTeX content and compiles
    it to PDF. Supports light/dark color modes for comfortable viewing.

    Args:
        latex_content: Raw LaTeX content to compile. Can be:
            - A complete document (with \\documentclass)
            - Document body only (will be wrapped automatically)
        project_dir: Optional path to scitex-writer project. If provided,
            PDF is copied to the project's .preview/ directory.
        color_mode: Color theme: 'light' (default) or 'dark' (Monaco #1E1E1E).
        name: Name for the output (used in filename).
        timeout: Compilation timeout in seconds.
        keep_aux: Keep auxiliary files (.aux, .log, etc.) after compilation.

    Returns:
        ``CompilationResult`` dataclass. Always carries ``success`` /
        ``exit_code`` / ``stdout`` / ``stderr`` / ``output_pdf`` /
        ``log_file`` / ``color_mode`` / ``temp_dir`` / ``message`` —
        unified across success / latexmk-fail / timeout / internal-
        exception paths. Migrated from the legacy ad-hoc dict return in
        2026-06-10 (G1 follow-up to G2 atomic publish + G3 flock).
        Dict-shape JSON callers can serialize via
        ``dataclasses.asdict(result)``.

    Example::

        import scitex_writer as sw

        # Compile simple content
        result = sw.compile.content(
            r"\\section{Introduction}\\nThis is my introduction.",
            color_mode="dark",
        )
    """
    from ._compile.content import compile_content as _compile_content

    return _compile_content(
        latex_content,
        project_dir=project_dir,
        color_mode=color_mode,
        name=name,
        timeout=timeout,
        keep_aux=keep_aux,
    )


@_supports_return_as
def diff(
    project_dir: str,
    doc_type: _Literal["manuscript", "supplementary", "revision"] = "manuscript",
    no_diff: bool = False,
    diff_from: _Optional[str] = None,
    timeout_sec: int = _DIFF_TIMEOUT_SEC,
) -> dict:
    """Build the version-diff PDF for ``doc_type`` (latexdiff markup).

    The pure-Python port of ``scripts/shell/modules/process_diff.sh``: reads the
    PREVIOUS version of the compiled ``.tex`` out of git history, runs latexdiff
    against the current one, stamps a metadata + ``fancyhdr`` signature block, and
    compiles the result with latexmk (bounded by ``timeout_sec``).

    ``diff_from`` overrides the OLD version (default: the previous commit that
    touched the compiled ``.tex``). With NO previous version this FAILS -- the
    shell used to compile current-vs-current, whose unmarked PDF is
    indistinguishable from "nothing changed". Missing ``latexdiff`` / ``latexmk``
    likewise fail with an install hint rather than emitting a wrong PDF.

    Returns ``{success, from_hash, to_hash, diff_tex, diff_pdf, pdf_bytes,
    skipped, error}``.
    """
    return _process_diff(project_dir, doc_type, no_diff, diff_from, timeout_sec)


@_supports_return_as
def archive(
    project_dir: str,
    doc_type: _Literal["manuscript", "supplementary", "revision"] = "manuscript",
    no_archive: bool = False,
) -> dict:
    """Snapshot the compiled outputs of ``doc_type`` into the versions directory.

    The pure-Python port of ``scripts/shell/modules/process_archive.sh``: copies
    the compiled PDF/TeX and the diff PDF/TeX to
    ``<archive_dir>/<stem>_<YYYYmmdd-HHMMSS>_<commit>.<ext>``, plus an un-stamped
    "current" copy of each.

    Archives ONLY a clean working tree -- a snapshot stamped with a commit hash it
    does not actually hold would be a lie -- so a dirty tree returns
    ``skipped=True`` with a ``skip_reason``.

    Returns ``{success, archive_id, archived, versions_dir, missing, skipped,
    skip_reason, error}``.
    """
    return _process_archive(project_dir, doc_type, no_archive)


__all__ = ["manuscript", "supplementary", "revision", "content", "diff", "archive"]

# EOF
