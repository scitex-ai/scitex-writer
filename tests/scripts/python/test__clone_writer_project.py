#!/usr/bin/env python3
"""Tests for scitex_writer._project._create.clone_writer_project.

clone_writer_project shells out to `git clone <template> <dir>` and, for
the 'child' strategy, follows with `git init/add/commit`. Instead of
mocking subprocess.run, these tests install a REAL `git` shim on PATH:

- a success shim that materializes the target directory on `clone` and
  exits 0 for every subcommand;
- a failure shim that exits 1;
- and, for the generic-exception path, a PATH with no `git` at all so
  subprocess raises a real FileNotFoundError.

This exercises the production subprocess.run codepath end-to-end.
"""

import os
import stat
from pathlib import Path

import pytest

from scitex_writer._project._create import clone_writer_project

_SUCCESS_GIT = """#!/usr/bin/env bash
# Minimal git stand-in. On `clone`, create the destination dir (last arg)
# so the post-clone steps + the caller's existence check pass.
if [ "$1" = "clone" ]; then
    dest="${@: -1}"
    mkdir -p "$dest/.git"
fi
exit 0
"""

_FAILURE_GIT = """#!/usr/bin/env bash
echo "fatal: simulated clone failure" >&2
exit 1
"""


def _install_git_shim(bin_dir: Path, script: str) -> None:
    bin_dir.mkdir(parents=True, exist_ok=True)
    git = bin_dir / "git"
    git.write_text(script)
    git.chmod(git.stat().st_mode | stat.S_IEXEC | stat.S_IXGRP | stat.S_IXOTH)


@pytest.fixture
def path_with_success_git(tmp_path):
    """Prepend a tmp bin/ holding a success git shim onto PATH."""
    bin_dir = tmp_path / "bin"
    _install_git_shim(bin_dir, _SUCCESS_GIT)
    saved = os.environ["PATH"]
    os.environ["PATH"] = f"{bin_dir}{os.pathsep}{saved}"
    try:
        yield
    finally:
        os.environ["PATH"] = saved


@pytest.fixture
def path_with_failing_git(tmp_path):
    """Prepend a tmp bin/ holding a git shim that exits non-zero."""
    bin_dir = tmp_path / "bin"
    _install_git_shim(bin_dir, _FAILURE_GIT)
    saved = os.environ["PATH"]
    os.environ["PATH"] = f"{bin_dir}{os.pathsep}{saved}"
    try:
        yield
    finally:
        os.environ["PATH"] = saved


@pytest.fixture
def path_without_git(tmp_path):
    """Replace PATH with a dir that contains no `git` binary at all."""
    bin_dir = tmp_path / "empty_bin"
    bin_dir.mkdir()
    saved = os.environ["PATH"]
    os.environ["PATH"] = str(bin_dir)
    try:
        yield
    finally:
        os.environ["PATH"] = saved


class TestCloneWriterProjectSuccess:
    """Success cases against a real (shimmed) git binary."""

    def test_returns_true_on_success(self, tmp_path, path_with_success_git):
        # Arrange
        project_dir = tmp_path / "new_paper"
        # Act
        result = clone_writer_project(str(project_dir))
        # Assert
        assert result is True

    def test_parent_strategy_returns_true(self, tmp_path, path_with_success_git):
        # Arrange
        project_dir = tmp_path / "new_paper"
        # Act
        result = clone_writer_project(str(project_dir), git_strategy="parent")
        # Assert
        assert result is True

    def test_branch_argument_returns_true(self, tmp_path, path_with_success_git):
        # Arrange
        project_dir = tmp_path / "new_paper"
        # Act
        result = clone_writer_project(str(project_dir), branch="develop")
        # Assert
        assert result is True

    def test_tag_argument_returns_true(self, tmp_path, path_with_success_git):
        # Arrange
        project_dir = tmp_path / "new_paper"
        # Act
        result = clone_writer_project(str(project_dir), tag="v1.0.0")
        # Assert
        assert result is True

    def test_default_child_strategy_returns_true(self, tmp_path, path_with_success_git):
        # Arrange
        project_dir = tmp_path / "new_paper"
        # Act
        result = clone_writer_project(str(project_dir))
        # Assert
        assert result is True

    def test_none_strategy_returns_true(self, tmp_path, path_with_success_git):
        # Arrange
        project_dir = tmp_path / "new_paper"
        # Act
        result = clone_writer_project(str(project_dir), git_strategy=None)
        # Assert
        assert result is True

    def test_origin_strategy_returns_true(self, tmp_path, path_with_success_git):
        # Arrange
        project_dir = tmp_path / "new_paper"
        # Act
        result = clone_writer_project(str(project_dir), git_strategy="origin")
        # Assert
        assert result is True


class TestCloneWriterProjectTemplateHistory:
    """Which strategies keep the template's own .git (the shim's clone makes one)."""

    @pytest.mark.parametrize(
        ("strategy", "keeps_template_git"),
        [("parent", False), (None, False), ("none", False), ("origin", True)],
    )
    def test_only_origin_keeps_the_template_git(
        self, tmp_path, path_with_success_git, strategy, keeps_template_git
    ):
        # Arrange: inside a parent repository, as hub's <project>/.scitex/writer
        project_dir = tmp_path / "project" / ".scitex" / "writer"
        project_dir.parent.mkdir(parents=True)
        # Act
        clone_writer_project(str(project_dir), git_strategy=strategy)
        # Assert
        assert (project_dir / ".git").exists() is keeps_template_git


class TestCloneWriterProjectFailure:
    """Failure cases."""

    def test_returns_false_when_clone_exits_nonzero(
        self, tmp_path, path_with_failing_git
    ):
        # Arrange
        project_dir = tmp_path / "new_paper"
        # Act
        result = clone_writer_project(str(project_dir))
        # Assert
        assert result is False

    def test_returns_false_when_git_binary_is_absent(self, tmp_path, path_without_git):
        # Arrange
        project_dir = tmp_path / "new_paper"
        # Act
        result = clone_writer_project(str(project_dir))
        # Assert
        assert result is False

    def test_returns_false_when_target_directory_already_exists(self, tmp_path):
        # Arrange
        project_dir = tmp_path / "existing"
        project_dir.mkdir()
        # Act
        result = clone_writer_project(str(project_dir))
        # Assert
        assert result is False
