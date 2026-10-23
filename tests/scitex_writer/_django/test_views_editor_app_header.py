#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# File: tests/scitex_writer/_django/test_views_editor_app_header.py

"""Writer's leaf header: one header mount, our title, OUR version, the host's picker.

The hub's header showed its own `v0.20.0-alpha` for a writer build, and a source
comment claimed 2.20.0; neither is a claim writer can make about itself. The leaf
states which installed package version is serving the page through the
`data-stx-app-header` mount (client-rendered badge from `data-app-version`),
and offers the picker partial that feeds the primitive's canonical
project-selector slot — rendering the picker only when the host's tag
library is actually installed, because `{% load %}`ing a library that is
not there is a hard TemplateSyntaxError.
"""

import json
import re
import tempfile
from importlib.metadata import version
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

_HEADER_OPEN = '<div class="writer-app-header">'
_MOUNT_DIV = "<div data-stx-app-header"
_SHARED_HEADER_CSS = "scitex_sdk/ui/css/app/app-header.css"


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
    end_marker = 'header-picker.js"></script>'
    end = body.index(end_marker, start) + len(end_marker)
    return body[start:end]


def _installed_version() -> str:
    manifest = json.loads(_MANIFEST.read_text(encoding="utf-8"))
    return version(manifest["pip_package"])


def _pyproject_version() -> str:
    for line in _PYPROJECT.read_text(encoding="utf-8").splitlines():
        if line.startswith("version"):
            return line.split("=")[1].strip().strip('"')
    raise AssertionError("pyproject.toml has no version")


# --- the version is one number, from one place --------------------------------


def test_installed_version_matches_pyproject():
    # Arrange
    declared = _pyproject_version()
    # Act
    installed = _installed_version()
    # Assert
    assert installed == declared


def test_manifest_delegates_version_to_installed_package_omits_manifest_version():
    # Arrange: pytest fixtures and local setup.
    placeholder = '0.0.0'
    # Act: exercise the real scenario.
    manifest = json.loads(_MANIFEST.read_text(encoding='utf-8'))
    # Assert
    assert 'version' not in manifest


def test_manifest_delegates_version_to_installed_package_resolves_installed_version():
    # Arrange: pytest fixtures and local setup.
    placeholder = '0.0.0'
    # Act: exercise the real scenario.
    manifest = json.loads(_MANIFEST.read_text(encoding='utf-8'))
    # Assert
    assert _installed_version() != placeholder


def test_the_header_shows_the_installed_version(project_dir):
    # Arrange — the primitive renders the badge client-side from the
    # data attribute; the server contract is the attribute itself.
    expected = _installed_version()
    # Act
    block = _header_block(_editor_html(project_dir))
    # Assert
    assert f'data-app-version="{expected}"' in block


def test_the_header_shows_the_leaf_package_not_a_host_or_a_comment(project_dir):
    # Arrange
    claims_from_elsewhere = ["v0.20.0-alpha", "2.20.0", "0.20.0-alpha"]
    # Act
    block = _header_block(_editor_html(project_dir))
    # Assert
    assert [claim for claim in claims_from_elsewhere if claim in block] == []


def test_the_page_publishes_generic_version_metadata(project_dir):
    # Arrange
    expected = f'<meta name="scitex-app-version" content="writer@{_installed_version()}">'
    # Act
    body = _editor_html(project_dir)
    # Assert
    assert expected in body


def test_the_views_app_config_is_the_sdk_one():
    # Arrange
    from scitex_sdk import app

    # Act
    config = views._app_config()
    # Assert
    assert isinstance(config, app.embed.ScitexAppConfig)


# --- exactly one header -------------------------------------------------------


def test_the_editor_page_renders_exactly_one_header(project_dir):
    # Arrange — one AppHeader mount; toolbars below are functional bars,
    # not the app row.
    # Act
    body = _editor_html(project_dir)
    # Assert
    assert body.count(_MOUNT_DIV) == 1


