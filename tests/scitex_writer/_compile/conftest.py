#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Shared fixtures for the compile tests.

`valid_project` materialises a REAL, structurally valid writer workspace on
disk from nothing -- no template clone, no network, no mocks -- by asking the
real validator what is missing until it is satisfied. Lifted out of
test__runner.py so the event-log tests can build the same workspace instead
of cloning the template from GitHub per test (which is what
`ensure_workspace` does, and what made a first draft of those tests take
minutes and need the network).
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

from scitex_writer._compile._validator import validate_before_compile


def _build_valid_project(project_dir: Path) -> None:
    """Materialize a structurally-valid scitex-writer project on disk.

    Builds the top-level trees, then iteratively creates whatever
    validate_before_compile reports as missing until it passes — a real
    project, no mocks. Compile scripts are written as no-op executables.
    """
    for sub in (
        "config",
        "00_shared",
        "01_manuscript",
        "02_supplementary",
        "03_revision",
        "scripts",
    ):
        (project_dir / sub).mkdir(exist_ok=True)

    for _ in range(60):
        try:
            validate_before_compile(project_dir)
            break
        except Exception as exc:  # ProjectValidationError
            made = False
            for rel in re.findall(r"expected at: ([^\s)]+)", str(exc)):
                target = project_dir / rel
                if "." in target.name and target.suffix:
                    target.parent.mkdir(parents=True, exist_ok=True)
                    target.write_text("")
                else:
                    target.mkdir(parents=True, exist_ok=True)
                made = True
            if not made:
                raise
    else:  # pragma: no cover - safety net for an unexpected validator
        raise RuntimeError("could not build a valid project structure")

    for doc_type in ("manuscript", "supplementary", "revision"):
        script = project_dir / "scripts" / "shell" / f"compile_{doc_type}.sh"
        script.parent.mkdir(parents=True, exist_ok=True)
        script.write_text("#!/bin/bash\nexit 0\n")
        script.chmod(0o755)


class _RecordingCommandRunner:
    """Real _run_sh_command stand-in: records the cmd, returns success."""

    def __init__(self):
        self.cmd = None

    def __call__(self, cmd, **kwargs):
        self.cmd = list(cmd)
        return {"stdout": "", "stderr": "", "exit_code": 0, "success": True}


@pytest.fixture
def valid_project(tmp_path):
    _build_valid_project(tmp_path)
    return tmp_path

# EOF
