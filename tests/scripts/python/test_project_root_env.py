#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# Test file for: _project_root.py (SCITEX_WRITER_PROJECT_ROOT vs the retired
# PROJECT_ROOT, and the warning that must accompany the old name)

import sys
from pathlib import Path

# Add scripts/python to path for imports
ROOT_DIR = Path(__file__).resolve().parent.parent.parent.parent
sys.path.insert(0, str(ROOT_DIR / "scripts" / "python"))

from _project_root import (  # noqa: E402
    ENV_PROJECT_ROOT,
    RETIRED_PROJECT_ROOT,
    resolve_project_root,
)


def test_the_namespaced_name_wins_when_both_are_set():
    # Arrange
    environ = {ENV_PROJECT_ROOT: "/tmp/new", RETIRED_PROJECT_ROOT: "/tmp/old"}
    # Act
    resolved = resolve_project_root(environ=environ)
    # Assert
    assert resolved == "/tmp/new"


def test_the_retired_name_is_still_honoured():
    """Vendored scripts run inside workspaces that export the old name."""
    # Arrange
    environ = {RETIRED_PROJECT_ROOT: "/tmp/old"}
    # Act
    resolved = resolve_project_root(environ=environ)
    # Assert
    assert resolved == "/tmp/old"


def test_the_retired_name_is_never_silent(capsys):
    # Arrange
    environ = {RETIRED_PROJECT_ROOT: "/tmp/old"}
    # Act
    resolve_project_root(environ=environ)
    # Assert
    assert ENV_PROJECT_ROOT in capsys.readouterr().err


def test_the_namespaced_name_is_silent(capsys):
    # Arrange
    environ = {ENV_PROJECT_ROOT: "/tmp/new"}
    # Act
    resolve_project_root(environ=environ)
    # Assert
    assert capsys.readouterr().err == ""


def test_the_default_is_used_when_neither_is_set():
    # Arrange
    environ = {}
    # Act
    resolved = resolve_project_root("/tmp/here", environ)
    # Assert
    assert resolved == "/tmp/here"


def test_no_default_falls_back_to_the_working_directory():
    # Arrange
    import os

    environ = {}
    # Act
    resolved = resolve_project_root(environ=environ)
    # Assert
    assert resolved == os.getcwd()


# EOF
