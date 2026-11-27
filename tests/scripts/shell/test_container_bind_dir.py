#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# File: tests/scripts/shell/test_container_bind_dir.py

"""The LaTeX container must see every file a project links to (issue #535).

A Writer project nested in a repository (``<repo>/.scitex/writer``) holds its
figures as SYMLINKS into the producing scripts' outputs under ``<repo>/scripts``
-- the media-provenance check requires exactly that. The container used to bind
only the project directory, so those links dangled inside it unless the repo
happened to sit under a path the runtime binds by default ($HOME, /tmp). A
fresh clone on /scratch or a CI runner's work dir then failed its first
``\\includegraphics``; latexmk stopped after one pass and the table-total gate
reported "front matter shows 0 tables but the compile counted N".

These tests run the REAL ``command_switching.src`` resolvers. The compile test
builds a minimal fresh project and compiles it with whatever pdflatex the engine
resolves (native, module, or container). With a container it runs under
``APPTAINER_CONTAIN=1`` so $HOME and /tmp are NOT bound implicitly -- the bind
the engine passes is the only way the linked figure is visible, wherever the
test itself runs.
"""

import os
import shutil
import struct
import subprocess
import zlib
from pathlib import Path

import pytest

MODULE = "scripts/shell/modules/command_switching.src"


def _find_repo_root() -> Path:
    p = Path(__file__).resolve()
    for parent in [p, *p.parents]:
        if (parent / "pyproject.toml").is_file() and (parent / "compile.sh").is_file():
            return parent
    raise RuntimeError(f"Could not find repo root from {__file__}")


ROOT = _find_repo_root()


def _bash(snippet: str, *args: str, env=None) -> subprocess.CompletedProcess:
    script = f'source "{ROOT / MODULE}" >/dev/null 2>&1\n{snippet}'
    return subprocess.run(
        ["bash", "-c", script, "_", *args],
        cwd=str(ROOT),
        capture_output=True,
        text=True,
        env=env,
        timeout=600,
    )


def _git_init(path: Path) -> None:
    subprocess.run(["git", "init", "-q", str(path)], check=True)


def _png(path: Path) -> None:
    """Write a valid 1x1 grey PNG (no imaging library needed)."""

    def chunk(kind: bytes, data: bytes) -> bytes:
        body = kind + data
        return struct.pack(">I", len(data)) + body + struct.pack(">I", zlib.crc32(body))

    ihdr = struct.pack(">IIBBBBB", 1, 1, 8, 0, 0, 0, 0)
    idat = zlib.compress(b"\x00\x80")
    path.write_bytes(
        b"\x89PNG\r\n\x1a\n"
        + chunk(b"IHDR", ihdr)
        + chunk(b"IDAT", idat)
        + chunk(b"IEND", b"")
    )


@pytest.fixture
def nested_project(tmp_path):
    """<repo>/.scitex/writer with a figure symlinked to <repo>/scripts/out."""
    repo = tmp_path / "repo"
    repo.mkdir()
    _git_init(repo)
    out = repo / "scripts" / "out"
    out.mkdir(parents=True)
    _png(out / "fig.png")
    project = repo / ".scitex" / "writer"
    (project / "media").mkdir(parents=True)
    (project / "media" / "fig.png").symlink_to(out / "fig.png")
    (project / "main.tex").write_text(
        "\\documentclass{article}\\usepackage{graphicx}\n"
        "\\begin{document}\\includegraphics[width=1cm]{media/fig.png}\\end{document}\n",
        encoding="utf-8",
    )
    return repo, project


def test_bind_dir_is_the_enclosing_repository(nested_project):
    # Arrange
    repo, project = nested_project
    # Act
    proc = _bash('container_bind_dir "$1"', str(project))
    # Assert
    assert proc.stdout.strip() == str(repo.resolve())


def test_bind_dir_outside_git_is_the_project_itself(tmp_path):
    # Arrange
    project = tmp_path / "plain"
    project.mkdir()
    # Act
    proc = _bash('container_bind_dir "$1"', str(project.resolve()))
    # Assert
    assert proc.stdout.strip() == str(project.resolve())


@pytest.fixture
def pdflatex_available(nested_project):
    _, project = nested_project
    if not _bash('get_cmd_pdflatex "$1"', str(project)).stdout.strip():
        pytest.skip("no pdflatex resolvable (native, module, or container)")


def _compile(project: Path) -> str:
    """Compile main.tex with the engine-resolved pdflatex; describe the outcome."""
    env = dict(os.environ, APPTAINER_CONTAIN="1", SINGULARITY_CONTAIN="1")
    proc = _bash(
        'cmd=$(get_cmd_pdflatex "$1") && cd "$1" && '
        'eval "$cmd -interaction=nonstopmode -halt-on-error main.tex"',
        str(project),
        env=env,
    )
    log_file = project / "main.log"
    log = log_file.read_text(errors="replace") if log_file.is_file() else ""
    if (
        proc.returncode == 0
        and (project / "main.pdf").is_file()
        and "not found" not in log
    ):
        return "pdf built"
    return f"rc={proc.returncode}\n{log[-1_500:]}\n{proc.stderr[-1_500:]}"


def test_fresh_nested_project_compiles_its_linked_figure(
    nested_project, pdflatex_available
):
    # Arrange
    _, project = nested_project
    # Act
    outcome = _compile(project)
    # Assert
    assert outcome == "pdf built"


if __name__ == "__main__":
    import sys

    sys.exit(pytest.main([os.path.abspath(__file__)]))
