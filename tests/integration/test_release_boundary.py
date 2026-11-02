"""Run the real archive/identity/lifecycle controls in ordinary PR test space."""

import subprocess
import sys
from pathlib import Path


def test_release_identity_archive_and_owned_process_controls():
    # Arrange
    root = Path(__file__).resolve().parents[2]
    script = root / ".github/ci/test_release_identity.py"
    # Act
    result = subprocess.run(
        [sys.executable, str(script)],
        cwd=root,
        capture_output=True,
        text=True,
        timeout=300,
    )
    # Assert
    assert result.returncode == 0, result.stdout + result.stderr
