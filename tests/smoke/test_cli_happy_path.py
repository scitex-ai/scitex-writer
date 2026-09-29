"""Smoke layer: fast (<60s) subprocess-driven CLI happy-path tests.

Each test shells out to the installed ``scitex-writer`` entry surface and
checks the user-visible contract (exit code + stdout). No network, no LaTeX,
no project scaffold — ``--version`` / ``--help`` only.
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest

from scitex_writer import __version__

pytestmark = pytest.mark.smoke


def test_version_reports_the_package_version(
    tmp_path: Path, isolated_home: Path
) -> None:
    # Arrange
    cmd = [sys.executable, "-m", "scitex_writer", "--version"]
    # Act
    proc = subprocess.run(cmd, capture_output=True, text=True, timeout=60, cwd=tmp_path)
    # Assert
    assert proc.returncode == 0 and __version__ in proc.stdout


def test_top_level_help_names_the_tables_verb(
    tmp_path: Path, isolated_home: Path
) -> None:
    # Arrange
    cmd = [sys.executable, "-m", "scitex_writer", "--help"]
    # Act
    proc = subprocess.run(cmd, capture_output=True, text=True, timeout=60, cwd=tmp_path)
    # Assert
    assert proc.returncode == 0 and "tables" in proc.stdout
