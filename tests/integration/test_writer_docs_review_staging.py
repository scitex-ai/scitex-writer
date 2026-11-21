"""Review receipts must bind the bytes Git actually puts in the patch."""

import hashlib
import importlib.util
import json
from pathlib import Path
from types import SimpleNamespace

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
MESSAGE = "Staged documentation differs from the build receipt"


@pytest.fixture
def staged_review_case(repository, tmp_path):
    def arrange(policy_name):
        policies = {
            "normalized": (
                ".gitattributes",
                REVIEW.BUNDLE + "/** text eol=lf\n",
                "index.html",
            ),
            "ignored": (".gitignore", REVIEW.BUNDLE + "/new.css\n", "new.css"),
            "binary": (".gitattributes", REVIEW.BUNDLE + "/** -text\n", "index.html"),
        }
        filename, rule, target_name = policies[policy_name]
        policy = repository / filename
        policy.write_text(rule)
        git(repository, "add", policy.name)
        git(repository, "commit", "-qm", "owned Git policy")
        base = git(repository, "rev-parse", "HEAD").decode().strip()
        (repository / REVIEW.BUNDLE / target_name).write_bytes(b"generated content\r\n")
        generated = receipt(repository)
        before = (
            generated["files"],
            policy.read_bytes(),
            "Preserve unrelated source\n",
            git(repository, "diff", "--cached", "--binary"),
            base,
        )
        output = tmp_path / "review"
        output.mkdir()
        return SimpleNamespace(
            root=repository,
            policy=policy,
            base=base,
            generated=generated,
            before=before,
            output=output,
        )

    return arrange


def preserved_state(case):
    return (
        receipt(case.root)["files"],
        case.policy.read_bytes(),
        (case.root / "README.md").read_text(),
        git(case.root, "diff", "--cached", "--binary"),
        git(case.root, "rev-parse", "HEAD").decode().strip(),
    )


def refusal_message(case):
    try:
        REVIEW.write_review(case.root, case.output, case.base, case.generated)
    except ValueError as error:
        return str(error)
    return None


def test_normalized_generated_bytes_are_refused(staged_review_case):
    # Arrange
    case = staged_review_case("normalized")
    # Act
    message = refusal_message(case)
    observed = (message, list(case.output.iterdir()), preserved_state(case))
    # Assert
    assert observed == (MESSAGE, [], case.before)


def test_ignored_generated_additions_are_refused(staged_review_case):
    # Arrange
    case = staged_review_case("ignored")
    # Act
    message = refusal_message(case)
    observed = (message, list(case.output.iterdir()), preserved_state(case))
    # Assert
    assert observed == (MESSAGE, [], case.before)


def test_binary_crlf_patch_replays_exactly(staged_review_case, tmp_path):
    # Arrange
    case = staged_review_case("binary")
    replay = tmp_path / "replay"
    # Act
    result = REVIEW.write_review(case.root, case.output, case.base, case.generated)
    git(case.root, "worktree", "add", "--detach", str(replay), case.base)
    git(replay, "apply", "--check", str(case.output / "bundle.patch"))
    git(replay, "apply", str(case.output / "bundle.patch"))
    observed = (
        receipt(replay)["files"],
        result["update_required"],
        result["patch_sha256"],
        json.loads((case.output / "manifest.json").read_text())["base_commit"],
        preserved_state(case),
    )
    expected_hash = hashlib.sha256(
        (case.output / "bundle.patch").read_bytes()
    ).hexdigest()
    # Assert
    assert observed == (
        case.generated["files"],
        True,
        expected_hash,
        case.base,
        case.before,
    )
