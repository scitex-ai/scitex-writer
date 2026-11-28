#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# Test file for: scripts/shell/modules/process_diff.sh::portable_diff_header
# (the latexdiff header must not name the mktemp file of the old side).

import re
import subprocess
import sys
from pathlib import Path

import pytest

ROOT_DIR = Path(__file__).resolve().parent.parent.parent.parent
PROCESS_DIFF = ROOT_DIR / "scripts" / "shell" / "modules" / "process_diff.sh"

HEADER = (
    "%DIF LATEXDIFF DIFFERENCE FILE\n"
    "%DIF DEL /home/someone/.cache/tmp/tmp.2QGwpDfMY8.tex   Sat Apr 18 18:03:47 2026\n"
    "%DIF ADD ./01_manuscript/manuscript.tex   Sat Apr 18 18:05:00 2026\n"
    "\\documentclass{article}\n"
    "%DIF DEL body line that is not a header\n"
)


def _function_source() -> str:
    """The portable_diff_header() definition, cut from the real module (the
    module runs its own main() when sourced, so it cannot be sourced)."""
    text = PROCESS_DIFF.read_text()
    match = re.search(r"^portable_diff_header\(\) \{\n.*?^\}\n", text, re.S | re.M)
    assert match, "portable_diff_header() not found in process_diff.sh"
    return match.group(0)


@pytest.fixture
def rewritten(tmp_path):
    diff_tex = tmp_path / "manuscript_diff.tex"
    diff_tex.write_text(HEADER)
    script = (
        _function_source()
        + 'portable_diff_header "$1" "abc1234:01_manuscript/manuscript.tex"'
        + ' "def5678+:01_manuscript/manuscript.tex"\n'
    )
    subprocess.run(["bash", "-c", script, "bash", str(diff_tex)], check=True)
    return diff_tex.read_text().splitlines()


def test_old_side_is_named_by_commit_and_relative_path(rewritten):
    # Arrange
    lines = rewritten
    # Act
    del_line = lines[1]
    # Assert
    assert del_line == (
        "%DIF DEL abc1234:01_manuscript/manuscript.tex   Sat Apr 18 18:03:47 2026"
    )


def test_new_side_is_named_by_commit_and_relative_path(rewritten):
    # Arrange
    lines = rewritten
    # Act
    add_line = lines[2]
    # Assert
    assert add_line == (
        "%DIF ADD def5678+:01_manuscript/manuscript.tex   Sat Apr 18 18:05:00 2026"
    )


def test_no_host_path_remains(rewritten):
    # Arrange
    text = "\n".join(rewritten)
    # Act
    leaked = "/home/" in text
    # Assert
    assert leaked is False


def test_body_is_untouched(rewritten):
    # Arrange
    lines = rewritten
    # Act
    tail = lines[3:]
    # Assert
    assert tail == HEADER.splitlines()[3:]


if __name__ == "__main__":
    sys.exit(pytest.main([__file__, "-v"]))

# EOF
