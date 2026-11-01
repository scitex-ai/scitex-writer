"""Run the tracked contributor build with real installed frontend packages.

Requires .[frontend-build] and Node/npm. No mocks, sibling checkouts or live data.
"""

from __future__ import annotations

import hashlib
import json
import subprocess
import sys
import tempfile
from pathlib import Path


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main() -> None:
    root = Path(__file__).resolve().parents[2]
    frontend = root / "src/scitex_writer/_django/frontend"
    package_files = [frontend / "package.json", frontend / "package-lock.json"]
    before = [digest(path) for path in package_files]
    with tempfile.TemporaryDirectory(prefix="writer-build-check-") as directory:
        receipt = Path(directory) / "receipt.json"
        subprocess.run(
            [
                sys.executable,
                str(root / "scripts/build_frontend.py"),
                "--receipt",
                str(receipt),
            ],
            check=True,
        )
        observed = json.loads(receipt.read_text())
        assert set(observed["frontend_packages"]) == {"scitex-sdk", "scitex-live-paper"}
        assert observed["asset_count"] == len(observed["assets"]) > 0
        static = frontend.parent / "static/writer"
        for relative, expected in observed["assets"].items():
            path = (static / relative).resolve()
            assert path.is_relative_to(static.resolve())
            assert digest(path) == expected
        assert [digest(path) for path in package_files] == before
        print(
            json.dumps(
                {
                    "tracked_build_command": "passed",
                    "frontend_packages": observed["frontend_packages"],
                    "asset_count": observed["asset_count"],
                    "dependency_files_unchanged": True,
                }
            )
        )


if __name__ == "__main__":
    main()
