"""create-project and update-project: the two project verbs.

create-project carries the tests for blocker #1 of card
``scitex-writer-standalone-readiness-measured-blockers-20260902``: measured
against a clean venv, every name a first-time user guesses (create-project /
init / new / create / init-project) answered "No such command", the usage guide
told the reader to ``git clone`` a personal repo by hand, and the only creation
path was the Python API. These drive the real CLI entry point
(`scitex_writer._cli.main` — the console script's own callable, whose RETURN
VALUE is the exit code) and never touch the network: an existing workspace is
the case that must not re-clone.
"""

import importlib
import json
from pathlib import Path



from scitex_writer._cli import main



def test_module_exposes_update_project():
    # Arrange
    # Act
    module = importlib.import_module("scitex_writer._cli.commands.project")
    # Assert
    assert hasattr(module, "update_project")


def test_module_exposes_create_project():
    # Arrange
    # Act
    module = importlib.import_module("scitex_writer._cli.commands.project")
    # Assert
    assert hasattr(module, "create_project")


_PACKAGE = Path(__file__).resolve().parents[4] / "src" / "scitex_writer"
_PROJECT_COMMAND = _PACKAGE / "_cli" / "commands" / "project.py"
_USAGE = _PACKAGE / "_usage.py"


def _workspace_fixture(root: Path) -> Path:
    """An EXISTING workspace — enough for ensure_workspace's early return."""
    workspace = root / ".scitex" / "writer"
    (workspace / "00_shared").mkdir(parents=True)
    (workspace / "01_manuscript" / "contents").mkdir(parents=True)
    (workspace / "scripts" / "shell" / "modules").mkdir(parents=True)
    (workspace / "scripts" / "shell" / "modules" / "check_dependancy_commands.sh").write_text(
        "#!/bin/bash\n"
    )
    (workspace / "compile.sh").write_text("#!/bin/bash\nexit 0\n")
    return workspace


# ---------------------------------------------------------------------------
# it is findable
# ---------------------------------------------------------------------------


def test_the_verb_is_listed_at_the_top_level(capsys):
    # Arrange
    # Act
    main(["--help"])
    # Assert
    assert "create-project" in capsys.readouterr().out


def test_the_usage_guide_names_the_verb(capsys):
    # Arrange: the guide used to send a first-time user to `git clone` of a
    # personal repo and mentioned project creation nowhere.
    # Act
    main(["show-usage"])
    # Assert
    assert "create-project" in capsys.readouterr().out


def test_the_usage_guide_no_longer_points_at_the_personal_repo(capsys):
    # Arrange: the same repo the template-source fix stopped cloning from.
    # Act
    main(["show-usage"])
    # Assert
    assert "ywatanabe1989/scitex-writer" not in capsys.readouterr().out


# ---------------------------------------------------------------------------
# it fails honestly
# ---------------------------------------------------------------------------


def test_a_missing_directory_fails(tmp_path):
    # Arrange: the exit code is the console script's own contract.
    missing = tmp_path / "not-here"
    # Act
    code = main(["create-project", str(missing)])
    # Assert
    assert code == 1


def test_a_missing_directory_says_what_was_not_found(tmp_path, capsys):
    # Arrange
    missing = tmp_path / "not-here"
    # Act
    main(["create-project", str(missing)])
    # Assert
    assert str(missing) in capsys.readouterr().err


# ---------------------------------------------------------------------------
# an existing project: report it, do not re-clone
# ---------------------------------------------------------------------------


def test_an_existing_workspace_succeeds(tmp_path, capsys):
    # Arrange
    _workspace_fixture(tmp_path)
    # Act
    code = main(["create-project", str(tmp_path)])
    # Assert
    assert code == 0


def test_an_existing_workspace_reports_its_path(tmp_path, capsys):
    # Arrange: the path the user must edit and compile in — the workspace, not
    # the root. Printing it is what stops the two being a guess.
    workspace = _workspace_fixture(tmp_path)
    # Act
    main(["create-project", str(tmp_path)])
    # Assert
    assert str(workspace) in capsys.readouterr().out


