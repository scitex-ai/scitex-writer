#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# File: src/scitex_writer/workspace_layout.py

"""Where things live inside a writer project — the single source of truth.

A writer project has TWO roots and they are not the same directory::

    <project_dir>/                       the project root the user names
    <project_dir>/.scitex/writer/        the writer WORKSPACE

Everything writer owns — ``scripts/``, ``01_manuscript/``, ``config/`` — hangs
off the WORKSPACE. That one hidden segment is the whole content of this module,
and it exists because it was being re-typed.

WHY THIS MODULE EXISTS (measured 2026-08-17, prod). Full compilation was dead
for every user with::

    bash: /workspace/scripts/shell/compile_manuscript.sh: No such file or directory

The script was real; it was at ``/workspace/.scitex/writer/scripts/shell/``.
The caller had spelled the path out by hand because writer published nothing to
import — so writer's layout became a string literal in somebody else's
codebase, and drifted the moment it was written. Publishing the layout is the
fix; a second copy of the string anywhere is the bug.

So: **if you need a path inside a writer project, compose it from here.** Do
not join ``"scripts"`` and ``"shell"`` yourself, in this package or any other.
This module is public (no leading underscore) precisely so downstream packages
— scitex-hub among them — can import it instead of guessing.

NOTHING HERE GUESSES WHICH ROOT YOU HOLD. :func:`workspace_dir` always appends
the segment and :func:`compile_script_relpath` is always relative to the
workspace, so composing them twice by mistake produces an obviously wrong path
rather than a plausible one. An "accepts either root" helper was considered and
rejected: the scitex-writer repository is itself a workspace that ALSO contains
a ``.scitex/writer/`` directory, so no heuristic can tell the two roots apart
from the path alone, and one that appeared to would be wrong exactly where it
was trusted most.
"""

from __future__ import annotations

import hashlib
import shutil
from pathlib import Path
from typing import Optional, Union

__all__ = [
    "WORKSPACE_RELPATH",
    "SHELL_SCRIPTS_RELPATH",
    "COMPILE_SCRIPT_RELPATHS",
    "workspace_dir",
    "compile_script_relpath",
    "compile_script",
    "is_workspace",
    "resolve_workspace",
    "NotAWriterWorkspaceError",
    "package_scripts_dir",
    "vendored_script_sha256",
    "refresh_vendored_scripts",
    "is_inside",
]

PathLike = Union[str, Path]

WORKSPACE_RELPATH = Path(".scitex") / "writer"
"""The writer workspace, relative to the project root.

Mirrors what :func:`scitex_writer.ensure_workspace` creates. Hidden by the
dotfile convention, which is exactly why callers forget the segment exists.
"""

SHELL_SCRIPTS_RELPATH = Path("scripts") / "shell"
"""The compile scripts' directory, relative to the WORKSPACE."""

COMPILE_SCRIPT_RELPATHS = {
    doc_type: SHELL_SCRIPTS_RELPATH / f"compile_{doc_type}.sh"
    for doc_type in ("manuscript", "supplementary", "revision")
}
"""doc_type -> compile script, relative to the WORKSPACE.

Derived from one pattern rather than written out three times: three literal
entries are three chances to update two of them.
"""


def workspace_dir(project_dir: PathLike) -> Path:
    """The writer workspace inside a PROJECT ROOT.

    Always appends :data:`WORKSPACE_RELPATH`. Pass a project root; passing a
    workspace gives you a nested path that does not exist, which is the
    intended failure — see the module docstring on why this does not try to
    detect which root it was handed.

    Parameters
    ----------
    project_dir : str or pathlib.Path
        The project root.

    Returns
    -------
    pathlib.Path
        The workspace directory. Not created, and not required to exist.

    Examples
    --------
    >>> workspace_dir("/tmp/paper").as_posix()
    '/tmp/paper/.scitex/writer'
    """
    return Path(project_dir) / WORKSPACE_RELPATH


