"""Human text conversions must not hide changed documentation receipt bytes."""

import importlib.util
import shlex
import sys
from pathlib import Path

SPEC = importlib.util.spec_from_file_location(
    "writer_textconv_fixtures",
    Path(__file__).with_name("test_writer_docs_review_artifact.py"),
)
FIXTURES = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(FIXTURES)
REVIEW = FIXTURES.REVIEW
repository = FIXTURES.repository
git = FIXTURES.git
receipt = FIXTURES.receipt


def test_text_conversion_preserves_raw_patch_replay(repository, tmp_path):
    # Arrange
    policy = repository / ".gitattributes"
    rule = REVIEW.BUNDLE + "/** diff=owned\n"
    policy.write_text(rule)
    git(repository, "add", policy.name)
    git(repository, "commit", "-qm", "owned diff attribute")
    base = git(repository, "rev-parse", "HEAD").decode().strip()
    marker = tmp_path / "textconv-invoked"
    program = (
        "from pathlib import Path; "
        f"Path({str(marker)!r}).write_text('called'); "
        "print('same human preview for all input')"
    )
    command = shlex.join([sys.executable, "-c", program])
    git(repository, "config", "diff.owned.textconv", command)
    (repository / REVIEW.BUNDLE / "index.html").write_text("generated content\n")
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
        git(repository, "config", "diff.owned.textconv").decode().strip(),
        policy.read_text(),
        git(repository, "diff", "--cached", "--binary"),
        git(repository, "rev-parse", "HEAD").decode().strip(),
        (repository / "README.md").read_text(),
        marker.exists(),
    )
    # Assert
    assert observed == (
        generated["files"],
        generated["files"],
        True,
        command,
        rule,
        before_index,
        base,
        "Preserve unrelated source\n",
        False,
    )
