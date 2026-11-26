#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# File: tests/integration/test_supplementary_title_page.py

"""The supplementary title page names the manuscript title exactly once.

Regression for scitex-ai/scitex-writer#518. ``02_supplementary/base.tex``
inputs the consumer-owned ``00_shared/title.tex`` (which both defines
``\\scitexmanuscripttitle`` and calls ``\\title``) and then sets the
supplementary title. elsarticle's ``\\title`` APPENDS to ``\\@title`` and to
``\\useelstitle`` instead of replacing them, so the page used to read
``<title> Supplementary Material for: <title>``.

The test compiles the REAL frontmatter block of the shipped ``base.tex``
against the REAL template ``title.tex``/``authors.tex`` and the real
``title_scope`` hook with elsarticle and pdflatex, then reads the rendered PDF
text. Nothing is restated from the fix.
"""

from __future__ import annotations

import re
import shutil
import subprocess
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
BASE_TEX = REPO_ROOT / "02_supplementary" / "base.tex"
SHARED = REPO_ROOT / "00_shared"
PREFIX = "Supplementary Material for:"

pytestmark = pytest.mark.skipif(
    shutil.which("pdflatex") is None, reason="pdflatex not installed"
)


def _template_title() -> str:
    """The title text the shipped template sets, read from title.tex itself."""
    src = (SHARED / "title.tex").read_text(encoding="utf-8")
    match = re.search(
        r"\\newcommand\{\\scitexmanuscripttitle\}\{%\s*(.*?)\s*\}", src, re.S
    )
    assert match, "template title.tex no longer defines \\scitexmanuscripttitle"
    return " ".join(match.group(1).split())


def _frontmatter_block() -> str:
    src = BASE_TEX.read_text(encoding="utf-8")
    match = re.search(r"\\begin\{frontmatter\}.*?\\end\{frontmatter\}", src, re.S)
    assert match, "02_supplementary/base.tex has no frontmatter block"
    return match.group(0)


def _compile_supplementary_frontmatter(tmp_path: Path) -> Path:
    shared = tmp_path / "00_shared"
    (shared / "latex_styles").mkdir(parents=True)
    for rel in (
        "title.tex",
        "authors.tex",
        "keywords.tex",
        "latex_styles/title_scope.tex",
    ):
        shutil.copy(SHARED / rel, shared / rel)
    # Page 2 prints elsarticle's running title (\useelstitle), which the same
    # append bug used to double as well.
    (tmp_path / "supp.tex").write_text(
        "\\documentclass[preprint,12pt]{elsarticle}\n"
        "\\input{./00_shared/latex_styles/title_scope}\n"
        "\\begin{document}\n"
        f"{_frontmatter_block()}\n"
        "\\clearpage\n"
        "RUNNING: \\useelstitle\n"
        "\\end{document}\n",
        encoding="utf-8",
    )
    proc = subprocess.run(
        ["pdflatex", "-interaction=nonstopmode", "-halt-on-error", "supp.tex"],
        cwd=tmp_path,
        capture_output=True,
        text=True,
    )
    assert proc.returncode == 0, proc.stdout[-3000:]
    return tmp_path / "supp.pdf"


def _page_texts(pdf: Path) -> list[str]:
    pymupdf = pytest.importorskip("pymupdf")
    with pymupdf.open(pdf) as doc:
        return [" ".join(page.get_text().split()) for page in doc]


def _title_mentions(text: str, title: str) -> list[str]:
    """For each occurrence of ``title`` in ``text``, the text right before it."""
    width = len(PREFIX) + 1
    return [
        text[max(0, m.start() - width) : m.start()].strip()
        for m in re.finditer(re.escape(title), text)
    ]


@pytest.fixture(scope="module")
def rendered(tmp_path_factory):
    """(page texts, template title) of the compiled supplementary frontmatter."""
    pdf = _compile_supplementary_frontmatter(tmp_path_factory.mktemp("supp"))
    return _page_texts(pdf), _template_title()


def test_title_page_shows_title_once_in_supplementary_form(rendered):
    # Arrange
    pages, title = rendered
    # Act
    mentions = _title_mentions(pages[0], title)
    # Assert: exactly one mention, and it is "Supplementary Material for: <title>".
    assert mentions == [PREFIX], pages[0]


def test_running_title_shows_title_once_in_supplementary_form(rendered):
    # Arrange
    pages, title = rendered
    # Act
    running = pages[-1].split("RUNNING:", 1)[1]
    # Assert
    assert _title_mentions(running, title) == [PREFIX], running


# EOF