def compile_script_relpath(doc_type: str) -> Path:
    """The compile script for ``doc_type``, relative to the WORKSPACE.

    Relative on purpose: a caller that already holds the workspace — a
    container bind, a remote path, a URL prefix — needs the tail, not an
    absolute path computed against whichever root this module guessed.

    Parameters
    ----------
    doc_type : str
        One of ``manuscript``, ``supplementary``, ``revision``.

    Returns
    -------
    pathlib.Path
        e.g. ``scripts/shell/compile_manuscript.sh``.

    Raises
    ------
    ValueError
        If ``doc_type`` is not a known document type. Names the valid set,
        because the caller supplying a bad one cannot see this dict.

    Examples
    --------
    >>> compile_script_relpath("manuscript").as_posix()
    'scripts/shell/compile_manuscript.sh'

    An absolute path, from a project root:

    >>> (workspace_dir("/tmp/paper") / compile_script_relpath("manuscript")).as_posix()
    '/tmp/paper/.scitex/writer/scripts/shell/compile_manuscript.sh'
    """
    try:
        return COMPILE_SCRIPT_RELPATHS[doc_type]
    except KeyError:
        raise ValueError(
            f"unknown doc_type {doc_type!r}; "
            f"choose from {sorted(COMPILE_SCRIPT_RELPATHS)}"
        ) from None


def compile_script(project_root: PathLike, doc_type: str) -> Path:
    """The absolute compile script path for ``doc_type`` inside a PROJECT ROOT.

    The one call a caller outside this package should need: hand it the
    directory the user named, get back the script to run. Nothing about
    ``.scitex/writer`` or ``scripts/shell`` has to be known — or re-typed —
    anywhere else. That re-typing is what killed full compilation for every
    user in 2026-08.

    This COMPOSES the two halves above; it does not inspect anything. A
    workspace passed here yields a nested path that does not exist, which is
    the intended failure — see the module docstring on why nothing here tries
    to detect which root it was handed.

    The returned path is NOT checked for existence. A caller about to execute
    it should say so loudly when it is missing, naming both the path and the
    root it was derived from: ``bash: … No such file or directory`` names the
    symptom and hides which of the two roots the caller was holding, and that
    is precisely how the original defect read in production.

    Parameters
    ----------
    project_root : str or pathlib.Path
        The project root — the directory the user names, NOT the workspace.
    doc_type : str
        One of ``manuscript``, ``supplementary``, ``revision``.

    Returns
    -------
    pathlib.Path
        Absolute path to the compile script.

    Raises
    ------
    ValueError
        If ``doc_type`` is not a known document type.

    Examples
    --------
    >>> compile_script("/workspace", "manuscript").as_posix()
    '/workspace/.scitex/writer/scripts/shell/compile_manuscript.sh'
    """
    return workspace_dir(project_root) / compile_script_relpath(doc_type)


def is_workspace(path: PathLike) -> bool:
    """Heuristic: does ``path`` look like a writer WORKSPACE rather than a
    PROJECT ROOT?

    A workspace is the directory that directly contains ``00_shared/``, or
    whose path tail equals ``WORKSPACE_RELPATH`` (``.scitex/writer``). This is
    intentionally a *hint* for tolerance, not a root detector: the module
    docstring explains why no path-only rule can tell the two roots apart
    with certainty (this repo is itself a workspace that also contains a
    ``.scitex/writer``). Callers that must be exact should compare against
    :func:`workspace_dir` of the root they hold.
    """
    p = Path(path)
    if (p / "00_shared").is_dir():
        return True
    return p.name == WORKSPACE_RELPATH.name and p.parent.name == WORKSPACE_RELPATH.parts[0]


