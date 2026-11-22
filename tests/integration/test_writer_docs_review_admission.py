"""Real CLI refusal must preserve existing review evidence and caller state."""

import importlib.util
import os
import shutil
import subprocess
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

SPEC = importlib.util.spec_from_file_location(
    "writer_admission_fixtures",
    Path(__file__).with_name("test_writer_docs_review_artifact.py"),
)
FIXTURES = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(FIXTURES)
repository = FIXTURES.repository
git = FIXTURES.git
receipt = FIXTURES.receipt


def preserved_state(case):
    return (
        git(case.root, "status", "--porcelain"),
        git(case.root, "diff", "--cached", "--binary"),
        git(case.root, "rev-parse", "HEAD"),
        (case.root / "README.md").read_bytes(),
        receipt(case.root)["files"],
        case.canary.read_bytes(),
        os.path.lexists(case.output),
        case.output.is_symlink(),
        str(case.output.resolve()),
        sorted(x.name for x in case.target.iterdir()),
    )


@pytest.fixture(params=["checkout", "symlink", "nonempty"])
def refused_review_case(repository, tmp_path, request):
    scripts = repository / "scripts"
    scripts.mkdir()
    script = scripts / "prepare_docs_update.py"
    shutil.copyfile(FIXTURES.ROOT / "scripts/prepare_docs_update.py", script)
    git(repository, "add", "scripts")
    git(repository, "commit", "-qm", "actual review CLI")
    (repository / "README.md").write_text("Preserve caller staging\n")
    git(repository, "add", "README.md")
    target = tmp_path / "existing-review"
    target.mkdir()
    canary = target / "manifest.json"
    canary.write_bytes(b"\x00existing evidence\xff\n")
    outputs = {
        "checkout": repository / "review",
        "symlink": tmp_path / "linked-review",
        "nonempty": target,
    }
    messages = {
        "checkout": "Review output must be outside the checkout, without a symlink destination",
        "symlink": "Review output must be outside the checkout, without a symlink destination",
        "nonempty": "Review output must be new or empty; existing evidence is preserved",
    }
    output = outputs[request.param]
    if request.param == "symlink":
        output.symlink_to(target, target_is_directory=True)
    case = SimpleNamespace(
        root=repository,
        script=script,
        output=output,
        target=target,
        canary=canary,
        message=messages[request.param],
    )
    case.before = preserved_state(case)
    return case


def test_invalid_output_preserves_existing_evidence(refused_review_case):
    # Arrange
    case = refused_review_case
    # Act
    result = subprocess.run(
        [sys.executable, str(case.script), "--output", str(case.output)],
        cwd=case.root,
        capture_output=True,
        timeout=10,
    )
    observed = (result.returncode, result.stdout, result.stderr, preserved_state(case))
    # Assert
    assert observed == (1, b"", (case.message + "\n").encode(), case.before)
