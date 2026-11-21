"""Real local clean filters must preserve receipt bytes for docs review."""

import importlib.util
import shlex
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

SPEC = importlib.util.spec_from_file_location(
    "writer_staging_fixtures",
    Path(__file__).with_name("test_writer_docs_review_staging.py"),
)
STAGING = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(STAGING)
REVIEW = STAGING.REVIEW
repository = STAGING.repository
git = STAGING.git
receipt = STAGING.receipt


@pytest.fixture
def filtered_review_case(repository, tmp_path):
    def arrange(mode):
        programs = {
            "changing": "data.replace(b'generated', b'filtered')",
            "identity": "data",
        }
        program = (
            "import sys; data=sys.stdin.buffer.read(); "
            f"sys.stdout.buffer.write({programs[mode]})"
        )
        command = shlex.join([sys.executable, "-c", program])
        git(repository, "config", "filter.owned.clean", command)
        git(repository, "config", "filter.owned.required", "true")
        policy = repository / ".gitattributes"
        policy.write_text(REVIEW.BUNDLE + "/** -text filter=owned\n")
        git(repository, "add", policy.name)
        git(repository, "commit", "-qm", "owned clean filter")
        base = git(repository, "rev-parse", "HEAD").decode().strip()
        (repository / REVIEW.BUNDLE / "figure caption α.txt").write_bytes(
            b"generated content\r\n"
        )
        output = tmp_path / "review"
        output.mkdir()
        case = SimpleNamespace(
            root=repository,
            policy=policy,
            base=base,
            generated=receipt(repository),
            output=output,
            command=command,
        )
        case.before = STAGING.preserved_state(case)
        return case

    return arrange


def test_changing_clean_filter_refuses_review(filtered_review_case):
    # Arrange
    case = filtered_review_case("changing")
    # Act
    message = STAGING.refusal_message(case)
    observed = (
        message,
        list(case.output.iterdir()),
        STAGING.preserved_state(case),
        git(case.root, "config", "filter.owned.clean").decode().strip(),
    )
    # Assert
    assert observed == (STAGING.MESSAGE, [], case.before, case.command)


def test_identity_clean_filter_replays_review(filtered_review_case, tmp_path):
    # Arrange
    case = filtered_review_case("identity")
    replay = tmp_path / "replay"
    # Act
    result = REVIEW.write_review(case.root, case.output, case.base, case.generated)
    git(case.root, "worktree", "add", "--detach", str(replay), case.base)
    git(replay, "apply", "--check", str(case.output / "bundle.patch"))
    git(replay, "apply", str(case.output / "bundle.patch"))
    observed = (
        receipt(replay)["files"],
        result["update_required"],
        STAGING.preserved_state(case),
        git(case.root, "config", "filter.owned.clean").decode().strip(),
    )
    # Assert
    assert observed == (case.generated["files"], True, case.before, case.command)
