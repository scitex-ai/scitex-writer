#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# File: src/scitex_writer/_mcp/handlers/_update/_handler.py

"""Main update handler: orchestrates file sync with safety checks."""

import shutil
from pathlib import Path
from typing import Optional

from ...utils import resolve_project_path
from ._constants import PRESERVED_PATHS
from ._diff import backup_files, collect_sync_files, compare_files
from ._fossil import neutralise_fossil_changelog
from ._git_safety import (
    git_status_summary,
    has_uncommitted_changes,
    is_git_repo,
)
from ._source import find_package_root, read_version
from ._source_check import outdated_source_error, source_report

# Dedicated, compile-immutable vendor stamp. Read by check_version_freshness.py
# (writer compile gate) + scitex-dev's fleet stale-install audit. Do NOT reuse
# 00_shared/scitex_writer_version.tex (the compile rewrites that from the
# installed version for PDF metadata).
VENDOR_STAMP_PATH = "00_shared/.scitex-writer-vendored-version"


def _write_vendor_stamp(project_path: Path, pkg_version: str) -> None:
    """Stamp the version this tree was vendored FROM (best-effort)."""
    try:
        stamp = project_path / VENDOR_STAMP_PATH
        stamp.parent.mkdir(parents=True, exist_ok=True)
        stamp.write_text(
            f"{pkg_version}\n"
            f"# scitex-writer vendored-from version (written by update-project).\n"
            f"# The compile-time freshness gate compares this to the installed\n"
            f"# scitex-writer; re-vendor (scitex-writer update-project) when behind.\n",
            encoding="utf-8",
        )
    except OSError:
        pass


def _restamp_version_tex(project_path: Path, pkg_version: str) -> None:
    """Re-stamp 00_shared/scitex_writer_version.tex to the vendored version.

    The compile (_compile.py) rewrites this for PDF metadata, but only AT compile
    time -- so after a re-vendor the visible "Compiled by SciTeX Writer vX"
    colophon + PDF Creator would still show the OLD version until the next
    compile. Re-stamp it here so it is correct immediately. Best-effort.

    RENDERED BY :func:`version_stamp_tex`, the same function the compile path
    uses. The version here answers a DIFFERENT question from the compile's --
    "what was vendored into this workspace" rather than "what is running" -- so
    the value legitimately differs after a tag/branch update, but the FORMAT must
    not: this used to write both macros itself, which is how one PDF came to
    carry two claims that could drift apart (2026-08-18 card).
    """
    from .._version_truth import version_stamp_tex

    try:
        version_tex = project_path / "00_shared" / "scitex_writer_version.tex"
        if not version_tex.parent.exists():
            return
        version_tex.write_text(version_stamp_tex(pkg_version), encoding="utf-8")
    except OSError:
        pass


