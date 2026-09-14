#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Load-point root->workspace resolution for the _django layer (#389 follow-up).

The scitex-hub leaf-v2 mount passes the PROJECT ROOT as ``?working_dir=<root>``
(``WorkingDirScopedView``). The leaf owns root->workspace: the single place the
_django layer loads a project is ``get_or_create_project`` (services.py), and
``state.project_dir`` must therefore be the WORKSPACE, not the raw root, so
every downstream handler composes workspace-relative paths (``compile.sh``,
``00_shared/``, ``logs/``, PDFs) against the right directory. Before the fix,
a ROOT reached ``run_compile_script`` and refused with
``compile.sh not found at <root>/compile.sh`` (the 2026-09-14 live failure).

These are pure tests of the load point: no compile thread, no LaTeX engine.
The end-to-end ``api/compile`` drive lives in ``test_views.py``.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from scitex_writer._django import services
from scitex_writer._django.services import (
    ProjectState,
    get_or_create_project,
    remove_project,
)
from scitex_writer.workspace_layout import (
    NotAWriterWorkspaceError,
    resolve_workspace,
)

# The module-level cache must be reset between tests so one test's ProjectState
# cannot leak into another (each builds a unique tmp root, but the TTL is long).


@pytest.fixture(autouse=True)
def _clean_cache():
    services._project_cache.clear()
    yield
    services._project_cache.clear()


@pytest.fixture
def nested_root(tmp_path: Path) -> Path:
    """A PROJECT ROOT with its writer WORKSPACE nested at .scitex/writer/.

    This is the exact shape the hub hands us: root R with
    R/.scitex/writer/00_shared/ already initialised (by the hub's project-state
    init), and nothing 00_shared/-shaped at the root itself.
    """
    root = tmp_path / "proj"
    workspace = root / ".scitex" / "writer"
    (workspace / "00_shared").mkdir(parents=True)
    (workspace / "compile.sh").write_text("#!/bin/bash\nexit 0\n")
    return root


@pytest.fixture
def flat_workspace(tmp_path: Path) -> Path:
    """A standalone/legacy WORKSPACE: 00_shared/ sits at the top level.

    The legacy hub path and the standalone CLI pass this directly; it must keep
    resolving to itself (the fix must not break the flat layout).
    """
    ws = tmp_path / "workspace"
    (ws / "00_shared").mkdir(parents=True)
    (ws / "compile.sh").write_text("#!/bin/bash\nexit 0\n")
    return ws


@pytest.fixture
def bare_empty_root(tmp_path: Path) -> Path:
    """A directory that is neither a root with a workspace nor a workspace."""
    bare = tmp_path / "just-a-folder"
    bare.mkdir()
    return bare


def _raises_named_error(root: Path):
    with pytest.raises(NotAWriterWorkspaceError) as excinfo:
        get_or_create_project(str(root))
    return excinfo.value


# ---------- the fix: a ROOT loads as its WORKSPACE ----------


def test_load_given_a_root_returns_a_workspace_project_state(nested_root: Path):
    # Arrange
    root = nested_root
    expected_workspace = resolve_workspace(root)
    # Act
    state = get_or_create_project(str(root))
    # Assert
    assert state.project_dir == expected_workspace


def test_load_given_a_root_caches_under_the_workspace_key(nested_root: Path):
    # Arrange
    root = nested_root
    # Act
    get_or_create_project(str(root))
    # Assert: the cache key is the resolved workspace
    assert str(resolve_workspace(root)) in services._project_cache


def test_load_given_a_root_does_not_cache_under_the_raw_root(nested_root: Path):
    # Arrange
    root = nested_root
    # Act
    get_or_create_project(str(root))
    # Assert: the raw root itself is NOT a cache key
    assert str(root) not in services._project_cache


def test_load_given_a_root_is_cached_under_the_workspace_not_the_root(
    nested_root: Path,
):
    # Arrange
    root = nested_root
    first = get_or_create_project(str(root))
    # Act: a second load of the SAME root returns the identical cached state
    second = get_or_create_project(str(root))
    # Assert
    assert first is second


# ---------- tolerance: a flat WORKSPACE resolves to itself (no regression) ----------


def test_load_given_a_flat_workspace_returns_itself(flat_workspace: Path):
    # Arrange
    workspace = flat_workspace
    # Act
    state = get_or_create_project(str(workspace))
    # Assert
    assert state.project_dir == workspace


# ---------- loud, named failure for a directory that is neither ----------


def test_load_given_a_bare_empty_root_raises_the_named_error(bare_empty_root: Path):
    # Arrange
    root = bare_empty_root
    # Act
    err = _raises_named_error(root)
    # Assert: the message names BOTH the path given and the workspace expected
    assert str(root) in err.args[0] and ".scitex/writer" in err.args[0]


def test_load_given_a_bare_empty_root_raises_not_a_bare_file_not_found(
    bare_empty_root: Path,
):
    # Arrange
    root = bare_empty_root
    # Act
    err = _raises_named_error(root)
    # Assert: it is the named ValueError, not a FileNotFoundError
    assert isinstance(err, ValueError) and not isinstance(err, FileNotFoundError)


# ---------- remove_project stays consistent with the workspace cache key ----------


def test_remove_by_root_evicts_the_workspace_cached_state(nested_root: Path):
    # Arrange
    root = nested_root
    state = get_or_create_project(str(root))
    # Act: the hub removes by the ROOT it passed in
    remove_project(str(root))
    # Assert: the workspace-keyed state is gone, and reloading builds a fresh one
    assert get_or_create_project(str(root)) is not state


def test_load_returns_a_project_state_subclass_instance(nested_root: Path):
    # Arrange
    root = nested_root
    # Act
    state = get_or_create_project(str(root))
    # Assert
    assert isinstance(state, ProjectState)


# EOF
