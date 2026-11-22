"""Patch context and rendering must support the documented plain apply step."""

import importlib.util
import shlex
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

SPEC = importlib.util.spec_from_file_location(
    "writer_config_fixtures",
    Path(__file__).with_name("test_writer_docs_review_artifact.py"),
)
FIXTURES = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(FIXTURES)
REVIEW = FIXTURES.REVIEW
repository = FIXTURES.repository
git = FIXTURES.git
receipt = FIXTURES.receipt


@pytest.fixture(params=["zero-context", "external-diff"])
def configured_review_case(repository, tmp_path, request):
    target = repository / REVIEW.BUNDLE / "index.html"
    target.write_text("stable start\nold html\nstable end\n")
    git(repository, "add", REVIEW.BUNDLE)
    git(repository, "commit", "-qm", "owned context fixture")
    marker = tmp_path / "external-invoked"
    program = (
        "from pathlib import Path; "
        f"Path({str(marker)!r}).write_text('called'); "
        "print('owned external diff output')"
    )
    settings = {
        "zero-context": ("diff.context", "0"),
        "external-diff": ("diff.external", shlex.join([sys.executable, "-c", program])),
    }
    setting, value = settings[request.param]
    git(repository, "config", setting, value)
    base = git(repository, "rev-parse", "HEAD").decode().strip()
    target.write_text("stable start\ngenerated html\nstable end\n")
    output = tmp_path / "review"
    output.mkdir()
    return SimpleNamespace(
        root=repository,
        base=base,
        generated=receipt(repository),
        output=output,
        setting=setting,
        value=value,
        marker=marker,
        index=git(repository, "diff", "--cached", "--binary"),
    )


def test_local_diff_configuration_preserves_replay(configured_review_case, tmp_path):
    # Arrange
    case = configured_review_case
    replay = tmp_path / "replay"
    # Act
    result = REVIEW.write_review(case.root, case.output, case.base, case.generated)
    git(case.root, "worktree", "add", "--detach", str(replay), case.base)
    git(replay, "apply", "--check", str(case.output / "bundle.patch"))
    git(replay, "apply", str(case.output / "bundle.patch"))
    observed = (
        receipt(replay)["files"],
        receipt(case.root)["files"],
        result["update_required"],
        git(case.root, "config", case.setting).decode().strip(),
        git(case.root, "diff", "--cached", "--binary"),
        git(case.root, "rev-parse", "HEAD").decode().strip(),
        (case.root / "README.md").read_text(),
        case.marker.exists(),
    )
    # Assert
    assert observed == (
        case.generated["files"],
        case.generated["files"],
        True,
        case.value,
        case.index,
        case.base,
        "Preserve unrelated source\n",
        False,
    )
