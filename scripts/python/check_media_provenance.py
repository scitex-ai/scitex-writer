#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# ROLE: engine-vendored — DO NOT edit here. `scitex-writer update-project`
# overwrites this file on every re-vendor; fix it upstream in the
# scitex-writer package instead (local edits are lost, and update-project
# may set it read-only in the consumer workspace after vendoring).
# File: scripts/python/check_media_provenance.py
# Purpose: Verify that media artifacts committed to a manuscript are SYMLINKS
#          (and, in strict mode, that they resolve under the project's
#          `scripts/`) -- i.e. the paper is chained to the code that produced
#          it, rather than holding loose, un-provenanced copies.
#
#          A scitex-writer project keeps rendered media under
#            <doc>/contents/figures/caption_and_media/   (image/pdf/tif/svg)
#            <doc>/contents/tables/caption_and_media/     (.csv)
#          Caption `.tex` files (and `.md/.yaml/.yml/.json` sidecars, incl.
#          figrecipe recipe yamls) are NOT media and are ignored.
#
#          This is a PRIVATE convention -- DISABLED (off) by default, so the
#          public package never errors-by-default. Severity is a user-level
#          knob with three levels:
#            off    -- check disabled, zero noise (DEFAULT)
#            warn   -- report non-symlink media as a warning (exit 0)
#            error  -- report non-symlink media as an error (exit 1)
#
#          Two modes (the whole check is off by default):
#            basic  -- a media file must be a symlink.
#            strict -- the symlink must additionally resolve to a path UNDER
#                      the project `scripts/` dir (require_under_scripts).
#
#          Severity precedence (highest -> lowest), mirroring the package's
#          documented config precedence:
#            1. --level {off,warn,error} CLI flag
#            2. env SCITEX_WRITER_MEDIA_PROVENANCE
#            3. project ./config.yaml key media_provenance.level
#            4. user-wide ~/.scitex/writer/config.yaml key media_provenance.level
#            5. default off
#          require_under_scripts precedence (CLI only ever tightens):
#            1. --require-under-scripts CLI flag (presence => true)
#            2. project ./config.yaml key media_provenance.require_under_scripts
#            3. user ~/.scitex/writer/config.yaml media_provenance.require_under_scripts
#            4. default false
#
# Usage:
#   python check_media_provenance.py [project_dir]
#                                    [--doc-type manuscript|supplementary|revision|all]
#                                    [--level off|warn|error]
#                                    [--require-under-scripts]
#
# Self-contained: stdlib + optional PyYAML (only needed to read config files).

import argparse
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from _severity import resolve_level  # noqa: E402

# ANSI colors (match check_paper_symlink.py / check_overflow.py)
GREEN = "\033[0;32m"
YELLOW = "\033[1;33m"
RED = "\033[0;31m"
DIM = "\033[0;90m"
BOLD = "\033[1m"
NC = "\033[0m"

PASS_COUNT = 0
WARN_COUNT = 0
FAIL_COUNT = 0

_LEVELS = ("off", "warn", "error")

_DOC_DIRS = {
    "manuscript": "01_manuscript",
    "supplementary": "02_supplementary",
    "revision": "03_revision",
}

# Rendered artifacts that must be symlinked, by media area.
_FIGURE_MEDIA_EXTS = {".jpg", ".jpeg", ".png", ".pdf", ".tif", ".tiff", ".svg"}
_TABLE_MEDIA_EXTS = {".csv"}

# How many offending paths to print before truncating.
_MAX_LIST = 50


def log_pass(msg):
    global PASS_COUNT
    print(f"  {GREEN}[PASS]{NC} {msg}")
    PASS_COUNT += 1


def log_warn(msg):
    global WARN_COUNT
    print(f"  {YELLOW}[WARN]{NC} {msg}")
    WARN_COUNT += 1


def log_fail(msg):
    global FAIL_COUNT
    print(f"  {RED}[FAIL]{NC} {msg}")
    FAIL_COUNT += 1


def log_detail(msg):
    print(f"    {DIM}{msg}{NC}")


def _read_block(config_path):
    """Read the ``media_provenance`` mapping from a YAML config, or ``{}``.

    A missing file/key is simply ``{}`` (not an error). PyYAML is optional --
    if it is absent we silently skip config files (env + CLI still work).
    """
    if not config_path.exists():
        return {}
    try:
        import yaml
    except ImportError:
        return {}
    try:
        data = yaml.safe_load(config_path.read_text(encoding="utf-8")) or {}
    except Exception:
        return {}
    if not isinstance(data, dict):
        return {}
    block = data.get("media_provenance")
    return block if isinstance(block, dict) else {}


def _config_blocks(project_dir):
    """Return (project_block, user_block) media_provenance mappings."""
    proj = _read_block(Path(project_dir) / "config.yaml")
    user = _read_block(Path.home() / ".scitex" / "writer" / "config.yaml")
    return proj, user


def resolve_require_under_scripts(cli_flag, proj_block, user_block):
    """Resolve require_under_scripts. The CLI flag only ever tightens (true)."""
    if cli_flag:
        return True
    for block in (proj_block, user_block):
        val = block.get("require_under_scripts")
        if isinstance(val, bool):
            return val
    return False


