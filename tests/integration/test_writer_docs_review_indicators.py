"""Machine-readable review patches must ignore human diff presentation."""

import importlib.util
from pathlib import Path

import pytest

SPEC = importlib.util.spec_from_file_location(
    "writer_indicator_fixtures",
    Path(__file__).with_name("test_writer_docs_review_artifact.py"),
)
FIXTURES = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(FIXTURES)
REVIEW = FIXTURES.REVIEW
repository = FIXTURES.repository
git = FIXTURES.git
receipt = FIXTURES.receipt


@pytest.mark.parametrize(
    "setting,value",
    [
        ("diff.outputIndicatorNew", ">"),
        ("diff.outputIndicatorOld", "<"),
        ("diff.outputIndicatorContext", "."),
        ("color.ui", "always"),
    ],
)
def test_presentation_settings_preserve_patch_replay(
    repository, tmp_path, setting, value
):
    # Arrange
    target = repository / REVIEW.BUNDLE / "index.html"
    target.write_text("old html\nstable heading\nstable footer\n")
    git(repository, "add", REVIEW.BUNDLE)
    git(repository, "commit", "-qm", "owned context lines")
    base = git(repository, "rev-parse", "HEAD").decode().strip()
    git(repository, "config", setting, value)
    target.write_text("generated html\nstable heading\nstable footer\n")
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
        git(repository, "config", setting).decode().strip(),
        git(repository, "diff", "--cached", "--binary"),
        git(repository, "rev-parse", "HEAD").decode().strip(),
        (repository / "README.md").read_text(),
    )
    # Assert
    assert observed == (
        generated["files"],
        generated["files"],
        True,
        value,
        before_index,
        base,
        "Preserve unrelated source\n",
    )
