"""Prepare a source-bound offline docs patch for normal pull-request review."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path

BUNDLE = "src/scitex_writer/_sphinx_html"


def git(root: Path, *args: str, env: dict | None = None) -> bytes:
    return subprocess.run(
        ["git", *args], cwd=root, env=env, check=True, capture_output=True
    ).stdout


def _verify_staged_bundle(root: Path, env: dict, files: dict) -> None:
    """Bind isolated-index membership and blob bytes to the build receipt."""
    staged = {
        os.fsdecode(path)
        for path in git(root, "ls-files", "-z", "--", BUNDLE, env=env).split(b"\0")
        if path
    }
    if staged != {f"{BUNDLE}/{name}" for name in files}:
        raise ValueError("Staged documentation differs from the build receipt")
    for name, digest in files.items():
        blob = git(root, "show", f":{BUNDLE}/{name}", env=env)
        if hashlib.sha256(blob).hexdigest() != digest:
            raise ValueError("Staged documentation differs from the build receipt")


def write_review(root: Path, output: Path, base: str, receipt: dict) -> dict:
    """Capture additions/deletions/binary bytes without staging the real index."""
    if git(root, "rev-parse", "HEAD").decode().strip() != base:
        raise ValueError("Source commit changed while generating documentation")
    target = root / BUNDLE
    actual = {}
    for file in sorted(target.rglob("*")):
        if file.is_symlink():
            raise ValueError("Generated documentation contains a symlink")
        if file.is_file():
            actual[file.relative_to(target).as_posix()] = hashlib.sha256(
                file.read_bytes()
            ).hexdigest()
    if actual != receipt["files"]:
        raise ValueError("Generated documentation differs from the build receipt")
    with tempfile.TemporaryDirectory(prefix="writer-docs-index-") as directory:
        env = {**os.environ, "GIT_INDEX_FILE": str(Path(directory) / "index")}
        git(root, "read-tree", base, env=env)
        git(root, "add", "-A", "--", BUNDLE, env=env)
        _verify_staged_bundle(root, env, receipt["files"])
        patch = git(
            root,
            "diff",
            "--cached",
            "--binary",
            "--no-color",
            "--full-index",
            "--src-prefix=a/",
            "--dst-prefix=b/",
            base,
            "--",
            BUNDLE,
            env=env,
        )
        summary = git(root, "diff", "--cached", "--stat", base, "--", BUNDLE, env=env)
    if git(root, "rev-parse", "HEAD").decode().strip() != base:
        raise ValueError("Source commit changed while preparing the review patch")
    manifest = {
        "base_commit": base,
        "source_version": receipt["source_version"],
        "update_required": bool(patch),
        "patch_sha256": hashlib.sha256(patch).hexdigest(),
        "bundle_path": BUNDLE,
        "python_version": receipt["python_version"],
        "toolchain": receipt["toolchain"],
        "acceptance": "generated review candidate; not reviewed, committed or published",
    }
    (output / "bundle.patch").write_bytes(patch)
    (output / "summary.txt").write_bytes(summary)
    (output / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n")
    return manifest


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[1]
    if args.output.is_symlink() or args.output.resolve().is_relative_to(root):
        raise SystemExit(
            "Review output must be outside the checkout, without a symlink destination"
        )
    if args.output.exists() and any(args.output.iterdir()):
        raise SystemExit(
            "Review output must be new or empty; existing evidence is preserved"
        )
    if git(root, "status", "--porcelain", "--untracked-files=normal"):
        raise SystemExit(
            "Commit the review source first; refusing to overwrite a dirty checkout"
        )
    base = git(root, "rev-parse", "HEAD").decode().strip()
    args.output.mkdir(parents=True, exist_ok=True)
    receipt = args.output / "generated-docs.json"
    subprocess.run(
        [
            sys.executable,
            str(root / "scripts/build_docs.py"),
            "--receipt",
            str(receipt),
        ],
        cwd=root,
        check=True,
    )
    result = write_review(root, args.output, base, json.loads(receipt.read_text()))
    print(json.dumps(result))


if __name__ == "__main__":
    main()