def resolve_workspace(project_dir: PathLike) -> Path:
    """Return the writer WORKSPACE for the project a caller named.

    The contract (scitex-hub leaf-v2 mount, 2026-09-14): the hub hands every
    leaf the PROJECT ROOT; the leaf owns root→workspace. This is the single
    entry the leaf uses to turn "whatever root-ish path I was given" into the
    workspace, tolerant of both spellings:

    * given a PROJECT ROOT  → return :func:`workspace_dir` of it;
    * given the WORKSPACE   → return it as is (has ``00_shared/``, or its tail
      is ``.scitex/writer``);
    * given a directory that is neither (no workspace, no ``00_shared/``) →
      raise :class:`NotAWriterWorkspaceError` naming BOTH the path given and
      the workspace that would be expected under it — never a bare
      ``FileNotFoundError`` downstream (the 2026-08/2026-09 defect class).
    """
    base = Path(project_dir)
    if is_workspace(base):
        return base
    candidate = workspace_dir(base)
    if candidate.exists() or (base / WORKSPACE_RELPATH).exists():
        return candidate
    if base.exists():
        raise NotAWriterWorkspaceError(
            f"{base} is not a scitex-writer project: no .scitex/writer workspace "
            f"under it and no 00_shared/ in it. Expected the writer workspace at "
            f"{candidate} (run `scitex-writer init` / ensure_workspace first), "
            f"or pass that directory directly."
        )
    # base itself does not exist at all — let the caller's existence check /
    # this error name the missing path.
    raise NotAWriterWorkspaceError(
        f"path does not exist: {base}. If it is a project root, its writer "
        f"workspace would be at {candidate}."
    )


class NotAWriterWorkspaceError(ValueError):
    """Raised when a path is neither a project root with a workspace nor a
    workspace itself. Carries a message naming both the given path and the
    expected workspace, so the failure reads as a root-vs-workspace
    explanation rather than a bare ``FileNotFoundError``."""


# ---------------------------------------------------------------------------
# Vendored-scripts refresh: keep a workspace's package-owned scripts/ in step
# with the INSTALLED package. A workspace is a full clone of the template, so
# it carries its own scripts/shell/... which would otherwise stay stale forever
# (2026-09-14 hub live repro: workspace check_dependancy_commands.sh = old hash
# c78358d5 while the installed package carried the new conditional check
# 796ca4da). The refresh overwrites those scripts from the installed package.
# ---------------------------------------------------------------------------


def package_scripts_dir() -> Optional[Path]:
    """The installed package's canonical ``scripts/`` directory (or ``None``).

    Resolves for both install modes:

    * wheel  — ``pyproject`` force-includes the repo ``scripts/`` as
      ``scitex_writer/scripts``, so ``<package>/scripts`` exists;
    * editable — the package lives in the repo, so the repo-root ``scripts/``
      (``<package>.parent.parent/scripts``) exists.

    The hub's dev container is an editable install, so refresh is effective
    there immediately without a rebuild; a wheel install picks it up once the
    force-include is in the released wheel.
    """
    import scitex_writer

    pkg = Path(scitex_writer.__file__).resolve().parent
    candidates = [pkg / "scripts", pkg.parents[1] / "scripts"]
    for candidate in candidates:
        try:
            if (candidate / "shell").is_dir():
                return candidate
        except OSError:
            continue
    return None


