"""The offline documentation shipped by Writer must identify its own version."""

import re
from importlib.metadata import version
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
DOCS = ROOT / "src/scitex_writer/_sphinx_html"
VERSION = version("scitex-writer")


def test_bundled_docs_title_identifies_project_version():
    # Arrange
    index = (DOCS / "index.html").read_text()
    # Act
    title = re.search(r"<title>(.*?)</title>", index).group(1)
    # Assert
    assert f"SciTeX Writer v{VERSION}" in title


def test_bundled_docs_search_options_identify_project_version():
    # Arrange
    script = (DOCS / "_static/documentation_options.js").read_text()
    # Act
    version = re.search(r"\bVERSION:\s*(['\"])(.*?)\1", script).group(2)
    # Assert
    assert version == VERSION


def test_docs_builder_refuses_wrong_installed_version_before_replacing_files(tmp_path):
    # Arrange
    import shutil
    import subprocess
    import sys

    (tmp_path / "scripts").mkdir()
    script = tmp_path / "scripts/build_docs.py"
    shutil.copyfile(ROOT / "scripts/build_docs.py", script)
    (tmp_path / "pyproject.toml").write_text('[project]\nversion = "0.0.0.dev0"\n')
    output = tmp_path / "src/scitex_writer/_sphinx_html"
    output.mkdir(parents=True)
    sentinel = output / "keep.txt"
    sentinel.write_text("unchanged")
    # Act
    result = subprocess.run(
        [sys.executable, str(script)], capture_output=True, text=True
    )
    # Assert
    assert (
        result.returncode != 0,
        "Install this checkout" in result.stderr,
        sentinel.read_text(),
    ) == (True, True, "unchanged")
