#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# File: src/scitex_writer/_project/_engine.py

"""Install the writer engine into a workspace that already holds content.

A project template may ship its manuscript TEXT at the writer workspace
(``<project>/.scitex/writer/00_shared/title.tex``,
``.../01_manuscript/contents/results.tex``, ...) without the engine around it:
no ``scripts/``, no ``base.tex``, no styles. That is the right thing for a
template to ship — the engine belongs to the installed writer, the text to the
author — but :func:`scitex_writer.ensure_workspace` used to treat any
non-empty workspace as complete and return it unchanged. Writer then had a
workspace it could not compile, and a host that tested for the workspace saw
one that "existed".

This module completes such a workspace from the writer template:

* **Additive only.** A path that already exists in the workspace — file,
  directory or link — is never replaced. Running it again changes nothing the
  author wrote, which is what lets a host call it on every initialisation.
* **No demo media.** The template's example figures and tables
  (``<doc>/contents/{figures,tables}/caption_and_media/*``) are placeholders
  for an EMPTY project. A workspace that brings its own content gets the
  directories, not the examples, so they never appear in its PDF.
* **Never leaves the workspace.** Files are written with descriptor-relative,
  no-follow operations (:func:`scitex_writer.workspace_layout._write_under`);
  a template link is recreated only when it is relative and stays inside the
  workspace (the template's absolute ``00_shared/scholar/library`` link to the
  installing user's home is skipped). A workspace reached through a symlink is
  refused.
"""

from __future__ import annotations

import os
import shutil
import tempfile
from pathlib import Path, PurePosixPath
from typing import Optional

from ..workspace_layout import (
    SHELL_SCRIPTS_RELPATH,
    _open_or_make_dir,
    _vendored_script_mode,
    _write_under,
)

__all__ = [
    "CONTENT_MARKERS",
    "EngineInstallError",
    "has_engine",
    "holds_content",
    "install_engine",
    "install_engine_from_template",
]

#: Directories whose presence means a workspace already carries manuscript
#: content (a template-shipped manuscript, or an author's own).
CONTENT_MARKERS = ("00_shared", "01_manuscript")

#: Never copied from the template: VCS state, caches, build artefacts.
_SKIP_DIR_NAMES = frozenset(
    {
        ".git",
        "__pycache__",
        "node_modules",
        ".pytest_cache",
        ".ruff_cache",
        ".mypy_cache",
        "_sphinx_html",
        ".update_backup",
    }
)

#: Example media lives directly in these directories of each document.
_EXAMPLE_MEDIA_DIRS = (
    ("figures", "caption_and_media"),
    ("tables", "caption_and_media"),
)


class EngineInstallError(RuntimeError):
    """The engine could not be installed; names the workspace and the cause."""


def has_engine(workspace: Path) -> bool:
    """True when ``workspace`` carries the writer's compile scripts directory."""
    return (Path(workspace) / SHELL_SCRIPTS_RELPATH).is_dir()


def holds_content(workspace: Path) -> bool:
    """True when ``workspace`` already has manuscript content directories."""
    return any((Path(workspace) / name).is_dir() for name in CONTENT_MARKERS)


def _is_example_media(rel: PurePosixPath) -> bool:
    """``<doc>/contents/{figures,tables}/caption_and_media/<file>`` only.

    Subdirectories (``jpg_for_compilation/``) are scaffold the compile writes
    into, so they are kept.
    """
    parts = rel.parts
    if len(parts) != 5 or parts[1] != "contents":
        return False
    return (parts[2], parts[3]) in _EXAMPLE_MEDIA_DIRS


def _link_stays_inside(rel: PurePosixPath, target: str) -> bool:
    """A relative link whose lexical target is still inside the workspace."""
    if os.path.isabs(target):
        return False
    depth = 0
    for part in (*rel.parent.parts, *PurePosixPath(target).parts):
        if part == "..":
            depth -= 1
            if depth < 0:
                return False
        elif part not in ("", "."):
            depth += 1
    return True


