"""Importing tests/conftest.py must not touch site-packages or caller env."""

from __future__ import annotations

import subprocess
import sys
import textwrap
from pathlib import Path

CONFTEST = Path(__file__).resolve().parents[1] / "conftest.py"


def test_conftest_leaves_site_packages_and_coverage_env_untouched():
    # Arrange
    child = textwrap.dedent(
        """\
        import os
        import runpy
        import site
        import sys

        os.environ["COVERAGE_PROCESS_START"] = "sentinel-process-start"
        os.environ["COVERAGE_FILE"] = "sentinel-coverage-file"

        def snapshot():
            dirs = []
            try:
                dirs.extend(site.getsitepackages() or [])
            except Exception:
                pass
            try:
                user = site.getusersitepackages()
                if isinstance(user, str):
                    dirs.append(user)
                elif user:
                    dirs.extend(user)
            except Exception:
                pass
            names = {}
            for directory in dirs:
                try:
                    names[directory] = sorted(os.listdir(directory))
                except OSError:
                    names[directory] = None
            return names

        before = snapshot()
        runpy.run_path(sys.argv[1])
        after = snapshot()
        assert before == after, "conftest.py created/changed files in site-packages"
        assert os.environ.get("COVERAGE_PROCESS_START") == "sentinel-process-start"
        assert os.environ.get("COVERAGE_FILE") == "sentinel-coverage-file"
        """
    )
    # Act
    proc = subprocess.run(
        [sys.executable, "-c", child, str(CONFTEST)],
        capture_output=True,
        text=True,
        timeout=120,
    )
    # Assert
    assert proc.returncode == 0, proc.stderr
