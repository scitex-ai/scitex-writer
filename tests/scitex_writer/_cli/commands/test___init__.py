#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# Test file for: src/scitex_writer/_cli/commands/__init__.py

"""The shell-completion wiring must come from a PUBLIC peer name, unguarded.

Why this file exists — two defects lived in six lines here:

1. PRIVATE IMPORT. It reached into `scitex_dev._cli._completion`, a peer's
   underscore module. A peer can rename or move a private path without notice;
   the public name is the promise. `scitex_dev.cli.attach_shell_completion` is
   in that module's `__all__`, so it is the supported surface.

2. `except ImportError: pass`. scitex-dev is a HARD dependency of writer — it is
   always installed — so that guard was not protecting against a missing
   optional package. It was SWALLOWING a real breakage: if the peer ever dropped
   or renamed the symbol, shell completion would silently stop existing and
   nothing would say why. The same shape as the port that silently slid and the
   install hint that installed nothing.

The guard is gone and the floor carries the promise instead (scitex-dev>=0.30.0,
the first release exposing the public name). Below it, the CLI fails to import —
loudly, at install time, which is where a dependency problem belongs.
"""

import ast
import inspect
from pathlib import Path

import tomllib

from scitex_writer._cli import commands

_ROOT = Path(__file__).resolve().parents[4]
_SOURCE = inspect.getsource(commands)
_TREE = ast.parse(_SOURCE)


def _imported_modules() -> list[str]:
    return [
        node.module
        for node in ast.walk(_TREE)
        if isinstance(node, ast.ImportFrom) and node.module
    ]


def test_no_private_scitex_dev_module_is_imported():
    # Arrange
    imports = _imported_modules()
    # Act
    private = [m for m in imports if m.startswith("scitex_dev._")]
    # Assert
    assert private == []


def test_shell_completion_comes_from_the_public_scitex_dev_cli():
    # Arrange
    imports = _imported_modules()
    # Act
    public = [m for m in imports if m == "scitex_dev.cli"]
    # Assert
    assert public != []


def test_the_completion_import_is_not_swallowed_by_an_import_guard():
    # Arrange
    guarded = {
        id(node)
        for try_node in ast.walk(_TREE)
        if isinstance(try_node, ast.Try)
        for statement in try_node.body
        for node in ast.walk(statement)
    }
    # Act
    guarded_completion_imports = [
        node
        for node in ast.walk(_TREE)
        if isinstance(node, ast.ImportFrom)
        and node.module == "scitex_dev.cli"
        and id(node) in guarded
    ]
    # Assert
    assert guarded_completion_imports == []


def test_the_scitex_dev_floor_carries_the_public_name_promise():
    # Arrange
    data = tomllib.loads((_ROOT / "pyproject.toml").read_text())
    # Act
    floors = [
        tuple(int(part) for part in req.split(">=")[1].split("."))
        for req in data["project"]["dependencies"]
        if req.startswith("scitex-dev>=")
    ]
    # Assert (later features may raise the floor, never below the public name)
    assert len(floors) == 1 and floors[0] >= (0, 30, 0)