def _link_under(root: Path, rel_parts: tuple, target: str) -> bool:
    """Create the link ``root/rel_parts -> target``; never replaces an entry.

    Parents are opened (or created) one component at a time with
    ``O_NOFOLLOW`` relative to an open descriptor, the same walk
    :func:`scitex_writer.workspace_layout._write_under` uses for files.
    """
    try:
        parent_fd = os.open(root, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
    except OSError:
        return False
    try:
        for part in rel_parts[:-1]:
            child = _open_or_make_dir(parent_fd, part)
            if child is None:
                return False
            os.close(parent_fd)
            parent_fd = child
        os.symlink(target, rel_parts[-1], dir_fd=parent_fd)
        return True
    except OSError:
        return False
    finally:
        os.close(parent_fd)


def _refuse_linked_workspace(workspace: Path) -> None:
    for linked in (workspace, workspace.parent):
        if linked.is_symlink():
            raise EngineInstallError(
                f"refusing to install the writer engine through a symlink: {linked} "
                f"-> {os.readlink(linked)}. Replace it with a real directory."
            )
    if not workspace.is_dir():
        raise EngineInstallError(f"workspace is not a directory: {workspace}")


def install_engine(workspace: Path, template_dir: Path) -> list[Path]:
    """Copy every template entry missing from ``workspace``; return those written.

    Parameters
    ----------
    workspace : pathlib.Path
        The writer workspace (``<project>/.scitex/writer``). Must be a real
        directory.
    template_dir : pathlib.Path
        A writer template tree (a clone of the scitex-writer repository).

    Returns
    -------
    list of pathlib.Path
        Workspace paths created, in walk order. Empty when nothing was missing.

    Raises
    ------
    EngineInstallError
        If the workspace is reached through a link, or an entry the template
        provides could not be written. Entries already written stay in place;
        a second call completes the rest.
    """
    workspace = Path(workspace)
    template_dir = Path(template_dir)
    _refuse_linked_workspace(workspace)
    if not template_dir.is_dir():
        raise EngineInstallError(f"writer template not found: {template_dir}")

    written: list[Path] = []
    failed: list[str] = []
    for current, dirnames, filenames in os.walk(template_dir, followlinks=False):
        here = Path(current)
        dirnames[:] = sorted(d for d in dirnames if d not in _SKIP_DIR_NAMES)
        for name in [*dirnames, *sorted(filenames)]:
            source = here / name
            rel = PurePosixPath(source.relative_to(template_dir).as_posix())
            destination = workspace / rel
            if os.path.lexists(destination):
                continue
            if source.is_symlink():
                target = os.readlink(source)
                if not _link_stays_inside(rel, target):
                    continue
                if source.is_dir():
                    # A linked directory is recreated as the link, not walked.
                    dirnames.remove(name)
                if _link_under(workspace, rel.parts, target):
                    written.append(destination)
                else:
                    failed.append(str(rel))
                continue
            if source.is_dir():
                continue  # created on demand by the files beneath it
            if _is_example_media(rel):
                continue
            try:
                payload = source.read_bytes()
            except OSError:
                failed.append(str(rel))
                continue
            if _write_under(
                workspace, rel.parts, payload, mode=_vendored_script_mode(source)
            ):
                written.append(destination)
            else:
                failed.append(str(rel))
    if failed:
        raise EngineInstallError(
            f"could not install {len(failed)} writer engine entr"
            f"{'y' if len(failed) == 1 else 'ies'} into {workspace}: "
            f"{', '.join(failed[:5])}{' ...' if len(failed) > 5 else ''}"
        )
    return written


def install_engine_from_template(
    workspace: Path,
    branch: Optional[str] = None,
    tag: Optional[str] = None,
) -> list[Path]:
    """Clone the writer template to a temporary directory and install from it.

    The clone is the same one a fresh workspace gets
    (:func:`scitex_writer._project._create.clone_writer_project`), so a
    completed workspace and a freshly created one compile against the same
    engine.
    """
    from ._create import clone_writer_project

    staging = Path(tempfile.mkdtemp(prefix="scitex-writer-engine-"))
    try:
        template = staging / "template"
        if not clone_writer_project(str(template), None, branch, tag):
            raise EngineInstallError(
                f"could not fetch the writer template to install the engine into "
                f"{workspace}; see the preceding git error"
            )
        return install_engine(Path(workspace), template)
    finally:
        shutil.rmtree(staging, ignore_errors=True)


# EOF