def _sha256(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


def vendored_script_sha256(workspace: Path, relpath: str) -> Optional[str]:
    """sha256 of a workspace's vendored script at ``relpath`` (or ``None``)."""
    f = Path(workspace) / "scripts" / relpath
    if not f.is_file():
        return None
    return _sha256(f)


_SCRIPTS_SENTINEL = ".scitex_writer_scripts_version"
_SCRIPTS_KEY_FILE = "shell/modules/check_dependancy_commands.sh"


def _source_sentinel_hash(scripts_dir: Path) -> str:
    """Content hash identifying the installed package's ``scripts/``.

    Hashes the key file (``check_dependancy_commands.sh``) when present — the
    exact file the 2026-09-14 hub repro showed going stale — falling back to an
    aggregate over the whole tree if the key file is renamed/absent, so the
    sentinel is always stable and content-dependent. Deliberately NOT the
    installed ``__version__``: the hub's editable dev container reports a stale
    version (2.43.0) even at current code, so a version marker would never fire
    for a script change that didn't bump the version.
    """
    key = scripts_dir / _SCRIPTS_KEY_FILE
    if key.is_file():
        return _sha256(key)
    h = hashlib.sha256()
    for p in sorted(f for f in scripts_dir.rglob("*") if f.is_file()):
        h.update(str(p.relative_to(scripts_dir)).encode("utf-8"))
        h.update(b"\0")
        h.update(_sha256(p).encode("ascii"))
        h.update(b"\0")
    return h.hexdigest()


def is_inside(child: PathLike, parent: PathLike) -> bool:
    """True when ``child`` is ``parent`` or lives under it, AFTER resolution.

    The containment predicate for every write this package performs inside
    somebody else's project. Resolution is the point: a plain textual prefix
    check would accept ``<parent>/../elsewhere`` and a link to anywhere, which
    is exactly the shape that let a symlinked workspace redirect the
    vendored-script refresh out of the project (2026-09-17 review finding).

    Lives here rather than beside its callers because ``workspace_layout`` owns
    what a workspace path MEANS; callers that write use this instead of
    re-deriving it.
    """
    child_path, parent_path = Path(child).resolve(), Path(parent).resolve()
    return child_path == parent_path or parent_path in child_path.parents


def refresh_vendored_scripts(
    workspace: Path,
    scripts_dir: Optional[Path] = None,
) -> list[Path]:
    """Overwrite a workspace's package-owned ``scripts/`` from the installed
    package, gated on the scripts' content hash. Idempotent.

    Fast path: a marker file (``<workspace>/scripts/.scitex_writer_scripts_
    version``) stores the content hash the workspace was last synced against.
    If it equals :func:`_source_sentinel_hash` of the installed scripts, the
    workspace is in step and nothing is touched. On a mismatch — a fresh
    workspace, a script change, or an OLD marker (a version string from the
    pre-hash gate) — every installed ``scripts/`` file is hash-compared against
    its workspace copy and the missing/differing ones overwritten; the marker
    is then set to the new content hash.

    Gating on the content hash (not ``__version__``) makes this robust to a
    stale version readout: the hub's editable dev container reports
    ``__version__`` 2.43.0 even at current code, so a version marker could
    never detect a script that changed without a version bump.

    Only ``<workspace>/scripts/...`` is read or written — the user's
    ``01_manuscript/`` and ``00_shared/`` content is never touched. Returns the
    list of files written (empty when already in sync).

    Parameters
    ----------
    workspace:
        The writer workspace (the dir that contains ``scripts/``,
        ``00_shared/``, ``compile.sh``, ...).
    scripts_dir:
        Explicit source ``scripts/`` dir. Defaults to
        :func:`package_scripts_dir` (the installed package). Injectable so
        tests can point at a fixture without touching the real package.
    """
    if scripts_dir is None:
        scripts_dir = package_scripts_dir()
    if scripts_dir is None:
        return []
    scripts_dir = Path(scripts_dir)
    ws_scripts = Path(workspace) / "scripts"
    if not ws_scripts.is_dir():
        return []

    # NEVER WRITE OUTSIDE THE WORKSPACE, and never THROUGH a link to get there.
    # The caller's authority covers the workspace it named, not wherever a link
    # points: measured before this guard, a project whose `.scitex/writer` was a
    # symlink to a victim directory had the whole vendored tree copied into the
    # victim (158 files) and two of its files overwritten, while the verb
    # reported "already present, nothing to do". Declining is a no-op refresh —
    # the safe direction, since the compile then runs with whatever the
    # workspace already has, exactly as it did before this refresh existed.
    ws_root = Path(workspace).resolve()
    if Path(workspace).is_symlink() or ws_scripts.is_symlink():
        return []

    sentinel = _source_sentinel_hash(scripts_dir)
    marker = ws_scripts / _SCRIPTS_SENTINEL
    if marker.is_file() and marker.read_text().strip() == sentinel:
        return []

    written: list[Path] = []
    for src_file in sorted(p for p in scripts_dir.rglob("*") if p.is_file()):
        rel = src_file.relative_to(scripts_dir)
        dst_file = ws_scripts / rel
        # A symlinked DIRECTORY inside scripts/ (or a symlinked file) would
        # redirect this write wherever it points, so containment is enforced per
        # destination rather than only at the workspace boundary.
        if not is_inside(dst_file.parent.resolve(), ws_root):
            continue
        if dst_file.is_symlink():
            continue
        src_hash = _sha256(src_file)
        if not dst_file.is_file() or _sha256(dst_file) != src_hash:
            dst_file.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(src_file, dst_file)
            written.append(dst_file)
    if is_inside(marker.parent.resolve(), ws_root):
        marker.parent.mkdir(parents=True, exist_ok=True)
        marker.write_text(sentinel + "\n")
    return written


# EOF
