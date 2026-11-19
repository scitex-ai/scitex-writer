#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# Test file for: scripts/python/check_media_provenance.py
#
# Strict mode (--require-under-scripts) in a VENDORED workspace
# (<repo>/.scitex/writer) must accept media that resolve under the RESEARCH
# repo's <repo>/scripts -- not only under the workspace's own scripts/
# (issue #505). Media resolving elsewhere still fail.

import subprocess
import sys
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parent.parent.parent.parent
_SCRIPT = ROOT_DIR / "scripts" / "python" / "check_media_provenance.py"
_FIG_MEDIA = "01_manuscript/contents/figures/caption_and_media"


def _vendored_repo(tmp_path: Path, target_rel: str) -> Path:
    """<repo>/.scitex/writer with one figure symlinked to <repo>/<target_rel>."""
    repo = tmp_path / "research"
    target = repo / target_rel
    target.parent.mkdir(parents=True)
    target.write_bytes(b"png")
    workspace = repo / ".scitex" / "writer"
    media = workspace / _FIG_MEDIA
    media.mkdir(parents=True)
    (media / "fig.png").symlink_to(target)
    return workspace


def _run(workspace: Path) -> subprocess.CompletedProcess:
    # An explicit minimal env: no inherited SCITEX_* settings.
    env = {"PATH": "/usr/bin:/bin", "HOME": str(workspace)}
    return subprocess.run(
        [
            sys.executable,
            str(_SCRIPT),
            str(workspace),
            "--level",
            "error",
            "--require-under-scripts",
        ],
        capture_output=True,
        text=True,
        env=env,
    )


def test_vendored_media_under_repo_scripts_pass(tmp_path):
    # Arrange
    workspace = _vendored_repo(tmp_path, "scripts/fig_out/fig.png")

    # Act
    proc = _run(workspace)

    # Assert
    assert (proc.returncode, "resolving under scripts/" in proc.stdout) == (0, True)


def test_vendored_media_outside_scripts_fail(tmp_path):
    # Arrange
    workspace = _vendored_repo(tmp_path, "data/fig.png")

    # Act
    proc = _run(workspace)

    # Assert
    assert (proc.returncode != 0, "resolves outside scripts/" in proc.stdout) == (
        True,
        True,
    )


# EOF
