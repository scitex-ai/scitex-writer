"""Real Git round trips for leaf-generated docs review artifacts."""

import hashlib
import importlib.util
import json
import subprocess
from pathlib import Path

import pytest
import yaml

ROOT = Path(__file__).resolve().parents[2]
SPEC = importlib.util.spec_from_file_location(
    "prepare_docs_update", ROOT / "scripts/prepare_docs_update.py"
)
REVIEW = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(REVIEW)


def git(root, *args):
    return subprocess.check_output(["git", *args], cwd=root)


@pytest.fixture
def repository(tmp_path):
    root = tmp_path / "source"
    root.mkdir()
    git(root, "init", "-q")
    git(root, "config", "user.name", "Docs fixture")
    git(root, "config", "user.email", "docs@example.invalid")
    git(root, "config", "core.hooksPath", "/dev/null")
    git(root, "config", "core.excludesFile", "/dev/null")
    (root / "README.md").write_text("Preserve unrelated source\n")
    bundle = root / REVIEW.BUNDLE
    bundle.mkdir(parents=True)
    (bundle / "index.html").write_text("old html\n")
    (bundle / "retired.css").write_text("old style\n")
    git(root, "add", ".")
    git(root, "commit", "-qm", "baseline")
    return root


def receipt(root):
    # This tests the Git artifact writer; the real builder supplies provenance.
    bundle = root / REVIEW.BUNDLE
    return {
        "source_version": "1.0.0",
        "python_version": "fixture",
        "toolchain": {"fixture": "1"},
        "files": {
            f.relative_to(bundle).as_posix(): hashlib.sha256(f.read_bytes()).hexdigest()
            for f in bundle.rglob("*")
            if f.is_file()
        },
    }


def test_patch_replays_changed_new_binary_and_deleted_files_without_staging(
    repository, tmp_path
):
    # Arrange
    root = repository
    base = git(root, "rev-parse", "HEAD").decode().strip()
    bundle = root / REVIEW.BUNDLE
    (bundle / "index.html").write_text("new html\n")
    (bundle / "retired.css").unlink()
    (bundle / "asset.bin").write_bytes(bytes(range(256)))
    generated = receipt(root)
    output = tmp_path / "review"
    output.mkdir()
    # Act
    result = REVIEW.write_review(root, output, base, generated)
    replay = tmp_path / "replay"
    git(root, "worktree", "add", "--detach", str(replay), base)
    git(replay, "apply", "--check", str(output / "bundle.patch"))
    git(replay, "apply", str(output / "bundle.patch"))
    # Assert
    assert (
        result["update_required"],
        git(root, "diff", "--cached"),
        git(root, "rev-parse", "HEAD").decode().strip(),
        receipt(replay)["files"],
        (replay / "README.md").read_text(),
        result["patch_sha256"],
    ) == (
        True,
        b"",
        base,
        generated["files"],
        "Preserve unrelated source\n",
        hashlib.sha256((output / "bundle.patch").read_bytes()).hexdigest(),
    )


def test_unchanged_bundle_produces_an_explicit_no_update_receipt(repository, tmp_path):
    # Arrange
    output = tmp_path / "review"
    output.mkdir()
    base = git(repository, "rev-parse", "HEAD").decode().strip()
    # Act
    result = REVIEW.write_review(repository, output, base, receipt(repository))
    # Assert
    assert (
        result["update_required"],
        (output / "bundle.patch").read_bytes(),
        json.loads((output / "manifest.json").read_text())["base_commit"],
    ) == (False, b"", base)


def test_changed_commit_is_refused_without_writing_a_candidate(repository, tmp_path):
    # Arrange
    output = tmp_path / "review"
    output.mkdir()
    base = git(repository, "rev-parse", "HEAD").decode().strip()
    git(repository, "commit", "--allow-empty", "-qm", "new source")
    # Act
    try:
        REVIEW.write_review(repository, output, base, receipt(repository))
    except ValueError as error:
        message = str(error)
    else:
        message = None
    # Assert
    assert (message, list(output.iterdir())) == (
        "Source commit changed while generating documentation",
        [],
    )


def test_unreceipted_generated_bytes_are_refused(repository, tmp_path):
    # Arrange
    output = tmp_path / "review"
    output.mkdir()
    base = git(repository, "rev-parse", "HEAD").decode().strip()
    generated = receipt(repository)
    (repository / REVIEW.BUNDLE / "index.html").write_text("changed after build")
    # Act
    try:
        REVIEW.write_review(repository, output, base, generated)
    except ValueError as error:
        message = str(error)
    else:
        message = None
    # Assert
    assert (message, list(output.iterdir())) == (
        "Generated documentation differs from the build receipt",
        [],
    )


def test_workflow_uploads_candidate_before_the_fail_closed_source_gate():
    # Arrange
    source = (ROOT / ".github/workflows/vendor-sphinx-html.yml").read_text()
    workflow = yaml.safe_load(source)
    steps = workflow["jobs"]["vendor"]["steps"]
    # Act
    upload = next(
        i
        for i, s in enumerate(steps)
        if s.get("uses", "").startswith("actions/upload-artifact@")
    )
    gate = next(
        i for i, s in enumerate(steps) if "git status --porcelain" in s.get("run", "")
    )
    # Assert
    assert (
        workflow["permissions"],
        steps[0]["with"]["persist-credentials"],
        upload < gate,
        "exit 1" in steps[gate]["run"],
        "--untracked-files=all" in steps[gate]["run"],
        any(
            x in source
            for x in (
                "git push",
                "git commit",
                "continue-on-error",
                "pull-requests: write",
            )
        ),
    ) == ({"contents": "read"}, False, True, True, True, False)


def test_dirty_source_is_refused_without_changing_the_callers_staging(
    repository, tmp_path
):
    # Arrange
    import shutil
    import sys

    script = repository / "scripts/prepare_docs_update.py"
    script.parent.mkdir()
    shutil.copyfile(ROOT / "scripts/prepare_docs_update.py", script)
    git(repository, "add", "scripts")
    git(repository, "commit", "-qm", "review helper")
    (repository / "README.md").write_text("Pending user work\n")
    git(repository, "add", "README.md")
    staged = git(repository, "diff", "--cached", "--binary")
    output = tmp_path / "review"
    # Act
    result = subprocess.run(
        [sys.executable, str(script), "--output", str(output)],
        capture_output=True,
        text=True,
    )
    # Assert
    assert (
        result.returncode != 0 and "dirty checkout" in result.stderr,
        git(repository, "diff", "--cached", "--binary"),
        (repository / "README.md").read_text(),
        output.exists(),
    ) == (True, staged, "Pending user work\n", False)