def test_an_existing_workspace_is_left_alone(tmp_path, capsys):
    # Arrange
    _workspace_fixture(tmp_path)
    # Act
    main(["create-project", str(tmp_path)])
    # Assert
    assert "already" in capsys.readouterr().out


def test_an_existing_workspace_is_not_re_cloned(tmp_path):
    # Arrange: a clone would leave a .git behind; nothing may touch the network
    # here, so this also pins that the fast path needs none.
    workspace = _workspace_fixture(tmp_path)
    # Act
    main(["create-project", str(tmp_path)])
    # Assert
    assert not (workspace / ".git").exists()


def test_json_reports_an_existing_workspace_as_not_created(tmp_path, capsys):
    # Arrange
    _workspace_fixture(tmp_path)
    # Act
    main(["create-project", str(tmp_path), "--json"])
    # Assert
    assert json.loads(capsys.readouterr().out)["created"] is False


def test_json_reports_the_resolved_workspace(tmp_path, capsys):
    # Arrange
    workspace = _workspace_fixture(tmp_path)
    # Act
    main(["create-project", str(tmp_path), "--json"])
    # Assert
    assert json.loads(capsys.readouterr().out)["workspace"] == str(workspace)


# ---------------------------------------------------------------------------
# a mutating verb previews, and asks before writing into someone's directory
# ---------------------------------------------------------------------------


def test_dry_run_says_it_is_a_preview(tmp_path, capsys):
    # Arrange: fleet CLI convention — every mutating verb previews on demand.
    _workspace_fixture(tmp_path)
    # Act
    main(["create-project", str(tmp_path), "--dry-run"])
    # Assert
    assert "preview" in capsys.readouterr().out


def test_dry_run_creates_nothing(tmp_path, capsys):
    # Arrange: an EMPTY directory — no workspace yet, so a real run would clone.
    # The dry run must not, and must not call the network either.
    # Act
    main(["create-project", str(tmp_path), "--dry-run"])
    capsys.readouterr()
    # Assert
    assert not (tmp_path / ".scitex").exists()


def test_dry_run_reports_whether_it_would_create(tmp_path, capsys):
    # Arrange
    # Act
    main(["create-project", str(tmp_path), "--dry-run", "--json"])
    # Assert
    assert json.loads(capsys.readouterr().out)["would_create"] is True


def test_a_directory_with_files_refuses_without_yes(tmp_path):
    # Arrange: additive or not, the verb does not silently write into a
    # directory that already holds someone's files (audit §2: mutating verbs do
    # not prompt — they refuse and name the flag).
    (tmp_path / "notes.txt").write_text("mine\n")
    # Act
    code = main(["create-project", str(tmp_path)])
    # Assert
    assert code == 1


def test_a_directory_with_files_creates_nothing_when_it_refuses(tmp_path, capsys):
    # Arrange
    (tmp_path / "notes.txt").write_text("mine\n")
    # Act
    main(["create-project", str(tmp_path)])
    capsys.readouterr()
    # Assert
    assert not (tmp_path / ".scitex").exists()


def test_the_refusal_names_the_flag_that_proceeds(tmp_path, capsys):
    # Arrange: a refusal an agent cannot act on is a dead end.
    (tmp_path / "notes.txt").write_text("mine\n")
    # Act
    main(["create-project", str(tmp_path)])
    # Assert
    assert "--yes" in capsys.readouterr().err


# ---------------------------------------------------------------------------
# one creation path, not two
# ---------------------------------------------------------------------------


def test_the_verb_delegates_to_the_public_api():
    # Arrange: the card's finding was that ensure_workspace was the ONLY path.
    # A verb that grew its own clone would be a second implementation of the
    # same act — the drift class this repo keeps paying for.
    source = _PROJECT_COMMAND.read_text(encoding="utf-8")
    # Act
    body = source[source.index('@main_group.command("create-project")') :]
    # Assert
    assert "ensure_workspace(" in body


def test_the_verb_does_not_shell_out_to_git():
    # Arrange
    source = _PROJECT_COMMAND.read_text(encoding="utf-8")
    # Act
    body = source[source.index('@main_group.command("create-project")') :]
    # Assert
    assert "subprocess" not in body and "git clone" not in body



# EOF
