#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# File: tests/scitex_writer/test_workspace_layout.py

"""Guard the published project layout against drift.

The point of these tests is NOT to restate the constants — that would pass
forever no matter what the tree looks like. Each drift guard below compares the
published layout against a SECOND, independent statement of the same fact:

  - the ``.scitex/writer`` segment, against what ``ensure_workspace`` creates;
  - the ``scripts/shell/compile_<doc_type>.sh`` tail, against the scripts that
    actually exist in this repository, which is the project template;
  - the compile runner's resolution, against the published relpath.

If any of those pairs stops agreeing, a downstream caller is about to get a
path that does not exist — which is exactly how full compilation shipped dead
(rc=127) in 2026-08.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from scitex_writer import ensure_workspace
from scitex_writer.workspace_layout import (
    COMPILE_SCRIPT_RELPATHS,
    NotAWriterWorkspaceError,
    SHELL_SCRIPTS_RELPATH,
    WORKSPACE_RELPATH,
    compile_script,
    compile_script_relpath,
    is_workspace,
    resolve_workspace,
    workspace_dir,
)

REPO_ROOT = Path(__file__).resolve().parents[2]

DOC_TYPES = ("manuscript", "supplementary", "revision")


# ---------------------------------------------------------------------------
# workspace_dir
# ---------------------------------------------------------------------------


def test_workspace_dir_appends_the_hidden_segment(tmp_path: Path):
    # Arrange
    project_root = tmp_path
    # Act
    resolved = workspace_dir(project_root)
    # Assert
    assert resolved == project_root / ".scitex" / "writer"


def test_workspace_dir_accepts_a_string_path(tmp_path: Path):
    # Arrange
    expected = workspace_dir(tmp_path)
    # Act
    resolved = workspace_dir(str(tmp_path))
    # Assert
    assert resolved == expected


def test_workspace_dir_does_not_try_to_detect_which_root_it_was_given(
    tmp_path: Path,
):
    """Composing twice must produce an obviously wrong path, not a plausible one.

    The scitex-writer repository is itself a workspace that ALSO contains a
    ``.scitex/writer/`` directory, so no heuristic can tell a project root from
    a workspace by looking at the path. A helper that appeared to would be
    wrong exactly where it was trusted.
    """
    # Arrange
    once = workspace_dir(tmp_path)
    # Act
    twice = workspace_dir(once)
    # Assert
    assert twice == once / ".scitex" / "writer"


# ---------------------------------------------------------------------------
# DRIFT GUARD — the segment agrees with what ensure_workspace creates
# ---------------------------------------------------------------------------


def test_workspace_dir_agrees_with_ensure_workspace(tmp_path: Path):
    """``ensure_workspace`` writes the canonical workspace; we must name it.

    Pre-seeded so ``ensure_workspace`` returns the existing directory instead
    of cloning the template over the network — the assertion under test is the
    PATH, not the clone.
    """
    # Arrange
    seeded = tmp_path / ".scitex" / "writer"
    seeded.mkdir(parents=True)
    (seeded / "marker").write_text("", encoding="utf-8")
    # Act
    created = ensure_workspace(tmp_path)
    # Assert
    assert Path(created) == workspace_dir(tmp_path)


# ---------------------------------------------------------------------------
# compile_script_relpath
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("doc_type", DOC_TYPES)
def test_compile_script_relpath_is_not_absolute(doc_type: str):
    # Arrange
    relpath = compile_script_relpath(doc_type)
    # Act
    absolute = relpath.is_absolute()
    # Assert
    assert absolute is False


@pytest.mark.parametrize("doc_type", DOC_TYPES)
def test_compile_script_relpath_starts_at_the_shell_scripts_dir(doc_type: str):
    # Arrange
    depth = len(SHELL_SCRIPTS_RELPATH.parts)
    # Act
    head = compile_script_relpath(doc_type).parts[:depth]
    # Assert
    assert head == SHELL_SCRIPTS_RELPATH.parts


@pytest.mark.parametrize("doc_type", DOC_TYPES)
def test_compile_script_relpath_is_named_for_its_doc_type(doc_type: str):
    # Arrange
    expected = f"compile_{doc_type}.sh"
    # Act
    name = compile_script_relpath(doc_type).name
    # Assert
    assert name == expected


@pytest.mark.parametrize("doc_type", DOC_TYPES)
def test_compile_script_relpath_carries_no_workspace_segment(doc_type: str):
    """The relpath must NOT include ``.scitex/writer``.

    If it did, a caller composing ``workspace_dir(root) / relpath`` would get
    the segment twice — and a caller that already holds a workspace would get
    it once too often. Keeping the two halves disjoint is what makes them
    composable.
    """
    # Arrange
    hidden_segment = WORKSPACE_RELPATH.parts[0]
    # Act
    parts = compile_script_relpath(doc_type).parts
    # Assert
    assert hidden_segment not in parts


def _rejection_message(doc_type: str) -> str:
    """The ValueError text for an unknown doc_type, as a plain string.

    Kept out of the test bodies so each message assertion stays a single
    assertion — ``pytest.raises`` counts as one on its own.
    """
    try:
        compile_script_relpath(doc_type)
    except ValueError as exc:
        return str(exc)
    raise AssertionError(f"compile_script_relpath({doc_type!r}) did not raise")


def test_compile_script_relpath_rejects_an_unknown_doc_type():
    # Arrange
    unknown = "bogus"

    def _call():
        return compile_script_relpath(unknown)

    # Act
    raised = pytest.raises(ValueError)
    # Assert
    with raised:
        _call()


def test_compile_script_relpath_error_names_the_valid_doc_types():
    """A caller supplying a bad doc_type cannot see the dict; tell them."""
    # Arrange
    unknown = "bogus"
    # Act
    message = _rejection_message(unknown)
    # Assert
    assert all(doc_type in message for doc_type in DOC_TYPES)


def test_compile_script_relpath_error_names_the_offending_value():
    # Arrange
    unknown = "bogus"
    # Act
    message = _rejection_message(unknown)
    # Assert
    assert unknown in message


# ---------------------------------------------------------------------------
# compile_script — the one call a caller outside this package should need
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("doc_type", DOC_TYPES)
def test_compile_script_composes_the_two_published_halves(
    tmp_path: Path, doc_type: str
):
    """It must compose, not re-derive — otherwise it is a third statement."""
    # Arrange
    expected = workspace_dir(tmp_path) / compile_script_relpath(doc_type)
    # Act
    resolved = compile_script(tmp_path, doc_type)
    # Assert
    assert resolved == expected


def test_compile_script_takes_a_project_root_not_a_workspace(tmp_path: Path):
    """The whole point: a caller hands over the directory the user named.

    scitex-hub's compile view holds a project root. If it had to know that a
    workspace segment exists in order to call this, the segment would still be
    duplicated in hub — which is the defect, not the fix.
    """
    # Arrange
    project_root = tmp_path
    # Act
    resolved = compile_script(project_root, "manuscript")
    # Assert
    assert resolved == (
        project_root
        / ".scitex"
        / "writer"
        / "scripts"
        / "shell"
        / "compile_manuscript.sh"
    )


def test_compile_script_rejects_an_unknown_doc_type():
    # Arrange
    def _call():
        return compile_script("/tmp/paper", "bogus")

    # Act
    raised = pytest.raises(ValueError)
    # Assert
    with raised:
        _call()


# ---------------------------------------------------------------------------
# DRIFT GUARD — the tail agrees with the scripts that actually exist
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("doc_type", DOC_TYPES)
def test_published_relpath_locates_a_real_script_in_this_repo(doc_type: str):
    """This repository IS the project template, so the tail must resolve here.

    A rename or move of ``scripts/shell/compile_*.sh`` that forgets this module
    fails here rather than in a downstream package's production logs.
    """
    # Arrange
    script = REPO_ROOT / compile_script_relpath(doc_type)
    # Act
    exists = script.is_file()
    # Assert
    assert exists, f"{script} does not exist — layout drifted"


def test_every_doc_type_the_compiler_knows_is_published():
    """The rest of writer must not know a doc_type the layout does not."""
    # Arrange
    from scitex_writer._dataclasses.config import DOC_TYPE_DIRS

    # Act
    published = set(COMPILE_SCRIPT_RELPATHS)
    # Assert
    assert published == set(DOC_TYPE_DIRS)


# ---------------------------------------------------------------------------
# DRIFT GUARD — the compile runner resolves through the published layout
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("doc_type", DOC_TYPES)
def test_runner_resolves_scripts_through_the_published_relpath(
    tmp_path: Path, doc_type: str
):
    # Arrange
    from scitex_writer._compile._runner import _get_compile_script

    # Act
    resolved = _get_compile_script(tmp_path, doc_type)
    # Assert
    assert resolved == tmp_path / compile_script_relpath(doc_type)


def test_runner_returns_none_for_an_unknown_doc_type(tmp_path: Path):
    """``run_compile`` branches on falsiness here; keep that shape."""
    # Arrange
    from scitex_writer._compile._runner import _get_compile_script

    # Act
    resolved = _get_compile_script(tmp_path, "bogus")
    # Assert
    assert resolved is None


# ---------------------------------------------------------------------------
# resolve_workspace — the leaf-owned root->workspace contract (hub 2026-09-14)
#
# The compile handlers call resolve_workspace(resolve_project_path(dir)).
# resolve_project_path only absolutises, so the ROOT-vs-WORKSPACE decision is
# entirely in this pure function. These are the three hub-required regressions,
# expressed without mocks (the function is pure: it reads the tree, returns a
# path, or raises a named error).
# ---------------------------------------------------------------------------


def _seed_project(root: Path) -> Path:
    """Create <root>/.scitex/writer with 00_shared/ (an initialised project)."""
    ws = root / ".scitex" / "writer"
    ws.mkdir(parents=True)
    (ws / "00_shared").mkdir()
    return ws


def test_resolve_workspace_given_a_project_root_maps_to_workspace(tmp_path: Path):
    # Arrange
    ws = _seed_project(tmp_path)
    # Act
    resolved = resolve_workspace(tmp_path)
    # Assert: the hub passes the ROOT; the leaf maps it to the workspace
    assert resolved == ws


def test_resolve_workspace_given_an_existing_workspace_returns_it(tmp_path: Path):
    # Arrange
    ws = _seed_project(tmp_path)
    # Act
    resolved = resolve_workspace(ws)
    # Assert: a path that already IS a workspace is used as is (no double-nest)
    assert resolved == ws


def _named_error_for(path: Path) -> NotAWriterWorkspaceError:
    """Return the NotAWriterWorkspaceError ``resolve_workspace`` raises for
    ``path``.

    Kept out of the test bodies so each test is a single assertion (STX-TQ007):
    the ``pytest.raises`` equivalent lives here, not in the test.
    """
    try:
        resolve_workspace(path)
    except NotAWriterWorkspaceError as exc:
        return exc
    raise AssertionError(f"resolve_workspace({path!r}) did not raise")


def test_resolve_workspace_given_a_non_writer_dir_raises_the_named_error(
    tmp_path: Path,
):
    # Arrange
    stray = tmp_path / "just-a-folder"
    stray.mkdir()
    # Act
    error = _named_error_for(stray)
    # Assert: the error NAMES the path given
    assert str(stray) in str(error)


def test_resolve_workspace_named_error_points_at_the_expected_workspace(
    tmp_path: Path,
):
    # Arrange
    stray = tmp_path / "just-a-folder"
    stray.mkdir()
    # Act
    error = _named_error_for(stray)
    # Assert: the error also names where the workspace would be (root/.scitex/writer)
    assert ".scitex/writer" in str(error)


def test_resolve_workspace_named_error_is_not_a_bare_file_not_found(tmp_path: Path):
    """The whole defect was a bare FileNotFoundError on root/00_shared/... ."""
    # Arrange
    stray = tmp_path / "just-a-folder"
    stray.mkdir()
    # Act
    error = _named_error_for(stray)
    # Assert: it is the named contract error, not FileNotFoundError
    assert not isinstance(error, FileNotFoundError)


def test_is_workspace_distinguishes_workspace_from_root(tmp_path: Path):
    # Arrange
    ws = _seed_project(tmp_path)
    # Act
    root_is_ws = is_workspace(tmp_path)
    ws_is_ws = is_workspace(ws)
    # Assert: the root is not a workspace; the workspace is
    assert ws_is_ws is True and root_is_ws is False


# EOF
