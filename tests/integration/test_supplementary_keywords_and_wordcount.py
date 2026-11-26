#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# File: tests/integration/test_supplementary_keywords_and_wordcount.py

"""Supplementary page 1: the shared keywords, and no stray glyph before the word count.

1. Keywords. ``01_manuscript/base.tex`` prints ``00_shared/keywords.tex`` in
   its frontmatter; ``02_supplementary/base.tex`` never input any keywords
   file, so the supplementary had none (and a project's own
   ``02_supplementary/contents/keywords.tex`` silently went stale).
2. Breve. ``formatting.tex`` opened the word-count files on a read stream named
   ``\\wordcount``. ``\\newread`` makes that name a ``\\chardef``, and the
   supplementary template writes ``\\begin{wordcount}...\\end{wordcount}``, so
   ``\\begin`` ran ``\\wordcount`` and typeset character <stream number>: in T1,
   slot 8 is a breve, printed just before "0 supplementary figures, ...".

Both tests compile the REAL shipped files (``base.tex`` frontmatter, the
template ``keywords.tex``, ``formatting.tex`` and the supplementary
``wordcount.tex``) with pdflatex and read the rendered text with PyMuPDF.
"""

from __future__ import annotations

import re
import shutil
import subprocess
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
SHARED = REPO_ROOT / "00_shared"
SUPP = REPO_ROOT / "02_supplementary"

pytestmark = pytest.mark.skipif(
    shutil.which("pdflatex") is None, reason="pdflatex not installed"
)


def _compile(tmp_path: Path, preamble: str, body: str) -> list[str]:
    """Compile ``body`` in ``tmp_path``; return the PDF's page texts."""
    (tmp_path / "doc.tex").write_text(
        "\\documentclass[preprint,12pt]{elsarticle}\n"
        "\\usepackage[T1]{fontenc}\n"
        # Unicode-mapped outline fonts, so "fi" reads back as two letters.
        "\\usepackage{lmodern}\\input{glyphtounicode}\\pdfgentounicode=1\n"
        f"{preamble}\n"
        "\\begin{document}\n"
        f"{body}\n"
        "\\end{document}\n",
        encoding="utf-8",
    )
    proc = subprocess.run(
        ["pdflatex", "-interaction=nonstopmode", "-halt-on-error", "doc.tex"],
        cwd=tmp_path,
        capture_output=True,
        text=True,
    )
    assert proc.returncode == 0, proc.stdout[-3000:]
    pymupdf = pytest.importorskip("pymupdf")
    with pymupdf.open(tmp_path / "doc.pdf") as doc:
        return [" ".join(page.get_text().split()) for page in doc]


def _copy_shared(tmp_path: Path, *rels: str) -> None:
    for rel in rels:
        target = tmp_path / "00_shared" / rel
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy(SHARED / rel, target)


def _template_keywords() -> list[str]:
    """The keywords the template's 00_shared/keywords.tex lists."""
    src = (SHARED / "keywords.tex").read_text(encoding="utf-8")
    match = re.search(r"\\begin\{keyword\}(.*?)\\end\{keyword\}", src, re.S)
    assert match, "template keywords.tex has no keyword environment"
    return [" ".join(k.split()) for k in match.group(1).split("\\sep")]


@pytest.fixture
def frontmatter_text(tmp_path):
    """Page-1 text of the shipped supplementary frontmatter."""
    _copy_shared(
        tmp_path,
        "title.tex",
        "authors.tex",
        "keywords.tex",
        "latex_styles/title_scope.tex",
    )
    block = re.search(
        r"\\begin\{frontmatter\}.*?\\end\{frontmatter\}",
        (SUPP / "base.tex").read_text(encoding="utf-8"),
        re.S,
    ).group(0)
    return _compile(tmp_path, "\\input{./00_shared/latex_styles/title_scope}", block)[0]


@pytest.fixture
def wordcount_text(tmp_path):
    """Page text of the shipped supplementary word-count line, real formatting.tex."""
    _copy_shared(
        tmp_path, "latex_styles/formatting.tex", "latex_styles/title_scope.tex"
    )
    (tmp_path / "wordcount.tex").write_text(
        (SUPP / "contents" / "wordcount.tex").read_text(encoding="utf-8"),
        encoding="utf-8",
    )
    preamble = (
        "\\usepackage{lineno,xcolor,tcolorbox,siunitx,soul,refcount,hyperref}\n"
        "\\input{./00_shared/latex_styles/formatting}"
    )
    # The count files are absent here, so every count reads 0 (the guarded path).
    return _compile(tmp_path, preamble, "\\input{./wordcount}")[0]


def test_supplementary_prints_the_shared_keywords(frontmatter_text):
    # Arrange
    keywords = _template_keywords()

    # Act
    missing = [k for k in keywords if k not in frontmatter_text]

    # Assert
    assert missing == [], frontmatter_text


def test_wordcount_line_starts_with_the_count_not_a_stray_glyph(wordcount_text):
    # Arrange
    marker = " supplementary figures"

    # Act: everything printed before the first count's label
    lead = wordcount_text.split(marker, 1)[0]

    # Assert: only the count itself (the old engine printed "˘ 0" / "¨ 0")
    assert lead == "0", wordcount_text


# EOF
