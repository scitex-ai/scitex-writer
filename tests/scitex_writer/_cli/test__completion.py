#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# File: tests/scitex_writer/_cli/test__completion.py

"""Tests for scitex_writer._cli._completion (drop-in contract v1).

Install must write ``$SCITEX_DIR/writer/runtime/completion/scitex-writer``
atomically + idempotently, print the path, and never touch shell
startup files. No mocks / monkeypatch — env vars are flipped via
yield-based fixtures and filesystem state via ``tmp_path``.
"""

from __future__ import annotations

import inspect
import os

import pytest
from click.testing import CliRunner

from scitex_writer._cli import main_group
from scitex_writer._cli import _completion as completion_mod

PROG = "scitex-writer"
SHORT = "writer"


@pytest.fixture
def runner():
    """Create a CLI runner."""
    return CliRunner()


@pytest.fixture
def isolated_scitex(tmp_path):
    """Point $SCITEX_DIR and $HOME at tmp dirs; restore prior values after."""
    prev_scitex = os.environ.get("SCITEX_DIR")
    prev_home = os.environ.get("HOME")
    scitex = tmp_path / "scitex-home"
    home = tmp_path / "home"
    home.mkdir()
    os.environ["SCITEX_DIR"] = str(scitex)
    os.environ["HOME"] = str(home)
    try:
        yield scitex, home
    finally:
        if prev_scitex is None:
            os.environ.pop("SCITEX_DIR", None)
        else:
            os.environ["SCITEX_DIR"] = prev_scitex
        if prev_home is None:
            os.environ.pop("HOME", None)
        else:
            os.environ["HOME"] = prev_home


def test_import__cli__completion_module():
    # Arrange
    module_path = "scitex_writer._cli._completion"
    # Act
    mod = pytest.importorskip(module_path)
    # Assert
    assert mod.__name__ == module_path


def test_install_shell_completion_exit_code(runner, isolated_scitex):
    # Arrange
    # Act
    result = runner.invoke(main_group, ["install-shell-completion", "--shell", "bash"])
    # Assert
    assert result.exit_code == 0


def test_install_shell_completion_writes_drop_in_file(runner, isolated_scitex):
    # Arrange
    scitex, _ = isolated_scitex
    drop_in = scitex / SHORT / "runtime" / "completion" / PROG
    # Act
    runner.invoke(main_group, ["install-shell-completion", "--shell", "bash"])
    # Assert
    assert drop_in.is_file()


def test_install_shell_completion_output_prints_drop_in_path(
    runner, isolated_scitex
):
    # Arrange
    scitex, _ = isolated_scitex
    drop_in = scitex / SHORT / "runtime" / "completion" / PROG
    # Act
    result = runner.invoke(main_group, ["install-shell-completion", "--shell", "bash"])
    # Assert
    assert str(drop_in) in result.output


def test_install_shell_completion_content_matches_print_output(
    runner, isolated_scitex
):
    # Arrange
    scitex, _ = isolated_scitex
    drop_in = scitex / SHORT / "runtime" / "completion" / PROG
    # Act
    printed = runner.invoke(main_group, ["print-shell-completion", "--shell", "bash"])
    runner.invoke(main_group, ["install-shell-completion", "--shell", "bash"])
    # Assert
    assert drop_in.read_text() == printed.output


def test_install_shell_completion_second_run_reports_already_installed(
    runner, isolated_scitex
):
    # Arrange
    runner.invoke(main_group, ["install-shell-completion", "--shell", "bash"])
    # Act
    second = runner.invoke(main_group, ["install-shell-completion", "--shell", "bash"])
    # Assert
    assert "already installed" in second.output


def test_install_shell_completion_second_run_keeps_mtime(runner, isolated_scitex):
    # Arrange
    scitex, _ = isolated_scitex
    drop_in = scitex / SHORT / "runtime" / "completion" / PROG
    runner.invoke(main_group, ["install-shell-completion", "--shell", "bash"])
    mtime = drop_in.stat().st_mtime_ns
    # Act
    runner.invoke(main_group, ["install-shell-completion", "--shell", "bash"])
    # Assert
    assert drop_in.stat().st_mtime_ns == mtime


