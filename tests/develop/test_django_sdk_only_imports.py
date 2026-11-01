#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# Test file for: src/scitex_writer/_django/ (leaf migration, CCT 2786)

"""The leaf owns its Django through ``scitex_sdk`` only.

Slice 1 of the leaf migration: no module under ``_django`` may import
``scitex_app`` or ``scitex_ui`` at runtime. The shared shell, assets and
mount machinery all come from ``scitex_sdk`` (``scitex_sdk.ui``,
``scitex_sdk.app.embed``); the retired hosts survive only in comments
and docstrings, which this test deliberately ignores by reading the
syntax tree instead of grepping text.
"""
from __future__ import annotations

import ast
from pathlib import Path

# tests/develop/<name>.py -> parents[2] is the repo root.
_DJANGO = Path(__file__).resolve().parents[2] / "src" / "scitex_writer" / "_django"

# The retired shell hosts. ``scitex_sdk`` (including ``scitex_sdk.ui``)
# is the one legal shell provider and is never flagged.
_RETIRED_TOP_LEVELS = ("scitex_app", "scitex_ui")


def _retired_imports(tree: ast.AST) -> list[str]:
    found = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                top = alias.name.split(".")[0]
                if top in _RETIRED_TOP_LEVELS:
                    found.append(alias.name)
        elif isinstance(node, ast.ImportFrom):
            top = (node.module or "").split(".")[0]
            if top in _RETIRED_TOP_LEVELS:
                found.append(node.module or "")
    return found


def _django_sources() -> list[Path]:
    return sorted(
        path
        for path in _DJANGO.rglob("*.py")
        if "__pycache__" not in path.parts
    )


def test_the_django_leaf_has_python_sources():
    # Arrange
    sources = _django_sources()
    # Act
    count = len(sources)
    # Assert
    assert count > 0


def test_no_django_module_imports_the_retired_shell_hosts():
    # Arrange
    offenders = {}
    for path in _django_sources():
        retired = _retired_imports(
            ast.parse(path.read_text(encoding="utf-8"))
        )
        if retired:
            offenders[str(path.relative_to(_DJANGO))] = retired
    # Act
    count = len(offenders)
    # Assert
    assert count == 0
