#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# File: tests/develop/test_writer_plugin_contract.py

"""Writer's half of the ``scitex.apps`` plugin contract (the hub's generic mount).

``pip install scitex-writer`` is the whole install: the host reads ONE entry
point from the ``scitex.apps`` group (``scitex_app.plugins.ENTRY_POINT_GROUP``),
mounts ``<config.name>.urls`` at the manifest route, and lists the launcher tile
from ``_django/manifest.json``. Nothing about Writer is special-cased in hub
code afterwards — which is exactly why the declaration has to be pinned HERE,
in Writer's own CI, instead of being trusted to a reader.

Two failure modes this file exists to catch, both measured rather than imagined:

1. The group name CONTAINS A DOT, so it must stay QUOTED. The unquoted form
   ``[project.entry-points.scitex.apps]`` parses cleanly (tomllib reads it as
   group ``scitex`` holding a nested sub-table), builds and installs — and
   declares nothing any host looks up. The card that requested this work
   specified that unquoted line verbatim; the reference commit
   (scitex-agent-container 4d222b87) quotes it. This test pins the real name.
2. ``mount_policy.login_required`` travels IN the leaf manifest so the host can
   gate the mount with no app-specific code (scitex-hub
   ``apps_app/services/plugin_guards.py`` and ``plugin_apps.py``). Dropping the
   key silently publishes an authenticated-only editor to anonymous users.
"""
from __future__ import annotations

import importlib
import importlib.util
import json
import tomllib
from pathlib import Path

import django.apps

_ROOT = Path(__file__).resolve().parents[2]
_PYPROJECT = _ROOT / "pyproject.toml"
_MANIFEST = _ROOT / "src" / "scitex_writer" / "_django" / "manifest.json"

# The one group name the host reads (scitex_app.plugins.ENTRY_POINT_GROUP).
PLUGIN_GROUP = "scitex.apps"

# The host keys tiles on the entry-point name and mounts by manifest slug, so
# the two have to agree; the leaf name is also the tile's first-wins identity.
EXPECTED_NAME = "writer"

EXPECTED_TARGET = "scitex_writer._django.apps:WriterEditorConfig"


def _entry_point_groups() -> dict:
    return tomllib.loads(_PYPROJECT.read_text(encoding="utf-8"))["project"][
        "entry-points"
    ]


def _manifest() -> dict:
    return json.loads(_MANIFEST.read_text(encoding="utf-8"))


# --- the declaration is one quoted, dotted group name --------------------------


def test_pyproject_declares_the_scitex_apps_entry_point():
    # Arrange
    groups = _entry_point_groups()
    # Act
    value = groups.get(PLUGIN_GROUP, {}).get(EXPECTED_NAME)
    # Assert
    assert value == EXPECTED_TARGET


def test_the_dotted_group_name_is_declared_as_one_group():
    # Arrange
    groups = _entry_point_groups()
    # Act
    declared = PLUGIN_GROUP in groups
    # Assert
    assert declared


def test_the_group_name_is_not_a_nested_scitex_table():
    # Arrange
    groups = _entry_point_groups()
    # Act
    # Unquoted TOML would surface as group "scitex" holding a sub-table, and
    # every host lookup for "scitex.apps" would then find nothing.
    nested = groups.get("scitex")
    # Assert
    assert nested is None


# --- the mount the host derives from the manifest ------------------------------


def test_the_entry_point_name_is_the_manifest_slug():
    # Arrange
    manifest = _manifest()
    # Act
    slug = manifest.get("slug")
    # Assert
    assert slug == EXPECTED_NAME


def test_the_manifest_does_not_override_the_mount_route():
    # Arrange
    manifest = _manifest()
    # Act
    # No "url": the host's default route is apps/<slug>/, so an override here
    # would silently move the mount.
    route_override = manifest.get("url")
    # Assert
    assert route_override in (None, "")


def test_the_manifest_asks_the_host_for_a_login_boundary():
    # Arrange
    policy = _manifest().get("mount_policy")
    # Act
    login_required = bool(isinstance(policy, dict) and policy.get("login_required"))
    # Assert
    assert login_required is True


# --- the target the entry point names -----------------------------------------


def test_the_entry_point_target_is_a_django_app_config():
    # Arrange
    module_path, _, attr = EXPECTED_TARGET.partition(":")
    # Act
    config_cls = getattr(importlib.import_module(module_path), attr)
    # Assert
    assert issubclass(config_cls, django.apps.AppConfig)


def test_base_install_provides_sdk_and_runtime_valid_plugin_metadata():
    from scitex_sdk import app

    project = tomllib.loads(_PYPROJECT.read_text())["project"]
    assert "scitex-sdk>=0.3.0" in project["dependencies"]
    module_path, _, attr = EXPECTED_TARGET.partition(":")
    config_cls = getattr(importlib.import_module(module_path), attr)
    assert issubclass(config_cls, app.embed.ScitexAppConfig)
    config = config_cls(config_cls.name, importlib.import_module(config_cls.name))
    assert "version" not in config.manifest
    assert config.validate_manifest() == []
    assert config.app_version == project["version"]


def test_the_urlconf_the_host_includes_exists():
    # Arrange
    module_path, _, attr = EXPECTED_TARGET.partition(":")
    config_cls = getattr(importlib.import_module(module_path), attr)
    # Act
    # The host mounts the plugin with include(f"{config.name}.urls").
    found = importlib.util.find_spec(f"{config_cls.name}.urls") is not None
    # Assert
    assert found
