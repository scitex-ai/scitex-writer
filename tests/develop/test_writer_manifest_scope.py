"""Guard the Writer app's declared ``scope`` against the closed-enum contract.

scitex-app (PR #185 @ d8528de4) makes the app ``scope`` an OPTIONAL closed enum
``{"user", "project"}``: absent -> normalizes to "user" (the safe no-selector
default); present but NOT in the enum -> FAILS LOUD at manifest validation
(appmaker/_validate/_manifest.py). Writer is PROJECT-scoped (hub mounts it via
WorkingDirScopedView; working_dir = the authenticated user's current project),
so it declares ``"scope": "project"`` in src/scitex_writer/_django/manifest.json.

Why this test lives HERE and not only in the scitex_app validator:
  * The fleet's scitex-app mount can lag behind d8528de4. At the older mount
    (e.g. 94d4a40, scitex_app 0.22.1) there is no ``_app_scope.py`` and the
    validator only checks required-key PRESENCE, not the closed-enum whitelist —
    so a typo'd scope ("projet", "Project", "PROJECT") would be SILENTLY IGNORED
    there and the app would quietly fall back to user-scope with no marker.
  * This test pins the enum in the Writer repo itself, so a typo or accidental
    removal of the declaration fails Writer's own CI regardless of which
    scitex_app revision the runner happens to mount.

It reads the real manifest, so it also guards against the key being dropped.
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

# The closed enum exactly as defined by the scitex-app d8528de4 contract.
ALLOWED_SCOPES = {"user", "project"}

# Writer is project-scoped (per the scitex-hub leader's contract ruling,
# m_d762af5357c5): the hub mounts Writer via WorkingDirScopedView and the leaf
# get_or_create_project keys on the authenticated user's current project.
EXPECTED_SCOPE = "project"

MANIFEST = (
    Path(__file__).resolve().parents[2]
    / "src"
    / "scitex_writer"
    / "_django"
    / "manifest.json"
)


def _load_manifest() -> dict:
    return json.loads(MANIFEST.read_text(encoding="utf-8"))


def test_manifest_path_exists():
    # Assert: the manifest the test guards is actually present (not a stale path).
    assert MANIFEST.is_file()


def test_writer_declares_project_scope():
    # Act: read the real declaration.
    manifest = _load_manifest()
    # Assert: Writer declares project scope (the leaf-side adoption, 1 line).
    assert manifest.get("scope") == EXPECTED_SCOPE


def test_declared_scope_is_a_member_of_the_closed_enum():
    # Act: read the real declaration.
    manifest = _load_manifest()
    scope = manifest.get("scope")
    # Assert: if present, it must be a member of the closed enum {"user","project"}.
    # This is the guard that catches a typo the older (pre-d8528de4) scitex_app
    # validator would silently ignore.
    assert scope in ALLOWED_SCOPES
