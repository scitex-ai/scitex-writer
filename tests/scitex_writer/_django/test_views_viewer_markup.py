#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# File: tests/scitex_writer/_django/test_views_viewer_markup.py

"""The viewer page must not ship a raw template comment to the browser.

Django's ``{# ... #}`` is a SINGLE-LINE comment: given a newline it stops being
a comment at all and the lexer hands back the whole block as TEXT
(``Lexer("A{# x\\ny #}B").tokenize()`` -> one TEXT token, no COMMENT token). The
favicon rationale in ``writer/viewer.html`` was written as a five-line ``{# #}``
block, so every ``/viewer/`` response carried the prose into the served HTML,
bare ``{#`` and all: measured this session on the develop tree, the rendered
page contained the literal string ``{# The bare SVG icon link is NOT here:``.

A comment that renders is not a comment — the file reads as documented while the
browser receives the documentation. ``{% comment %}`` carries multi-line prose
(and is what the fix uses).
"""
from __future__ import annotations

import tempfile
from pathlib import Path

import pytest
from django.test import RequestFactory

from scitex_writer._django import views

# The first words of the rationale in viewer.html: if the comment is parsed as
# a comment they cannot reach the page, whatever wording the note grows.
_RATIONALE_OPENING = "bare SVG icon link"


@pytest.fixture
def project_dir():
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        (root / "01_manuscript" / "contents").mkdir(parents=True)
        (root / "01_manuscript" / "contents" / "01_intro.tex").write_text(
            r"\section{Intro}"
        )
        (root / "00_shared").mkdir()
        yield root


def _viewer_html(project_dir) -> str:
    request = RequestFactory().get(f"/viewer/?working_dir={project_dir}")
    return views.viewer_page(request).content.decode()


def test_the_viewer_page_carries_no_raw_template_comment(project_dir):
    # Arrange
    # (the fixture builds the minimal project the view needs)
    # Act
    html = _viewer_html(project_dir)
    # Assert
    assert "{#" not in html


def test_the_viewer_page_does_not_print_the_favicon_rationale(project_dir):
    # Arrange
    # (the fixture builds the minimal project the view needs)
    # Act
    html = _viewer_html(project_dir)
    # Assert
    assert _RATIONALE_OPENING not in html
