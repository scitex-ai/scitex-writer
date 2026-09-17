#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# File: tests/scitex_writer/_django/test_views_editor_app_header.py

"""Writer's leaf header: one header, our title, OUR version, the host's picker.

The hub's header showed its own `v0.20.0-alpha` for a writer build, and a source
comment claimed 2.20.0; neither is a claim writer can make about itself. The leaf
now states which package and version is serving the page, in the SDK's own
manifest field, and offers the canonical project-selector slot — rendering the
picker only when the host's tag library is actually installed, because
`{% load %}`ing a library that is not there is a hard TemplateSyntaxError.
"""

import json
import re
import tempfile
from pathlib import Path

import pytest
from django.template.loader import render_to_string
from django.test import RequestFactory

from scitex_writer._django import views

_DJANGO_DIR = Path(__file__).resolve().parents[3] / "src" / "scitex_writer" / "_django"
_PROJECT_ROOT = _DJANGO_DIR.parents[2]
_MANIFEST = _DJANGO_DIR / "manifest.json"
_PYPROJECT = _PROJECT_ROOT / "pyproject.toml"
_HEADER_CSS = _DJANGO_DIR / "static" / "writer" / "css" / "app-header.css"

_HEADER_OPEN = '<header class="writer-app-header" id="writer-app-header">'


@pytest.fixture
def project_dir():
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        (root / "01_manuscript" / "contents").mkdir(parents=True)
        (root / "01_manuscript" / "contents" / "abstract.tex").write_text(
            "\\begin{abstract}x\\end{abstract}\n", encoding="utf-8"
        )
        (root / "00_shared").mkdir()
        yield root


def _editor_html(project_dir) -> str:
    request = RequestFactory().get(f"/?working_dir={project_dir}")
    return views.editor_page(request).content.decode()


def _header_block(body: str) -> str:
    start = body.index(_HEADER_OPEN)
    end = body.index("</header>", start)
    return body[start:end]


def _manifest_version() -> str:
    return json.loads(_MANIFEST.read_text(encoding="utf-8"))["version"]


def _pyproject_version() -> str:
    for line in _PYPROJECT.read_text(encoding="utf-8").splitlines():
        if line.startswith("version"):
            return line.split("=")[1].strip().strip('"')
    raise AssertionError("pyproject.toml has no version")


# --- the version is one number, from one place --------------------------------


def test_manifest_version_matches_pyproject():
    # Arrange
    declared = _pyproject_version()
    # Act
    manifest = _manifest_version()
    # Assert
    assert manifest == declared


def test_manifest_version_is_not_the_sdk_placeholder():
    # Arrange
    placeholder = "0.0.0"
    # Act
    manifest = _manifest_version()
    # Assert
    assert manifest != placeholder


def test_the_header_shows_the_manifest_version(project_dir):
    # Arrange
    expected = _manifest_version()
    # Act
    block = _header_block(_editor_html(project_dir))
    # Assert
    assert f"v{expected}" in block


def test_the_header_shows_the_leaf_package_not_a_host_or_a_comment(project_dir):
    # Arrange
    claims_from_elsewhere = ["v0.20.0-alpha", "2.20.0", "0.20.0-alpha"]
    # Act
    block = _header_block(_editor_html(project_dir))
    # Assert
    assert [claim for claim in claims_from_elsewhere if claim in block] == []


def test_the_page_publishes_generic_version_metadata(project_dir):
    # Arrange
    expected = f'<meta name="scitex-app-version" content="writer@{_manifest_version()}">'
    # Act
    body = _editor_html(project_dir)
    # Assert
    assert expected in body


def test_the_views_app_config_is_the_sdk_one():
    # Arrange
    from scitex_app.embed import ScitexAppConfig

    # Act
    config = views._app_config()
    # Assert
    assert isinstance(config, ScitexAppConfig)


# --- exactly one header -------------------------------------------------------


def test_the_editor_page_renders_exactly_one_header(project_dir):
    # Arrange
    marker = _HEADER_OPEN
    # Act
    body = _editor_html(project_dir)
    # Assert
    assert body.count(marker) == 1


def test_a_host_that_renders_its_own_header_gets_no_second_one(project_dir):
    # Arrange
    context = {
        "app_name": "writer",
        "project_dir": str(project_dir),
        "writer_version": _manifest_version(),
        "writer_label": "Writer",
        "project_picker_available": False,
        "app_header_rendered": True,
    }
    # Act
    body = render_to_string("writer/editor.html", context)
    # Assert
    assert _HEADER_OPEN not in body


def test_the_header_names_the_app_from_the_manifest(project_dir):
    # Arrange
    label = json.loads(_MANIFEST.read_text(encoding="utf-8"))["label"]
    # Act
    block = _header_block(_editor_html(project_dir))
    # Assert
    assert f">{label}<" in block


def test_the_header_precedes_the_toolbar(project_dir):
    # Arrange
    body = _editor_html(project_dir)
    # Act
    header = body.index(_HEADER_OPEN)
    toolbar = body.index('class="writer-toolbar"')
    # Assert
    assert header < toolbar


def test_no_template_comment_leaks_into_the_page(project_dir):
    # Arrange
    # Django's `{# #}` is SINGLE-LINE: a multi-line one ships as page text. It
    # has already happened once in this file's history, so it is pinned here.
    phrases = ["leaf header", "Generic version metadata", "endcomment", "{#"]
    # Act
    body = _editor_html(project_dir)
    # Assert
    assert [phrase for phrase in phrases if phrase in body] == []


# --- the host's picker slot ---------------------------------------------------


def test_the_header_offers_the_canonical_project_selector_slot(project_dir):
    # Arrange
    slot = 'class="stx-app-header__slot--project-selector'
    # Act
    block = _header_block(_editor_html(project_dir))
    # Assert
    assert slot in block


def test_the_header_offers_the_actions_slot(project_dir):
    # Arrange
    slot = "stx-app-header__slot--actions"
    # Act
    block = _header_block(_editor_html(project_dir))
    # Assert
    assert slot in block


def test_the_picker_renders_only_when_its_tag_library_is_installed(project_dir):
    # Arrange
    available = views._project_picker_available()
    # Act
    body = _editor_html(project_dir)
    # Assert
    assert ("writer-project-scope" in body) is available


def test_an_installed_picker_library_would_be_detected():
    # Arrange
    from django.template import engines

    # Act
    libraries = engines["django"].engine.template_libraries
    # Assert
    assert "static" in libraries and views._project_picker_available() == (
        "scitex_project_picker" in libraries
    )


# --- the header's own layout --------------------------------------------------


def test_the_header_stylesheet_is_loaded(project_dir):
    # Arrange
    stylesheet = "writer/css/app-header.css"
    # Act
    body = _editor_html(project_dir)
    # Assert
    assert f'href="/static/{stylesheet}"' in body


def test_the_header_wraps_instead_of_overflowing_a_phone():
    # Arrange
    css = _HEADER_CSS.read_text(encoding="utf-8")
    # Act
    rule = re.search(r"\.writer-app-header\s*\{([^}]*)\}", css).group(1)
    # Assert
    assert "flex-wrap: wrap" in rule


def test_host_picker_controls_are_phone_sized():
    # Arrange
    css = _HEADER_CSS.read_text(encoding="utf-8")
    # Act
    phone = css[css.index("@media (max-width: 768px)") :]
    # Assert
    assert re.search(
        r"\.writer-app-header (select|button|a)[^{]*\{[^}]*"
        r"min-height:\s*var\(--writer-touch-target-min",
        phone,
    )


# EOF
