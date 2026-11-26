#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# File: tests/integration/test_pdf_text_extraction.py

"""Text copied out of a compiled PDF keeps its spaces and ligatures.

pdfTeX with ``\\usepackage[T1]{fontenc}`` and no outline T1 font falls back to
bitmap (Type3) EC fonts. Their glyphs carry no Unicode mapping, so a copy of
"effort" yields "e\\x1bort" and viewers that rely on real space glyphs run the
words together. The test compiles a REAL document with the engine's own font
setup (``00_shared/latex_styles/pdf_text.tex`` after T1 fontenc, as in
``packages.tex``) and reads the text back from the PDF.
"""

from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
STYLES = REPO_ROOT / "00_shared" / "latex_styles"
SENTENCE = (
    "Existing research tools record each step without additional author effort, "
    "and affected readers can find the source."
)

pytestmark = pytest.mark.skipif(
    shutil.which("pdflatex") is None, reason="pdflatex not installed"
)


@pytest.fixture(scope="module")
def page(tmp_path_factory):
    """Text of page 1 (real space glyphs only) of a document using the engine font setup."""
    pymupdf = pytest.importorskip("pymupdf")
    root = tmp_path_factory.mktemp("pdftext")
    (root / "00_shared" / "latex_styles").mkdir(parents=True)
    shutil.copy(STYLES / "pdf_text.tex", root / "00_shared" / "latex_styles")
    (root / "doc.tex").write_text(
        "\\documentclass[preprint,review,12pt]{elsarticle}\n"
        "\\usepackage[T1]{fontenc}\n"
        "\\input{./00_shared/latex_styles/pdf_text}\n"
        "\\begin{document}\n"
        f"{SENTENCE}\n"
        "\\end{document}\n",
        encoding="utf-8",
    )
    proc = subprocess.run(
        ["pdflatex", "-interaction=nonstopmode", "-halt-on-error", "doc.tex"],
        cwd=root,
        capture_output=True,
        text=True,
    )
    assert proc.returncode == 0, proc.stdout[-3000:]
    with pymupdf.open(root / "doc.pdf") as doc:
        # TEXT_INHIBIT_SPACES: report only space glyphs the PDF really
        # contains, as copy-paste in many viewers does, not gaps the
        # extractor guesses from glyph positions.
        return doc[0].get_text(flags=pymupdf.TEXT_INHIBIT_SPACES)


def test_words_are_separated_by_spaces(page):
    # Arrange
    expected = "Existing research tools record each step"
    # Act
    flat = " ".join(page.split())
    # Assert
    assert expected in flat, repr(page)


def test_ff_ligature_round_trips_in_effort(page):
    # Arrange
    expected = "additional author effort"
    # Act
    flat = " ".join(page.split())
    # Assert
    assert expected in flat, repr(page)


def test_ff_ligature_round_trips_in_affected(page):
    # Arrange
    expected = "affected readers"
    # Act
    flat = " ".join(page.split())
    # Assert
    assert expected in flat, repr(page)


def test_fi_ligature_round_trips_in_find(page):
    # Arrange
    expected = "can find the source"
    # Act
    flat = " ".join(page.split())
    # Assert
    assert expected in flat, repr(page)


# EOF
