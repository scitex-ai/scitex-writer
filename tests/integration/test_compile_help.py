"""Packaged shell help is read-only and independent of compile dependencies."""

from __future__ import annotations

import hashlib
import os
import shutil
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]


@pytest.fixture
def engine(tmp_path):
    package = tmp_path / "paper"
    package.mkdir()
    shutil.copy2(ROOT / "compile.sh", package / "compile.sh")
    shutil.copytree(ROOT / "scripts", package / "scripts")
    for script in (package / "scripts").rglob("*.sh"):
        script.chmod(0o644)
    tools = tmp_path / "tools"
    tools.mkdir()
    for name in ("bash", "cat", "dirname", "basename", "date", "git"):
        binary = shutil.which(name)
        if binary is None:
            raise RuntimeError(f"Required real test tool is unavailable: {name}")
        (tools / name).symlink_to(binary)
    environment = {
        **os.environ,
        "PATH": str(tools),
        "SCITEX_WRITER_PROJECT_ROOT": str(tmp_path / "absent"),
    }
    environment.pop("PROJECT_ROOT", None)
    return package, environment


def _snapshot(root):
    return {
        str(path.relative_to(root)): hashlib.sha256(path.read_bytes()).hexdigest()
        if path.is_file()
        else "directory"
        for path in root.rglob("*")
    }


@pytest.mark.parametrize(
    "relative,arguments,expected",
    [
        ("compile.sh", ["--help"], "Usage: ./compile.sh"),
        ("compile.sh", ["-h"], "Usage: ./compile.sh"),
        ("compile.sh", ["--help-recursive"], "compile_revision.sh"),
        ("compile.sh", ["manuscript", "--help"], "compile_manuscript.sh"),
        ("compile.sh", ["supplementary", "--help"], "compile_supplementary.sh"),
        ("compile.sh", ["revision", "--help"], "compile_revision.sh"),
        ("compile.sh", ["all", "--help"], "compile_revision.sh"),
        ("scripts/shell/compile_manuscript.sh", ["--help"], "compile_manuscript.sh"),
        (
            "scripts/shell/compile_supplementary.sh",
            ["--help"],
            "compile_supplementary.sh",
        ),
        ("scripts/shell/compile_revision.sh", ["--help"], "compile_revision.sh"),
    ],
)
def test_packaged_help_needs_no_config_yq_tex_or_project_writes(
    engine, relative, arguments, expected
):
    # Arrange
    package, environment = engine
    before = _snapshot(package)
    # Act
    result = subprocess.run(
        ["/usr/bin/bash", str(package / relative), *arguments],
        cwd=package,
        env=environment,
        capture_output=True,
        text=True,
        timeout=15,
    )
    observed = (
        result.returncode,
        expected in result.stdout,
        "No help available" not in result.stdout,
        _snapshot(package) == before,
    )
    # Assert
    assert observed == (0, True, True, True)


def test_real_compilation_still_refuses_a_missing_yq(engine):
    # Arrange
    package, environment = engine
    shutil.copytree(ROOT / "config", package / "config")
    environment["SCITEX_WRITER_PROJECT_ROOT"] = str(package)
    # Act
    result = subprocess.run(
        ["/usr/bin/bash", str(package / "scripts/shell/compile_manuscript.sh")],
        cwd=package,
        env=environment,
        capture_output=True,
        text=True,
        timeout=15,
    )
    # Assert
    assert (
        result.returncode != 0,
        "yq not found on PATH" in result.stdout + result.stderr,
    ) == (True, True)
