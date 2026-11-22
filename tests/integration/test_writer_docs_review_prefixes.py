"""Review patches must replay with plain git apply despite local diff settings."""

import importlib.util
from pathlib import Path

SPEC = importlib.util.spec_from_file_location(
    "writer_artifact_fixtures",
    Path(__file__).with_name("test_writer_docs_review_artifact.py"),
)
FIXTURES = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(FIXTURES)
REVIEW = FIXTURES.REVIEW
repository = FIXTURES.repository
git = FIXTURES.git
receipt = FIXTURES.receipt


def test_no_prefix_configuration_preserves_patch_replay(repository, tmp_path):
    # Arrange
    git(repository, "config", "diff.noprefix", "true")
    base = git(repository, "rev-parse", "HEAD").decode().strip()
    bundle = repository / REVIEW.BUNDLE
    (bundle / "index.html").write_text("generated html\n")
    (bundle / "new asset.bin").write_bytes(b"\x00\xffgenerated\n")
    (bundle / "retired.css").unlink()
    generated = receipt(repository)
    before_index = git(repository, "diff", "--cached", "--binary")
    output = tmp_path / "review"
    output.mkdir()
    replay = tmp_path / "replay"
    # Act
    result = REVIEW.write_review(repository, output, base, generated)
    git(repository, "worktree", "add", "--detach", str(replay), base)
    git(replay, "apply", "--check", str(output / "bundle.patch"))
    git(replay, "apply", str(output / "bundle.patch"))
    observed = (
        receipt(replay)["files"],
        receipt(repository)["files"],
        result["update_required"],
        git(repository, "config", "diff.noprefix").decode().strip(),
        git(repository, "diff", "--cached", "--binary"),
        git(repository, "rev-parse", "HEAD").decode().strip(),
        (repository / "README.md").read_text(),
    )
    # Assert
    assert observed == (
        generated["files"],
        generated["files"],
        True,
        "true",
        before_index,
        base,
        "Preserve unrelated source\n",
    )
