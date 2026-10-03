#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# Test file for: src/scitex_writer/_django/apps.py

"""ALL OR NOTHING: one feature extra, and the remedy we print must deliver it.

Why this file exists: writer used to offer three fine-grained extras
(`desktop`, `editor`, `scholar`), which asked users to predict at install time
which features they would later want. It got that wrong in the worst possible
way — `editor` was declared EMPTY (`editor = []`) while `_server.py`, `apps.py`
and the CLI all told anyone missing scitex-app to run
`pip install scitex-writer[editor]`. That remedy installed NOTHING. The user ran
the fix we handed them, stayed exactly as broken, and the editor kept serving
without the workspace shell.

An install instruction that resolves to a no-op is worse than no instruction:
the user believes they have already tried it.

The fleet rule (operator, 2026-07-13) is now ALL OR NOTHING: plain install for
the compile engine, `[all]` for every feature. `dev` / `docs` remain, because
those are for people building writer, not using it.

These tests read the real pyproject and pin the contract, so a future edit that
re-introduces a half-empty extra — or an error message naming an extra that
does not provide the module whose absence triggered it — fails HERE.
"""

from pathlib import Path

import tomllib

_ROOT = Path(__file__).resolve().parents[3]
_PYPROJECT = _ROOT / "pyproject.toml"

# The modules whose absence degrades a feature, and the ONE extra our error
# messages are allowed to name as the cure.
_FEATURE_MODULES = ["scitex-sdk", "scitex-scholar", "pywebview"]
_THE_ONLY_FEATURE_EXTRA = "all"
_RETIRED_EXTRAS = ["editor", "desktop", "scholar"]


def _optional_dependencies() -> dict[str, list[str]]:
    data = tomllib.loads(_PYPROJECT.read_text())
    return data["project"]["optional-dependencies"]


def test_the_retired_fine_grained_extras_are_gone():
    # Arrange
    extras = _optional_dependencies()
    # Act
    survivors = [name for name in _RETIRED_EXTRAS if name in extras]
    # Assert
    assert survivors == []


def test_no_declared_extra_is_empty():
    # Arrange
    extras = _optional_dependencies()
    # Act
    empty = [name for name, reqs in extras.items() if not reqs]
    # Assert
    assert empty == []


def test_the_all_extra_provides_every_feature_module():
    # Arrange
    all_extra = " ".join(
        tomllib.loads(_PYPROJECT.read_text())["project"]["dependencies"]
        + _optional_dependencies()[_THE_ONLY_FEATURE_EXTRA]
    )
    # Act
    missing = [mod for mod in _FEATURE_MODULES if mod not in all_extra]
    # Assert
    assert missing == []


def test_workspace_shell_has_one_required_sdk_distribution_requires_sdk_dependency():
    # Arrange: pytest fixtures and local setup.
    # Act: exercise the real scenario.
    data = tomllib.loads(_PYPROJECT.read_text())['project']
    requirements = data['dependencies'] + [requirement for extra in data['optional-dependencies'].values() for requirement in extra]
    # Assert
    assert 'scitex-sdk>=0.3.0' in data['dependencies']


def test_workspace_shell_has_one_required_sdk_distribution_excludes_retired_distributions():
    # Arrange: pytest fixtures and local setup.
    # Act: exercise the real scenario.
    data = tomllib.loads(_PYPROJECT.read_text())['project']
    requirements = data['dependencies'] + [requirement for extra in data['optional-dependencies'].values() for requirement in extra]
    # Assert
    assert not any((requirement.startswith(('scitex-app', 'scitex-ui')) for requirement in requirements))


def test_nothing_still_tells_a_user_to_install_a_retired_extra():
    # Arrange
    searched = [_ROOT / "src", _ROOT / "docs", _ROOT / "scripts", _ROOT / "README.md"]
    files = [
        path
        for root in searched
        for path in ([root] if root.is_file() else root.rglob("*"))
        if path.is_file()
        and path.suffix in {".py", ".md", ".rst", ".ts", ".toml", ".gui"}
        and "_sphinx_html" not in path.parts
    ]
    # Act
    offenders = [
        str(path.relative_to(_ROOT))
        for path in files
        for extra in _RETIRED_EXTRAS
        if f"scitex-writer[{extra}]" in path.read_text(errors="ignore")
    ]
    # Assert
    assert offenders == []


def test_app_config_keeps_its_django_label():
    # Arrange
    from scitex_writer._django.apps import WriterEditorConfig

    # Act
    label = WriterEditorConfig.label
    # Assert
    assert label == "writer_editor"
