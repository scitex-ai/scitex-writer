#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# File: tests/develop/test_writer_mount_policy_jail.py

"""Writer's Slice 2 jail declaration (leaf migration, CCT 2786).

The host's generic plugin mount enforces ``scitex_sdk.app.jail`` with NO
per-app code: the leaf DECLARES its path-bearing channels in
``_django/manifest.json`` under ``mount_policy``, and the SDK VALIDATES
the declaration at mount time (``validate_mount_policy`` raises
``LeafContractError`` on anything malformed). A file-touching plugin
without a ``jail`` block fails loudly instead of mounting open.

Writer's declared channels, measured against the handlers (2026-10-15):

* ``working_dir`` (GET) — the working-directory key itself
  (``views.py``, ``sections.py``); the wrapper overwrites it
  server-side, never honours the caller's value.
* ``path`` (GET query + POST JSON body) — file read/save
  (``handlers/files.py::handle_file``) and thumbnails
  (``handlers/media.py::handle_thumbnail``).
* ``target`` (GET) — DAG target file (``handlers/viewer.py::handle_dag``).
* ``output_file`` (POST JSON body) — claim output file
  (``handlers/claim.py::handle_add_claim``).
* ``pdf`` (GET) — preview PDF basename (``sections.py::manuscript_status``,
  basename-locked leaf-side; declared so the mount-time bar sees it).

Scope is ``project``: every one of these resolves against the host's
server-side project directory (``project.project_dir`` in plugin mode),
not the caller's looser data root. The leaf keeps its own containment
checks (``files.py::_resolve_safe``, ``sections.py::_within``) for
standalone mode, where no host enforcement exists.
"""
from __future__ import annotations

import json
import tomllib
from pathlib import Path

import pytest

from scitex_sdk.app import jail
from scitex_sdk.app.plugins import LeafContractError

_ROOT = Path(__file__).resolve().parents[2]
_PYPROJECT = _ROOT / "pyproject.toml"
_MANIFEST = _ROOT / "src" / "scitex_writer" / "_django" / "manifest.json"

EXPECTED_PATH_PARAMS = ("path", "target", "output_file", "pdf")


def _manifest() -> dict:
    return json.loads(_MANIFEST.read_text(encoding="utf-8"))


def _policy() -> dict:
    return _manifest()["mount_policy"]


# --- the declaration --------------------------------------------------------


def test_the_manifest_declares_it_touches_files():
    # Arrange
    policy = _policy()
    # Act
    touches = policy.get("touches_files")
    # Assert
    assert touches is True


def test_the_manifest_declares_a_jail_block():
    # Arrange
    policy = _policy()
    # Act
    block = policy.get("jail")
    # Assert
    assert isinstance(block, dict)


def test_the_jail_scope_is_project():
    # Arrange
    raw = _policy()["jail"]
    # Act
    normalized = jail.normalize_jail_policy(raw, plugin="writer")
    # Assert
    assert normalized["scope"] == "project"


def test_the_jail_working_dir_param_is_working_dir():
    # Arrange
    raw = _policy()["jail"]
    # Act
    normalized = jail.normalize_jail_policy(raw, plugin="writer")
    # Assert
    assert normalized["working_dir_param"] == "working_dir"


def test_the_jail_path_params_cover_the_handler_channels():
    # Arrange
    raw = _policy()["jail"]
    # Act
    normalized = jail.normalize_jail_policy(raw, plugin="writer")
    # Assert
    assert normalized["path_params"] == EXPECTED_PATH_PARAMS


# --- the mount-time bar ------------------------------------------------------


def test_validate_mount_policy_accepts_the_shipped_manifest():
    # Arrange
    manifest = _manifest()
    # Act
    normalized = jail.validate_mount_policy(manifest, plugin="writer")
    # Assert
    assert normalized == {
        "scope": "project",
        "working_dir_param": "working_dir",
        "path_params": EXPECTED_PATH_PARAMS,
    }


def test_validate_mount_policy_rejects_touches_files_without_jail():
    # Arrange
    manifest = {"mount_policy": {"login_required": True, "touches_files": True}}
    # Act
    # Assert
    with pytest.raises(LeafContractError):
        jail.validate_mount_policy(manifest, plugin="writer")


def test_validate_mount_policy_rejects_a_jailed_mount_without_login():
    # Arrange
    manifest = {
        "mount_policy": {
            "touches_files": True,
            "jail": {
                "scope": "project",
                "working_dir_param": "working_dir",
                "path_params": ["path"],
            },
        }
    }
    # Act
    # Assert
    with pytest.raises(LeafContractError):
        jail.validate_mount_policy(manifest, plugin="writer")


# --- the floor the declaration needs -----------------------------------------


def test_the_sdk_floor_covers_the_jail_contract():
    # Arrange
    project = tomllib.loads(_PYPROJECT.read_text(encoding="utf-8"))["project"]
    # Act
    dependencies = project["dependencies"]
    # Assert
    assert "scitex-sdk>=0.3.12" in dependencies
