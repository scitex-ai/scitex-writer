#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# File: src/scitex_writer/_utils/_pdf_pages.py

r"""Ground-truth page count of a PDF a compile run just produced.

This is the discriminator between the two outcomes a NON-ZERO engine exit can
hide:

* **produced a PDF** -- pdfTeX finalized a complete document and only a
  *warning-grade* problem (typically a non-fatal ``bibtex`` error on a stub
  entry, which makes ``latexmk`` exit 12) made the engine return non-zero. The
  artifact is usable and must NOT be destroyed.
* **produced nothing** -- the run really failed. There is no PDF, or the file on
  disk is a stale leftover / a zero-page husk. This must still fail loud.

``pages > 0`` is the line between them, and it is deliberately established from
the *LaTeX log of this run* first: pdfTeX writes

    Output written on <path> (7 pages, 129061 bytes).

ONLY when it finalized a PDF during that run, so the line cannot be inherited
from an earlier successful compile the way a stale ``.pdf`` on disk can. The raw
PDF byte scan is the fallback for when the log is absent or was cleaned.
"""

from __future__ import annotations

import re
import zlib
from pathlib import Path
from typing import Optional

_OUTPUT_WRITTEN_RE = re.compile(r"Output written on .*?\((\d+) pages?[,)]")
"""pdfTeX's per-run "I finalized a PDF" line, with its page count."""

_PAGE_OBJ_RE = re.compile(rb"/Type\s*/Page[^s]")
"""A page object. ``/Type /Pages`` is the page-TREE root, hence the ``[^s]``."""

_STREAM_RE = re.compile(rb"stream\r?\n(.*?)\r?\nendstream", re.DOTALL)
"""A raw PDF stream body. pdflatex writes PDF 1.5, which packs the page objects
into COMPRESSED object streams (/ObjStm) -- so scanning the raw bytes alone finds
zero pages on a perfectly good manuscript. The streams must be inflated first."""


def _page_objects(data: bytes) -> int:
    """Count page objects in ``data``, inflating any compressed streams first."""
    pages = len(_PAGE_OBJ_RE.findall(data))
    for match in _STREAM_RE.finditer(data):
        try:
            inflated = zlib.decompress(match.group(1))
        except zlib.error:
            continue  # not a Flate stream (image data, etc.) -- nothing to count
        pages += len(_PAGE_OBJ_RE.findall(inflated))
    return pages


def pages_from_latex_log(log_file: Path) -> int:
    """Return the page count pdfTeX reported for THIS run, or 0 if unknown."""
    try:
        text = Path(log_file).read_text(encoding="utf-8", errors="replace")
    except (OSError, ValueError):
        return 0
    matches = _OUTPUT_WRITTEN_RE.findall(text)
    return int(matches[-1]) if matches else 0


def pages_in_pdf(pdf_file: Path) -> int:
    """Return the number of page objects in ``pdf_file``, or 0 if unreadable."""
    try:
        data = Path(pdf_file).read_bytes()
    except (OSError, ValueError):
        return 0
    return _page_objects(data)


def produced_page_count(pdf_file: Path, log_file: Optional[Path] = None) -> int:
    """Return the page count of the PDF produced by this run (0 = none produced).

    Prefers the LaTeX log's ``Output written on ... (N pages`` line -- it is
    per-run evidence -- and falls back to scanning the PDF itself. A missing PDF
    is always 0, even when a log claims otherwise: the artifact must exist.
    """
    pdf_file = Path(pdf_file)
    if not pdf_file.is_file():
        return 0
    if log_file is not None:
        pages = pages_from_latex_log(log_file)
        if pages > 0:
            return pages
    return pages_in_pdf(pdf_file)


__all__ = [
    "pages_from_latex_log",
    "pages_in_pdf",
    "produced_page_count",
]

# EOF
