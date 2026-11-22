"""The actual docs builder must refuse symlinked bundle publication."""

import shutil
import subprocess
import sys
from importlib.metadata import version
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def test_symlink_bundle_destination_preserves_existing_files(tmp_path):
    # Arrange
    scripts = tmp_path / "scripts"
    scripts.mkdir()
    script = scripts / "build_docs.py"
    shutil.copyfile(ROOT / "scripts/build_docs.py", script)
    installed = version("scitex-writer")
    (tmp_path / "pyproject.toml").write_text(f'[project]\nversion = "{installed}"\n')
    existing = tmp_path / "existing-docs"
    existing.mkdir()
    sentinel = existing / "index.html"
    sentinel.write_bytes(b"\x00preserve installed documentation\xff\n")
    target = tmp_path / "src/scitex_writer/_sphinx_html"
    target.parent.mkdir(parents=True)
    target.symlink_to(existing, target_is_directory=True)
    receipt = tmp_path / "new-receipt.json"
    before = (sentinel.read_bytes(), sentinel.stat().st_ino, target.lstat().st_ino)
    # Act
    result = subprocess.run(
        [sys.executable, str(script), "--receipt", str(receipt)],
        capture_output=True,
        timeout=10,
    )
    observed = (
        result.returncode,
        result.stdout,
        result.stderr,
        target.is_symlink(),
        target.resolve(),
        (sentinel.read_bytes(), sentinel.stat().st_ino, target.lstat().st_ino),
        sorted(x.name for x in existing.iterdir()),
        receipt.exists(),
    )
    # Assert
    assert observed == (
        1,
        b"",
        b"Refusing a symlinked offline documentation destination\n",
        True,
        existing,
        before,
        ["index.html"],
        False,
    )