def test_a_host_that_renders_its_own_header_gets_no_second_one(project_dir):
    # Arrange
    context = {
        "app_name": "writer",
        "project_dir": str(project_dir),
        "writer_version": _installed_version(),
        "writer_label": "SciTeX Writer",
        "project_picker_available": False,
        "app_header_rendered": True,
    }
    # Act
    body = render_to_string("writer/editor.html", context)
    # Assert
    assert _MOUNT_DIV not in body


def test_the_header_names_the_app_with_the_full_header_title(project_dir):
    # Arrange — tile label and header title are independent (operator
    # 2026-10-23): the header keeps the full product title.
    # Act
    block = _header_block(_editor_html(project_dir))
    # Assert
    assert 'data-app-title="Writer"' in block


def test_the_header_title_differs_from_the_short_tile_label():
    # Arrange — the manifest carries the short tile form, never the header.
    # Act
    label = json.loads(_MANIFEST.read_text(encoding="utf-8"))["label"]
    # Assert
    assert label == "Writer"


def test_the_header_precedes_the_toolbar(project_dir):
    # Arrange
    body = _editor_html(project_dir)
    # Act
    header = body.index(_MOUNT_DIV)
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
    # Arrange — the slot is created client-side by the primitive; the
    # server contract is the picker include that feeds it. The include
    # resolves server-side, so assert its rendered marker, not its name.
    # Act
    block = _header_block(_editor_html(project_dir))
    # Assert
    assert '<div class="writer-project-scope">' in block


def test_the_header_offers_the_actions_slot(project_dir):
    # Arrange — the actions slot is created client-side by the primitive;
    # the leaf must NOT define its own (a second set of buttons would be a
    # second source of truth). Assert absence, not presence.
    # Act
    block = _header_block(_editor_html(project_dir))
    # Assert
    assert "stx-app-header__actions" not in block


def test_the_header_mounts_the_shared_primitive(project_dir):
    """The leaf emits the AppHeader mount point, not a hand-rolled row."""
    # Arrange
    block = _header_block(_editor_html(project_dir))
    # Act
    mounted = _MOUNT_DIV in block
    # Assert
    assert mounted


def test_the_header_defines_no_shared_element_classes(project_dir):
    """No leaf-defined stx-app-header__* element classes: the canonical
    class names live in the SDK's rendered output, not in leaf markup."""
    # Arrange
    leaf_definitions = (
        'class="stx-app-header ',
        "stx-app-header__title",
        "stx-app-header__version",
        "stx-app-header__actions",
    )
    # Act
    block = _header_block(_editor_html(project_dir))
    # Assert
    assert [markup for markup in leaf_definitions if markup in block] == []


def test_the_retired_slot_adapter_classes_are_gone(project_dir):
    """The leaf-only classes that shadowed the shared slot must not come back."""
    # Arrange
    retired = ("writer-app-header__slot", "writer-app-header__picker")
    # Act
    block = _header_block(_editor_html(project_dir))
    # Assert
    assert [markup for markup in retired if markup in block] == []


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


def test_the_shared_header_stylesheet_is_loaded(project_dir):
    """The row's layout is the SDK's, so the SDK's sheet has to be on the page."""
    # Arrange
    stylesheet = _SHARED_HEADER_CSS
    # Act
    body = _editor_html(project_dir)
    # Assert
    assert f'href="/static/{stylesheet}"' in body


def test_the_leaf_no_longer_redefines_the_shared_header_row():
    """The row's flex layout has ONE definition (scitex-ui), not two.

    Writer keeps only what the shared sheet does not cover: the identity
    grouping and the picker control's phone sizing. A leaf rule that sets the
    row's own flex layout again is exactly the duplicate this adoption removed.
    """
    # Arrange
    row_properties = ("display", "align-items", "flex-wrap", "gap", "padding")
    # Act
    css = re.sub(r"/\*.*?\*/", "", _HEADER_CSS.read_text(encoding="utf-8"), flags=re.S)
    leaf_row_rule = re.search(r"\.writer-app-header\s*\{([^}]*)\}", css)
    # Assert
    assert leaf_row_rule is None or not any(
        prop in leaf_row_rule.group(1) for prop in row_properties
    )


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