def test_install_shell_completion_dry_run_writes_nothing(runner, isolated_scitex):
    # Arrange
    scitex, _ = isolated_scitex
    drop_in = scitex / SHORT / "runtime" / "completion" / PROG
    # Act
    runner.invoke(main_group, ["install-shell-completion", "--shell", "bash", "--dry-run"])
    # Assert
    assert not drop_in.exists()


def test_install_shell_completion_dry_run_mentions_path(runner, isolated_scitex):
    # Arrange
    scitex, _ = isolated_scitex
    # Act
    result = runner.invoke(
        main_group, ["install-shell-completion", "--shell", "bash", "--dry-run"]
    )
    # Assert
    assert str(scitex) in result.output


def test_install_shell_completion_leaves_bashrc_untouched(runner, isolated_scitex):
    # Arrange
    _, home = isolated_scitex
    (home / ".bashrc").write_text("# user rc\n")
    # Act
    runner.invoke(main_group, ["install-shell-completion", "--shell", "bash"])
    # Assert
    assert (home / ".bashrc").read_text() == "# user rc\n"


def test_install_shell_completion_leaves_zshrc_untouched(runner, isolated_scitex):
    # Arrange
    _, home = isolated_scitex
    (home / ".zshrc").write_text("# user rc\n")
    # Act
    runner.invoke(main_group, ["install-shell-completion", "--shell", "bash"])
    # Assert
    assert (home / ".zshrc").read_text() == "# user rc\n"


def test_install_shell_completion_help_has_no_rc_wording(runner):
    # Arrange
    banned = (".bashrc", ".zshrc", "bashrc", "zshrc", "fish/completions")
    # Act
    result = runner.invoke(main_group, ["install-shell-completion", "--help"])
    # Assert
    assert not any(token in result.output for token in banned)


def test_no_rc_helpers_left():
    # Arrange
    removed = ("_rc_path", "_marker", "_source_line")
    # Act
    present = [name for name in removed if hasattr(completion_mod, name)]
    # Assert
    assert present == []


def test_no_builtin_print_in_module():
    # Arrange
    # Act
    source = inspect.getsource(completion_mod)
    # Assert
    assert "\nprint(" not in source and "pprint" not in source


def test_write_atomic_writes_full_content(tmp_path):
    # Arrange
    target = tmp_path / "completion" / PROG
    target.parent.mkdir(parents=True)
    # Act
    completion_mod._write_atomic(target, "script-body\n")
    # Assert
    assert target.read_text() == "script-body\n"


def test_write_atomic_leaves_no_tmp_files(tmp_path):
    # Arrange
    target = tmp_path / "completion" / PROG
    target.parent.mkdir(parents=True)
    # Act
    completion_mod._write_atomic(target, "script-body\n")
    # Assert
    assert list(tmp_path.rglob("*.tmp")) == []


def test_print_shell_completion_all_shells_exit_zero(runner):
    # Arrange
    shells = ("bash", "zsh", "fish")
    # Act
    codes = [
        runner.invoke(main_group, ["print-shell-completion", "--shell", shell]).exit_code
        for shell in shells
    ]
    # Assert
    assert codes == [0, 0, 0]


def test_print_shell_completion_bash_mentions_prog(runner):
    # Arrange
    # Act
    result = runner.invoke(main_group, ["print-shell-completion", "--shell", "bash"])
    # Assert
    assert "scitex-writer" in result.output.lower()


def test_deprecated_aliases_exit_nonzero(runner):
    # Arrange
    aliases = ("install-tab-completion", "completion")
    # Act
    codes = [runner.invoke(main_group, [alias]).exit_code for alias in aliases]
    # Assert
    assert codes == [2, 2]


def test_deprecated_aliases_point_to_canonical(runner):
    # Arrange
    aliases = ("install-tab-completion", "completion")
    # Act
    outputs = [runner.invoke(main_group, [alias]).output for alias in aliases]
    # Assert
    assert all("install-shell-completion" in output for output in outputs)


# EOF