def _iter_media_files(project_dir, doc_types):
    """Yield (path, area) for every rendered-media file under the selected docs.

    ``area`` is "figures" or "tables". Walks
    ``<doc>/contents/{figures,tables}/caption_and_media/`` recursively;
    selects files by extension so caption ``.tex`` and ``.md/.yaml/.yml/.json``
    sidecars are skipped. Symlinked directories are not followed (os.walk
    default) so a symlinked media file is still yielded as a file.
    """
    areas = (("figures", _FIGURE_MEDIA_EXTS), ("tables", _TABLE_MEDIA_EXTS))
    for doc_type in doc_types:
        doc_dir = project_dir / _DOC_DIRS[doc_type]
        for area, exts in areas:
            media_dir = doc_dir / "contents" / area / "caption_and_media"
            if not media_dir.is_dir():
                continue
            for root, _dirs, files in os.walk(media_dir):
                for name in files:
                    p = Path(root) / name
                    if p.suffix.lower() in exts:
                        yield p, area


def _scripts_dirs(project_dir):
    """The ``scripts/`` dirs media may resolve under (issue #505).

    Same roots as ``_claim_paths._claim_path_roots``: the project dir, the
    research repo above a VENDORED ``<repo>/.scitex/writer`` workspace, and
    the enclosing git root. In a vendored layout the research code lives in
    ``<repo>/scripts``, not in the workspace's own ``scripts/``.
    """
    roots = [project_dir]
    for parent in project_dir.parents:
        if parent.name == ".scitex":
            roots.append(parent.parent)
            break
    for parent in (project_dir, *project_dir.parents):
        if (parent / ".git").exists():
            if parent not in roots:
                roots.append(parent)
            break
    return [(root / "scripts").resolve() for root in roots]


def _resolves_under(path, scripts_dirs):
    """True if the symlink ``path`` resolves under one of ``scripts_dirs``."""
    try:
        target = Path(os.path.realpath(path))
    except OSError:
        return False
    return any(target.is_relative_to(d) for d in scripts_dirs)


def main():
    parser = argparse.ArgumentParser(
        description="Verify manuscript media are symlinks (chained to the code "
        "that produced them). Private convention -- disabled (off) by default."
    )
    parser.add_argument("project_dir", nargs="?", default=".")
    parser.add_argument(
        "--doc-type",
        choices=[*_DOC_DIRS, "all"],
        default="all",
        help="Which document(s) to scan (default: all present).",
    )
    parser.add_argument(
        "--level",
        choices=list(_LEVELS),
        default=None,
        help="Severity: off (default), warn, or error. Overrides env and config.",
    )
    parser.add_argument(
        "--require-under-scripts",
        action="store_true",
        help="Strict mode: each media symlink must resolve UNDER the project "
        "scripts/ dir, not merely be a symlink.",
    )
    args = parser.parse_args()

    project_dir = Path(args.project_dir).resolve()
    proj_block, user_block = _config_blocks(project_dir)
    level = resolve_level(
        "media_provenance",
        args.level,
        project_dir,
        default="off",
        env_var="SCITEX_WRITER_MEDIA_PROVENANCE",
    )
    require_under_scripts = resolve_require_under_scripts(
        args.require_under_scripts, proj_block, user_block
    )

    mode = "strict" if require_under_scripts else "basic"
    print(f"\n{BOLD}=== Media Provenance Check (level={level}, {mode}) ==={NC}\n")

    if level == "off":
        print(
            f"  {DIM}[INFO]{NC} media-provenance check is disabled (level=off). "
            f"Set media_provenance.level or --level to enable."
        )
        print(
            f"\n{BOLD}Summary:{NC} {GREEN}0 passed{NC}, "
            f"{YELLOW}0 warnings{NC}, {RED}0 errors{NC}"
        )
        return 0

    doc_types = list(_DOC_DIRS) if args.doc_type == "all" else [args.doc_type]
    scripts_dirs = _scripts_dirs(project_dir)

    report = log_fail if level == "error" else log_warn
    total = 0
    offenders = []
    for path, _area in _iter_media_files(project_dir, doc_types):
        total += 1
        rel = path.relative_to(project_dir)
        if not path.is_symlink():
            offenders.append((str(rel), "not a symlink (loose copy)"))
        elif require_under_scripts and not _resolves_under(path, scripts_dirs):
            offenders.append((str(rel), "symlink resolves outside scripts/"))

    if total == 0:
        log_pass("no media files found under contents/*/caption_and_media/")
    elif not offenders:
        suffix = " resolving under scripts/" if require_under_scripts else ""
        log_pass(f"all {total} media file(s) are symlinks{suffix}")
    else:
        for rel, why in offenders[:_MAX_LIST]:
            report(f"{rel}: {why}")
        if len(offenders) > _MAX_LIST:
            log_detail(f"... and {len(offenders) - _MAX_LIST} more")
        log_detail(
            "fix: generate media from scripts/ and symlink it into "
            "caption_and_media/, rather than committing a loose copy."
        )

    print()
    print(
        f"{BOLD}Summary:{NC} {GREEN}{PASS_COUNT} passed{NC}, "
        f"{YELLOW}{WARN_COUNT} warnings{NC}, {RED}{FAIL_COUNT} errors{NC}"
    )
    if FAIL_COUNT > 0:
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
