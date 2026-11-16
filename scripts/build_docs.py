"""Build Writer's version-bound offline HTML using installed docs dependencies.

Run with Python 3.11+ after installing .[docs,dev]. No manuscript is compiled.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import shutil
import subprocess
import sys
import tempfile
from importlib.metadata import version
from pathlib import Path

import tomllib


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--receipt", type=Path)
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[1]
    expected = tomllib.loads((root / "pyproject.toml").read_text())["project"][
        "version"
    ]
    installed = version("scitex-writer")
    if installed != expected:
        raise SystemExit(
            f"Install this checkout's docs dependencies first: {installed} != {expected}"
        )
    target = root / "src/scitex_writer/_sphinx_html"
    if target.is_symlink():
        raise SystemExit("Refusing a symlinked offline documentation destination")
    with tempfile.TemporaryDirectory(prefix="writer-offline-docs-") as directory:
        work = Path(directory)
        output = work / "html"
        subprocess.run(
            [
                sys.executable,
                "-m",
                "sphinx",
                "-W",
                "--keep-going",
                "-b",
                "html",
                "-d",
                str(work / "doctrees"),
                str(root / "docs/sphinx"),
                str(output),
            ],
            check=True,
            cwd=root,
        )
        index = (output / "index.html").read_text()
        options = (output / "_static/documentation_options.js").read_text()
        match = re.search(r"\bVERSION:\s*(['\"])(.*?)\1", options)
        if (
            f"SciTeX Writer v{expected}" not in index
            or not match
            or match.group(2) != expected
        ):
            raise SystemExit("Generated HTML does not identify this Writer version")
        # Sphinx caches are not part of the offline documentation payload.
        (output / ".buildinfo").unlink(missing_ok=True)
        (output / ".nojekyll").touch()
        if target.exists():
            shutil.rmtree(target)
        shutil.copytree(output, target)
    hashes = {
        f.relative_to(target).as_posix(): hashlib.sha256(f.read_bytes()).hexdigest()
        for f in sorted(target.rglob("*"))
        if f.is_file()
    }
    receipt = {
        "source_version": expected,
        "installed_version": installed,
        "sphinx_version": version("sphinx"),
        "files": hashes,
        "scope": "strict generated offline HTML/version delivery; not whole-guide semantic or hosted acceptance",
    }
    if args.receipt:
        args.receipt.parent.mkdir(parents=True, exist_ok=True)
        args.receipt.write_text(json.dumps(receipt, indent=2) + "\n")
    print(json.dumps({"version": expected, "files": len(hashes)}))


if __name__ == "__main__":
    main()
