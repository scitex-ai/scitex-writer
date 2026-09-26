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
from scitex_writer._cli.commands import project as project_module
from scitex_writer._cli.commands.project import refuse_reason


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
# the guard: what is refused, and what is normal
# ---------------------------------------------------------------------------
#
# These drive `refuse_reason` directly rather than the command, because the
# command's next step is a template clone and the guard is the part worth
# pinning. The end-to-end run is recorded on the PR (clean venv, published
# wheel): `create-project my-paper` on a path that does not exist yet creates
# the root and the workspace, measured, not assumed.


def test_a_path_that_does_not_exist_yet_is_not_a_refusal(tmp_path):
    # Arrange: `create-project my-paper` is the FIRST RUN, and it names a
    # directory that does not exist. The first published version of this verb
    # borrowed update-project's "Project not found" check and refused exactly
    # this case — the bug this test exists to keep out.
    missing = tmp_path / "my-paper"
    # Act
    reason = refuse_reason(missing, yes=False)
    # Assert
    assert reason is None


def test_an_empty_directory_is_not_a_refusal(tmp_path):
    # Arrange
    # Act
    reason = refuse_reason(tmp_path, yes=False)
    # Assert
    assert reason is None


def test_an_existing_workspace_is_not_a_refusal(tmp_path):
    # Arrange: an existing project is reported and left alone, not refused.
    _workspace_fixture(tmp_path)
    # Act
    reason = refuse_reason(tmp_path, yes=False)
    # Assert
    assert reason is None


def test_a_file_in_the_way_is_refused(tmp_path):
    # Arrange: a path that is a FILE cannot hold a workspace.
    target = tmp_path / "my-paper"
    target.write_text("not a directory\n")
    # Act
    reason = refuse_reason(target, yes=False)
    # Assert
    assert "not a directory" in (reason or "")


def test_a_directory_with_files_is_refused(tmp_path):
    # Arrange: additive or not, the verb does not silently write into a
    # directory that already holds someone's files (audit §2: mutating verbs do
    # not prompt — they refuse and name the flag).
    (tmp_path / "notes.txt").write_text("mine\n")
    # Act
    reason = refuse_reason(tmp_path, yes=False)
    # Assert
    assert reason is not None


def test_the_refusal_names_the_flag_that_proceeds(tmp_path):
    # Arrange: a refusal an agent cannot act on is a dead end.
    (tmp_path / "notes.txt").write_text("mine\n")
    # Act
    reason = refuse_reason(tmp_path, yes=False)
    # Assert
    assert "--yes" in (reason or "")


def test_yes_is_the_way_through_that_refusal(tmp_path):
    # Arrange
    (tmp_path / "notes.txt").write_text("mine\n")
    # Act
    reason = refuse_reason(tmp_path, yes=True)
    # Assert
    assert reason is None


def test_a_non_empty_directory_is_still_not_written_without_yes(tmp_path):
    # Arrange: the guard is wired, not merely available — the command must not
    # reach the clone for this case (which is also why this test needs no
    # network).
    (tmp_path / "notes.txt").write_text("mine\n")
    # Act
    code = main(["create-project", str(tmp_path)])
    # Assert
    assert code == 1


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



# ---------------------------------------------------------------------------
# adversarial: what a hostile or malformed target must NOT be able to do
# ---------------------------------------------------------------------------


def _victim_with_scripts(root: Path) -> Path:
    """A directory that is NOT the project, holding its own vendored scripts.

    This is the shape the escape actually damaged (another workspace, or any
    directory that happens to contain scripts/), and byte-identity is the
    assertion — so the exact contents matter more than their plausibility.
    """
    victim = root / "victim"
    (victim / "scripts" / "shell" / "modules").mkdir(parents=True)
    (victim / "scripts" / "README.md").write_text("victim readme\n")
    (victim / "scripts" / "shell" / "modules" / "check_dependancy_commands.sh").write_text(
        "VICTIM OWN CONTENT\n"
    )
    return victim


def _tree_bytes(root: Path) -> dict:
    return {
        str(p.relative_to(root)): p.read_bytes()
        for p in sorted(root.rglob("*"))
        if p.is_file()
    }


def _project_with_symlinked_workspace(tmp_path: Path, victim: Path) -> Path:
    project = tmp_path / "proj"
    (project / ".scitex").mkdir(parents=True)
    (project / ".scitex" / "writer").symlink_to(victim)
    return project


