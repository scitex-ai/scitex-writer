#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# File: src/scitex_writer/_cli/commands/project.py

"""update-project command (update engine files in a project)."""

from __future__ import annotations

import os
from pathlib import Path

import click

from ... import ensure_workspace
from ...workspace_layout import is_inside
from .._core import main_group
from .._helpers import _emit_json

# =========================================================================
# update (mutating top-level — needs object; keep `update` as alias via shim)
# =========================================================================


@main_group.command("update-project")
@click.argument("project", default=".", required=False)
@click.option("--branch", default=None, help="Pull from a specific template branch.")
@click.option("--tag", default=None, help="Pull from a specific template tag/version.")
@click.option(
    "--dry-run", is_flag=True, default=False, help="Preview only (this is the default)."
)
@click.option("--force", is_flag=True, default=False, help="Skip git safety check.")
@click.option(
    "--yes",
    "-y",
    is_flag=True,
    default=False,
    help="Apply the update (default is a safe preview).",
)
@click.option(
    "--allow-outdated",
    is_flag=True,
    default=False,
    help="Vendor from an outdated installed scitex-writer anyway (refused by default).",
)
@click.option("--json", "as_json", is_flag=True, default=False, help="Emit JSON.")
def update_project(project, branch, tag, dry_run, force, yes, allow_outdated, as_json):
    """Update engine files in a scitex-writer project, preserving user content.

    The engine is vendored from the INSTALLED scitex-writer. If that package is
    behind the latest release, this refuses rather than silently copying a stale
    engine and reporting success.

    \b
    Example:
        $ scitex-writer update-project
        $ scitex-writer update-project ~/proj/my-paper --dry-run
        $ scitex-writer update-project --tag v2.8.0
    """
    from ... import update

    project_path = Path(project).resolve()
    if not project_path.exists():
        click.echo(f"Error: Project not found: {project_path}", err=True)
        return 1
    # Safe by default: preview unless --yes is given (--dry-run forces preview).
    preview = dry_run or not yes
    result = update.project(
        str(project_path),
        branch=branch,
        tag=tag,
        dry_run=preview,
        force=force,
        allow_outdated=allow_outdated,
    )
    if as_json:
        _emit_json(result)
        return 0 if result.get("success") else 1
    if not result["success"]:
        click.echo(f"Error: {result['error']}", err=True)
        return 1
    for w in result.get("warnings", []):
        click.echo(f"Warning: {w}", err=True)
    mode = " (preview)" if preview else ""
    click.echo(f"\nSciTeX Writer Update{mode}")
    click.echo(f"Template version: {result.get('version', 'unknown')}")
    click.echo(f"Project: {project_path}\n")
    modified = result.get("modified", [])
    added = result.get("added", [])
    unchanged = result.get("unchanged", [])
    if modified or added:
        click.echo("Engine files drifted from the template:" if preview else "Updated:")
        for p in modified:
            click.echo(f"  M {p} (drifted)")
        for p in added:
            click.echo(f"  A {p} (missing)")
        click.echo()
    click.echo(
        f"  {len(modified)} drifted, {len(added)} missing, {len(unchanged)} in sync"
    )
    if result.get("backup_dir"):
        click.echo(f"\n  Backup: {result['backup_dir']}")
    if preview and (modified or added):
        click.echo(
            "\nPreview only — nothing changed. To apply (a timestamped backup is "
            f"made first):\n  scitex-writer update-project {project} --yes"
        )
    return 0


# =========================================================================
# create-project — the missing first step
# =========================================================================


def refuse_reason(project_path: Path, *, yes: bool) -> str | None:
    """Why ``create-project`` will not write here, or ``None`` to proceed.

    Pure and separate from the clone, because the guard is the part worth
    testing: a test that drove the real command would have to reach the network.

    A MISSING PATH IS NOT A REFUSAL. ``create-project my-paper`` is what a
    first-time user types, and it names a directory that does not exist yet —
    which is why the first published version of this verb was wrong to borrow
    ``update-project``'s "Project not found" check, whose target necessarily
    exists. ``ensure_workspace`` creates the root, the workspace and every
    parent, measured in a clean venv against the wheel.

    WHAT IS REFUSED, and why each one is a refusal rather than a note:

    * ``project_path`` is a FILE — there is nowhere to put a workspace.
    * ``.scitex`` or ``.scitex/writer`` is a SYMLINK. This one is a security
      boundary, not tidiness: ``ensure_workspace`` follows the link, and the
      vendored-script refresh then writes THROUGH it. Measured before this guard
      existed: a project with ``.scitex/writer -> /tmp/victim2`` and no ``--yes``
      reported "already present, nothing to do" while overwriting
      ``victim2/scripts/README.md`` and
      ``victim2/scripts/shell/modules/check_dependancy_commands.sh`` and copying
      158 files into a directory outside the project.
    * ``.scitex/writer`` exists as a NON-directory.
    * a resolved workspace that ESCAPES the project (belt and braces beside the
      symlink refusals: those make this unreachable today, and it is pinned by
      its own test so it stays true if they are ever relaxed).
    * a directory that already holds someone else's files, without ``--yes`` —
      additive or not, that is the caller's decision to make explicitly.
    """
    if project_path.exists() and not project_path.is_dir():
        return (
            f"Error: {project_path} exists and is not a directory.\n"
            "Nothing was created."
        )

    for linked in (project_path / ".scitex", project_path / ".scitex" / "writer"):
        if linked.is_symlink():
            return (
                f"Error: {linked} is a symlink to {os.readlink(linked)}.\n"
                "Nothing was created: a workspace reached through a link would let "
                "the vendored-script refresh write outside this project.\n"
                f"Replace it with a real directory and retry: rm {linked}"
            )

    workspace = project_path / ".scitex" / "writer"
    if workspace.exists() and not workspace.is_dir():
        return (
            f"Error: {workspace} exists and is not a directory.\n"
            "Nothing was created."
        )

    if workspace.is_dir():
        if not is_inside(workspace, project_path):
            return (
                f"Error: the workspace {workspace.resolve()} is outside "
                f"{project_path}.\nNothing was created."
            )
        return None  # an existing workspace is reported, never re-cloned

    if project_path.is_dir() and any(project_path.iterdir()) and not yes:
        return (
            f"Error: {project_path} is not empty and has no writer workspace.\n"
            "Nothing was created. To create the workspace here anyway:\n"
            f"  scitex-writer create-project {project_path} --yes"
        )
    return None