def update_project(
    project_dir: str,
    branch: Optional[str] = None,
    tag: Optional[str] = None,
    dry_run: bool = True,
    force: bool = False,
    allow_outdated: bool = False,
) -> dict:
    """Update engine files of an existing scitex-writer project.

    Syncs engine/template files (scripts, build scripts, base.tex, styles,
    Makefile) from the installed scitex-writer package to the project. The
    package's own src/ is never vendored in; user content is never modified.

    THE VENDOR SOURCE IS THE INSTALLED PACKAGE. Running this on an outdated
    scitex-writer vendors an outdated engine and reports success — the project
    then carries bugs the fleet has already fixed, with nothing to say so. When
    we can prove the source is stale we refuse and hand back the upgrade command;
    when PyPI is unreachable we proceed but say the check did not happen. Silence
    must never read as "you are current".

    Parameters
    ----------
    project_dir : str
        Path to the existing scitex-writer project.
    branch : str, optional
        Update from a specific template branch (triggers GitHub clone).
    tag : str, optional
        Update from a specific template tag (triggers GitHub clone).
    dry_run : bool
        If True, report what would change without touching any files.
    force : bool
        If True, skip the uncommitted-changes git safety check.
    allow_outdated : bool
        If True, vendor from an outdated installed package anyway. Off by
        default: a stale vendor is the bug, not an inconvenience.

    Returns
    -------
    dict
        success, source, modified, added, unchanged, backup_dir, dry_run,
        git_safe, warnings, message, source_version, latest_version,
        is_outdated, source_note, error (on failure)
    """
    try:
        project_path = resolve_project_path(project_dir)

        if not project_path.exists():
            return {"success": False, "error": f"Project not found: {project_path}"}

        if not (project_path / "00_shared").exists():
            return {
                "success": False,
                "error": (
                    f"{project_path} does not look like a scitex-writer project "
                    "(00_shared/ directory not found)."
                ),
            }

        # Git safety checks
        warnings: list[str] = []
        git_safe = True

        safety_error = _check_git_safety(
            project_path, project_dir, dry_run, force, warnings
        )
        if safety_error:
            return safety_error
        if warnings:
            git_safe = False

        # Resolve source template
        source_dir, is_temp = find_package_root(branch, tag)
        pkg_version = read_version(source_dir)

        # Only the INSTALLED package can be silently stale. An explicit
        # branch/tag is a deliberate choice, so we do not second-guess it.
        source_info = {}
        if not (branch or tag):
            source_info = source_report(pkg_version)
            if source_info.get("is_outdated") and not allow_outdated:
                if is_temp:
                    shutil.rmtree(str(source_dir.parent), ignore_errors=True)
                return {
                    "success": False,
                    "error": outdated_source_error(
                        pkg_version, source_info["latest_version"]
                    ),
                    **source_info,
                }

        try:
            source_files = collect_sync_files(source_dir, project_path)
            modified, added, unchanged = compare_files(source_files, project_path)

            backup_dir = None
            if not dry_run and (modified or added):
                backup_dir = _apply_updates(project_path, source_files, modified, added)
        finally:
            if is_temp:
                shutil.rmtree(str(source_dir.parent), ignore_errors=True)

        # Stamp the vendored-FROM version so the compile-time freshness gate
        # (check_version_freshness.py) and the fleet stale-install audit can
        # detect a stale vendored tree. Distinct from scitex_writer_version.tex
        # (which the compile rewrites from the installed version for PDF
        # metadata) -- this stamp is written ONLY here and reflects the version
        # update-project vendored from. Absent => a pre-feature vendor (stale).
        # The scaffolded engine CHANGELOG.md is in no sync list, so it freezes at
        # the version the project was created on and then keeps NAMING it -- a
        # second, lying answer to "what engine is this?" (a tree stamped 2.24.7
        # carried a changelog saying 2.9.0, and it was believed). Replace it with
        # a pointer to the real one; reported, never silent.
        fossil_neutralised = neutralise_fossil_changelog(
            project_path, pkg_version, dry_run=dry_run
        )

        if not dry_run:
            _write_vendor_stamp(project_path, pkg_version)
            # Also refresh the visible colophon / PDF-Creator stamp so it shows
            # the vendored version immediately (without waiting for a recompile).
            _restamp_version_tex(project_path, pkg_version)

        return {
            "success": True,
            "dry_run": dry_run,
            "fossil_changelog_neutralised": fossil_neutralised,
            "git_safe": git_safe,
            "warnings": warnings,
            "source": str(source_dir),
            "version": pkg_version,
            "modified": modified,
            "added": added,
            "unchanged": unchanged,
            "backup_dir": str(backup_dir) if backup_dir else None,
            # Legacy compatibility keys
            "updated_paths": modified + added,
            "skipped_paths": [],
            "missing_paths": [],
            "preserved_paths": [str(p) for p in PRESERVED_PATHS],
            # Which scitex-writer this tree was vendored FROM, and whether that
            # was the current one. Reported even on success: a caller must be
            # able to see the source without inferring it.
            **source_info,
            "message": _build_message(
                project_path, modified, added, unchanged, dry_run, backup_dir
            ),
        }

    except Exception as e:
        return {"success": False, "error": str(e)}


