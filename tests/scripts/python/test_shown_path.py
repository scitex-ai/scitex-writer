#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# Test file for: scripts/python/_shown_path.py + its use in compile_tex_structure
# (the flattened .tex never names the checkout's absolute path).

import os
import sys
from pathlib import Path

import pytest

ROOT_DIR = Path(__file__).resolve().parent.parent.parent.parent
sys.path.insert(0, str(ROOT_DIR / "scripts" / "python"))

from _shown_path import shown_path  # noqa: E402
from compile_tex_structure import expand_inputs  # noqa: E402


@pytest.fixture
def in_project(tmp_path):
    """cwd = a project root (as during a compile); restored afterwards."""
    saved = os.getcwd()
    os.chdir(tmp_path)
    try:
        yield tmp_path
    finally:
        os.chdir(saved)


def test_absolute_path_under_cwd_is_dot_relative(in_project):
    # Arrange
    path = in_project / "01_manuscript" / "x.tex"
    # Act
    out = shown_path(path)
    # Assert
    assert out == "./01_manuscript/x.tex"


def test_path_outside_cwd_is_unchanged(in_project, tmp_path_factory):
    # Arrange
    other = tmp_path_factory.mktemp("elsewhere") / "x.tex"
    # Act
    out = shown_path(other)
    # Assert
    assert out == str(other)


def test_expand_inputs_file_comment_is_project_relative(in_project):
    # Arrange: a base file inputs another by ABSOLUTE path (as a FINAL.tex
    # written by an older pipeline did).
    part = in_project / "01_manuscript" / "contents" / "part.tex"
    part.parent.mkdir(parents=True)
    part.write_text("PART\n")
    base = in_project / "01_manuscript" / "base.tex"
    base.write_text(f"\\input{{{part}}}\n")
    # Act
    out = expand_inputs(base)
    # Assert
    assert str(in_project) not in out


if __name__ == "__main__":
    sys.exit(pytest.main([__file__, "-v"]))

# EOF
