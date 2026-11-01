"""Build Writer assets from installed SDK/LivePaper public frontend packages.

Install .[frontend-build], then run python scripts/build_frontend.py.
Node/npm are external build tools. No sibling source checkouts are required.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import shutil
import subprocess
import tempfile
from pathlib import Path


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--offline", action="store_true", help="Use the existing npm cache only"
    )
    parser.add_argument("--receipt", type=Path)
    args = parser.parse_args()
    npm = shutil.which("npm")
    if not npm:
        raise SystemExit("Node/npm are required to build the browser assets")
    try:
        from scitex_live_paper import get_frontend_package_dir as live_paper_frontend
        from scitex_sdk import get_frontend_package_dir as sdk_frontend
    except ImportError as error:
        raise SystemExit(
            "Install the provider-capable wheels and scitex-writer[frontend-build]"
        ) from error

    root = Path(__file__).resolve().parents[1]
    source = root / "src/scitex_writer/_django/frontend"
    destination = source.parent / "static/writer"
    providers = {
        "scitex-sdk": sdk_frontend(),
        "scitex-live-paper": live_paper_frontend(),
    }
    versions = {
        name: json.loads((path / "package.json").read_text())["version"]
        for name, path in providers.items()
    }
    ignored = shutil.ignore_patterns("node_modules", "__pycache__", ".git")
    with tempfile.TemporaryDirectory(prefix="writer-frontend-build-") as directory:
        packages = Path(directory) / "packages"
        for name, package in providers.items():
            module = "scitex_sdk" if name == "scitex-sdk" else "scitex_live_paper"
            shutil.copytree(package, packages / name / "src" / module, ignore=ignored)
        frontend = packages / "scitex-writer/src/scitex_writer/_django/frontend"
        shutil.copytree(source, frontend, ignore=ignored)
        command = [npm, "ci"]
        if args.offline:
            command.append("--offline")
        subprocess.run(command, cwd=frontend, check=True)
        subprocess.run([npm, "run", "build"], cwd=frontend, check=True)
        output = frontend.parent / "static/writer"
        manifest = json.loads((output / ".vite/manifest.json").read_text())
        for item in manifest.values():
            for relative in [
                item["file"],
                *item.get("css", []),
                *item.get("assets", []),
            ]:
                member = (output / relative).resolve()
                if not member.is_relative_to(output.resolve()) or not member.is_file():
                    raise ValueError(f"Vite manifest asset unavailable: {relative}")
        hashes = {}
        for member in sorted(output.rglob("*")):
            if not member.is_file():
                continue
            if not member.resolve().is_relative_to(output.resolve()):
                raise ValueError("Build asset escaped the generated output directory")
            relative = member.relative_to(output)
            target = destination / relative
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(member, target)
            hashes[relative.as_posix()] = hashlib.sha256(
                member.read_bytes()
            ).hexdigest()
    receipt = {
        "frontend_packages": versions,
        "method": "public helpers, temporary portable layout, npm ci, tsc/Vite",
        "assets": hashes,
        "asset_count": len(hashes),
        "deleted_files": 0,
    }
    rendered = json.dumps(receipt, indent=2) + "\n"
    if args.receipt:
        args.receipt.parent.mkdir(parents=True, exist_ok=True)
        args.receipt.write_text(rendered)
    print(
        json.dumps(
            {
                "frontend_packages": versions,
                "asset_count": len(hashes),
                "receipt": str(args.receipt) if args.receipt else None,
            }
        )
    )


if __name__ == "__main__":
    main()