def _check_git_safety(
    project_path: Path,
    project_dir: str,
    dry_run: bool,
    force: bool,
    warnings: list[str],
) -> Optional[dict]:
    """Check git safety. Returns error dict or None if safe."""
    if is_git_repo(project_path):
        if not dry_run and not force and has_uncommitted_changes(project_path):
            status = git_status_summary(project_path)
            return {
                "success": False,
                "git_safe": False,
                "error": (
                    "Uncommitted changes detected in the project. "
                    "Commit or stash them first so you can revert if needed.\n\n"
                    f"  git -C {project_path} stash\n"
                    f"  scitex-writer update {project_dir}\n"
                    f"  git -C {project_path} stash pop\n\n"
                    f"Or pass --force / force=True to skip this check.\n\n"
                    f"Git status:\n{status}"
                ),
            }
    else:
        warnings.append(
            "Project is not a git repository. "
            "Cannot revert engine changes via git if something goes wrong."
        )
    return None


def _apply_updates(
    project_path: Path,
    source_files: dict[str, Path],
    modified: list[str],
    added: list[str],
) -> Optional[Path]:
    """Apply file updates with backup. Returns backup_dir or None."""
    backup_dir = None
    if modified:
        backup_dir = backup_files(project_path, modified)

    for rel in modified + added:
        src = source_files[rel]
        dst = project_path / rel
        dst.parent.mkdir(parents=True, exist_ok=True)
        if dst.exists():
            # A previous vendor may have set this engine file read-only
            # (see _set_engine_readonly). Restore the write bit before
            # overwriting so a re-vendor never fails on the second run --
            # this is what keeps update-project idempotent.
            dst.chmod(dst.stat().st_mode | 0o200)
        shutil.copy2(src, dst)

    # Ensure compile.sh is executable
    compile_sh = project_path / "compile.sh"
    if compile_sh.exists():
        compile_sh.chmod(compile_sh.stat().st_mode | 0o111)

    # Ensure scripts are executable
    scripts_dir = project_path / "scripts"
    if scripts_dir.is_dir():
        for script in scripts_dir.rglob("*.sh"):
            script.chmod(script.stat().st_mode | 0o111)

    # Make the freshly-vendored engine files read-only in the consumer
    # workspace so an accidental local edit fails loudly instead of being
    # silently lost on the next re-vendor. Done LAST so it sees the final
    # (post +x) mode bits. PRESERVED_PATHS (consumer-owned) files are never
    # in the sync set, so they are untouched and stay writable.
    _set_engine_readonly(project_path, modified + added)

    return backup_dir


def _set_engine_readonly(project_path: Path, written_rels: list[str]) -> None:
    """Set freshly-vendored engine files read-only in the CONSUMER workspace.

    Engine-vendored files are overwritten by every re-vendor, so a local edit
    is always lost -- worse, it silently masks the need to fix the file
    upstream in scitex-writer (the band-aid class of bug this guards against).
    Marking them read-only (r-x for executables, r-- otherwise) turns an
    accidental edit into an immediate, visible permission error, forcing the
    fix upstream. update-project clears the write bit again before re-writing
    (see _apply_updates), so this stays idempotent across repeated runs. Git
    only tracks the +x bit, so these perms live only in the consumer
    workspace, never in a commit. Best-effort: a chmod failure never aborts a
    vendor.
    """
    for rel in written_rels:
        dst = project_path / rel
        if not dst.is_file():
            continue
        try:
            executable = bool(dst.stat().st_mode & 0o111)
            dst.chmod(0o555 if executable else 0o444)
        except OSError:
            pass


def _build_message(
    project_path: Path,
    modified: list[str],
    added: list[str],
    unchanged: list[str],
    dry_run: bool,
    backup_dir: Optional[Path],
) -> str:
    """Build a human-readable summary message."""
    parts = []

    if dry_run:
        parts.append("Dry run -- no files modified.")
    else:
        total = len(modified) + len(added)
        if total:
            parts.append(f"Updated {total} file(s) in {project_path}.")
            if backup_dir:
                parts.append(f"Backup: {backup_dir}")
            parts.append(f"Review changes: git -C {project_path} diff")
        else:
            parts.append("Already up to date.")

    parts.append(
        f"{len(modified)} modified, {len(added)} new, {len(unchanged)} unchanged"
    )

    return "\n".join(parts)


# EOF
