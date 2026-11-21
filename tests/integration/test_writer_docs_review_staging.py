"""Review receipts must bind the bytes Git actually puts in the patch."""

import hashlib
import importlib.util
import json
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
SPEC = importlib.util.spec_from_file_location(
    "writer_review_fixtures",
    Path(__file__).with_name("test_writer_docs_review_artifact.py"),
)
FIXTURES = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(FIXTURES)
REVIEW = FIXTURES.REVIEW
repository = FIXTURES.repository
git = FIXTURES.git
receipt = FIXTURES.receipt


@pytest.mark.parametrize("case", ["normalized", "ignored", "binary_crlf"])
def test_review_patch_binds_staged_bytes(repository, tmp_path, case):
    root = repository
    bundle = root / REVIEW.BUNDLE
    if case == "ignored":
        policy = root / ".gitignore"
        policy.write_text(REVIEW.BUNDLE + "/new.css\n")
    else:
        policy = root / ".gitattributes"
        rule = "text eol=lf" if case == "normalized" else "-text"
        policy.write_text(REVIEW.BUNDLE + "/** " + rule + "\n")
    git(root, "add", policy.name)
    git(root, "commit", "-qm", "owned Git policy")
    base = git(root, "rev-parse", "HEAD").decode().strip()
    target = bundle / ("new.css" if case == "ignored" else "index.html")
    target.write_bytes(b"generated content\r\n")
    generated = receipt(root)
    staged_before = git(root, "diff", "--cached", "--binary")
    policy_before = policy.read_bytes()
    output = tmp_path / "review"
    output.mkdir()
    if case in ["normalized", "ignored"]:
        with pytest.raises(
            ValueError, match="^Staged documentation differs from the build receipt$"
        ):
            REVIEW.write_review(root, output, base, generated)
        assert list(output.iterdir()) == []
    else:
        result = REVIEW.write_review(root, output, base, generated)
        replay = tmp_path / "replay"
        git(root, "worktree", "add", "--detach", str(replay), base)
        git(replay, "apply", "--check", str(output / "bundle.patch"))
        git(replay, "apply", str(output / "bundle.patch"))
        assert receipt(replay)["files"] == generated["files"]
        assert result["update_required"] is True
        assert (
            result["patch_sha256"]
            == hashlib.sha256((output / "bundle.patch").read_bytes()).hexdigest()
        )
        assert json.loads((output / "manifest.json").read_text())["base_commit"] == base
    assert receipt(root)["files"] == generated["files"]
    assert policy.read_bytes() == policy_before
    assert (root / "README.md").read_text() == "Preserve unrelated source\n"
    assert git(root, "diff", "--cached", "--binary") == staged_before
    assert git(root, "rev-parse", "HEAD").decode().strip() == base