def test_a_symlinked_workspace_is_refused(tmp_path):
    # Arrange: before this guard, `.scitex/writer -> victim` was accepted, and
    # the vendored-script refresh wrote THROUGH the link — the victim's
    # check_dependancy_commands.sh hash went 5ed0d8a9… -> 796ca4da… and 158
    # files landed outside the project, with no --yes.
    project = _project_with_symlinked_workspace(tmp_path, _victim_with_scripts(tmp_path))
    # Act
    code = main(["create-project", str(project)])
    # Assert
    assert code == 1


def test_a_symlinked_workspace_leaves_the_victim_byte_identical(tmp_path, capsys):
    # Arrange
    victim = _victim_with_scripts(tmp_path)
    project = _project_with_symlinked_workspace(tmp_path, victim)
    before = _tree_bytes(victim)
    # Act
    main(["create-project", str(project)])
    capsys.readouterr()
    # Assert
    assert _tree_bytes(victim) == before


def test_a_symlinked_workspace_refusal_names_the_link(tmp_path, capsys):
    # Arrange: the message must say what to remove, or the operator is stuck.
    project = _project_with_symlinked_workspace(tmp_path, _victim_with_scripts(tmp_path))
    # Act
    main(["create-project", str(project)])
    # Assert
    assert "symlink" in capsys.readouterr().err


def test_a_symlinked_scitex_directory_is_refused(tmp_path):
    # Arrange: the PARENT link — `.scitex -> victim` — is the same escape one
    # level up, so it is refused by the same check.
    victim = _victim_with_scripts(tmp_path)
    project = tmp_path / "proj2"
    project.mkdir()
    (project / ".scitex").symlink_to(victim)
    # Act
    code = main(["create-project", str(project)])
    # Assert
    assert code == 1


def test_a_regular_file_workspace_is_refused(tmp_path):
    # Arrange: `<project>/.scitex/writer` as a regular FILE used to raise an
    # uncaught NotADirectoryError from `any(workspace.iterdir())`, which ran
    # before the guard.
    project = tmp_path / "proj3"
    (project / ".scitex").mkdir(parents=True)
    (project / ".scitex" / "writer").write_text("not a directory\n")
    # Act
    code = main(["create-project", str(project)])
    # Assert
    assert code == 1


def test_a_regular_file_workspace_reports_instead_of_tracing(tmp_path, capsys):
    # Arrange
    project = tmp_path / "proj4"
    (project / ".scitex").mkdir(parents=True)
    (project / ".scitex" / "writer").write_text("not a directory\n")
    # Act
    main(["create-project", str(project)])
    captured = capsys.readouterr()
    # Assert
    assert "Traceback" not in captured.out + captured.err


# ---------------------------------------------------------------------------
# delegation: the case refuse_reason alone cannot see
# ---------------------------------------------------------------------------


def _with_stubbed_ensure_workspace(stub):
    """Install a stub via DIRECT ATTRIBUTE ASSIGNMENT.

    PA-306 bans mock-shaped tests (the ``monkeypatch`` fixture), and this is the
    idiom scitex-dev itself uses instead: every caller in the command module
    resolves ``ensure_workspace`` from that module's globals at call time, so
    assigning the attribute IS the seam. The caller restores it in a finally.
    """
    saved = project_module.ensure_workspace
    project_module.ensure_workspace = stub
    return saved


def test_the_command_delegates_to_ensure_workspace_for_a_missing_target(tmp_path):
    # Arrange: THE case refuse_reason cannot cover — it says "proceed" for a
    # missing path, so if a `if not project_path.exists(): return 1` early
    # return were ever restored in the command body, the guard tests would all
    # still pass. Only a command-level run can tell.
    calls = []

    def _stub(project_dir, **kwargs):
        calls.append(Path(project_dir))
        return Path(project_dir) / ".scitex" / "writer"

    saved = _with_stubbed_ensure_workspace(_stub)
    try:
        # Act
        code = main(["create-project", str(tmp_path / "my-paper")])
    finally:
        project_module.ensure_workspace = saved
    # Assert
    assert (code, len(calls)) == (0, 1)


def test_the_delegated_target_is_the_path_the_user_gave(tmp_path):
    # Arrange
    calls = []

    def _stub(project_dir, **kwargs):
        calls.append(Path(project_dir))
        return Path(project_dir) / ".scitex" / "writer"

    saved = _with_stubbed_ensure_workspace(_stub)
    missing = tmp_path / "my-paper"
    try:
        # Act
        main(["create-project", str(missing)])
    finally:
        project_module.ensure_workspace = saved
    # Assert
    assert calls == [missing.resolve()]


# EOF