@main_group.command("create-project")
@click.argument("project", default=".", required=False)
@click.option(
    "--git-strategy",
    default="child",
    type=click.Choice(["child", "parent", "origin", "none"]),
    help="Git initialisation strategy (default: child).",
)
@click.option("--branch", default=None, help="Template branch to clone.")
@click.option("--tag", default=None, help="Template tag/version to clone.")
@click.option("--dry-run", is_flag=True, default=False, help="Preview only; nothing is created.")
@click.option(
    "--yes",
    "-y",
    is_flag=True,
    default=False,
    help="Do not ask before writing into a directory that already has files.",
)
@click.option("--json", "as_json", is_flag=True, default=False, help="Emit JSON.")
def create_project(project, git_strategy, branch, tag, dry_run, yes, as_json):
    """Create a scitex-writer project at PROJECT (default: the current dir).

    Creates ``{PROJECT}/.scitex/writer`` — the WORKSPACE — from the template the
    installed scitex-writer pins, and reports the path. That is the same call
    the Python API has always exposed (``scitex_writer.ensure_workspace``); it
    simply had no verb, so a first-time user's ``create-project``/``init``/
    ``new`` all answered "No such command" and the only documented way in was a
    Python import.

    \b
    WHERE YOUR PROJECT IS: the workspace lives at ``<project>/.scitex/writer``,
    not at the root. Both are accepted by the compile/editor entry points — a
    ROOT is resolved to its workspace — but this verb prints the workspace path
    so the two are never a guess.

    \b
    Idempotent: an existing workspace is reported and left alone (no re-clone,
    no network). It is NOT a scaffold of user content — ``01_manuscript`` and
    ``00_shared`` come from the template, and your edits to them are never
    touched by an update.

    \b
    Example:
        $ scitex-writer create-project ~/proj/my-paper
        $ scitex-writer create-project . --tag v2.43.4
        $ scitex-writer create-project . --json
    """
    project_path = Path(project).resolve()
    # The guard runs BEFORE anything reads the target: `any(workspace.iterdir())`
    # on a malformed target (`<project>/.scitex/writer` as a regular file) raised
    # an uncaught NotADirectoryError, and evaluating it first also meant the
    # symlink refusal below could be short-circuited by the ordering.
    refusal = refuse_reason(project_path, yes=yes)
    if refusal is not None:
        click.echo(refusal, err=True)
        return 1

    workspace = project_path / ".scitex" / "writer"
    existed = workspace.is_dir() and any(workspace.iterdir())

    # A dry run reports the plan and touches nothing — including no clone.
    if dry_run:
        if as_json:
            _emit_json(
                {
                    "success": True,
                    "dry_run": True,
                    "project": str(project_path),
                    "workspace": str(workspace),
                    "would_create": not existed,
                }
            )
        else:
            click.echo("\nSciTeX Writer Project (preview — nothing changed)")
            click.echo(f"Project root: {project_path}")
            click.echo(f"Workspace:    {workspace}")
            click.echo(
                "  Would create the workspace from the template."
                if not existed
                else "  Workspace already exists — nothing to create."
            )
        return 0

    try:
        resolved = ensure_workspace(
            project_path,
            git_strategy=git_strategy,
            branch=branch,
            tag=tag,
        )
    except Exception as exc:  # the clone is the failure surface (git, network, tag)
        if as_json:
            _emit_json(
                {
                    "success": False,
                    "project": str(project_path),
                    "workspace": str(workspace),
                    "error": str(exc),
                }
            )
        else:
            click.echo(f"Error: could not create the project: {exc}", err=True)
        return 1

    if as_json:
        _emit_json(
            {
                "success": True,
                "project": str(project_path),
                "workspace": str(resolved),
                "created": not existed,
            }
        )
        return 0

    click.echo(f"\nSciTeX Writer Project{' (already present)' if existed else ''}")
    click.echo(f"Project root: {project_path}")
    click.echo(f"Workspace:    {resolved}\n")
    if existed:
        click.echo("  Nothing to do — the workspace already exists.")
    else:
        click.echo("  Created. Next:")
        click.echo(f"    scitex-writer compile-manuscript {project_path}")
        click.echo(f"    scitex-writer gui serve {project_path}")
    return 0


# EOF


# EOF
