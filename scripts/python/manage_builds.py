#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# ROLE: engine-vendored — DO NOT edit here. `scitex-writer update-project`
# overwrites this file on every re-vendor; fix it upstream in the
# scitex-writer package instead (local edits are lost, and update-project
# may set it read-only in the consumer workspace after vendoring).
# File: scripts/python/manage_builds.py
# Purpose: List and inspect compiled-manuscript build IDs (writer #77).

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from _project_root import resolve_project_root  # noqa: E402

GREEN = "\033[0;32m"
YELLOW = "\033[1;33m"
DIM = "\033[0;90m"
CYAN = "\033[0;36m"
YELLOW = "\033[1;33m"
BOLD = "\033[1m"
NC = "\033[0m"

_DEPRECATION_WARNED = False  # print legacy-path warning at most once


def _resolve_registry(project_root: Path) -> Path:
    """Resolve the build-registry JSON path (runtime/ canonical).

    Returns the canonical path under ``runtime/builds/builds.json``.
    If only the legacy ``builds/builds.json`` exists, returns that instead
    and emits a one-time deprecation warning (back-compat §8).
    """
    global _DEPRECATION_WARNED
    canonical = (
        project_root / ".scitex" / "writer" / "runtime" / "builds" / "builds.json"
    )
    legacy = project_root / ".scitex" / "writer" / "builds" / "builds.json"

    if canonical.exists():
        return canonical
    if legacy.exists():
        if not _DEPRECATION_WARNED:
            print(
                f"{YELLOW}WARN:{NC} build registry at legacy path {legacy}. "
                f"Move it to {canonical} for PS-102 compliance.",
                file=sys.stderr,
            )
            _DEPRECATION_WARNED = True
        return legacy
    return canonical


def _load(project_root: Path) -> list[dict]:
    registry = _resolve_registry(project_root)
    if not registry.exists():
        return []
    try:
        data = json.loads(registry.read_text())
    except Exception:
        return []
    return data.get("builds", [])


def cmd_list(args: argparse.Namespace) -> int:
    project_root = Path(args.project_root).resolve()
    builds = _load(project_root)
    if not builds:
        registry = _resolve_registry(project_root)
        print(f"{DIM}No builds recorded yet at {registry}{NC}")
        print(
            f"{DIM}(Compile anything with ./compile.sh to create the first entry.){NC}"
        )
        return 0

    n = args.n if args.n else len(builds)
    recent = builds[-n:]

    print(f"{BOLD}{CYAN}SciTeX Writer build registry{NC}")
    print(f"{DIM}{_resolve_registry(project_root)}{NC}")
    print(f"{DIM}Showing {len(recent)} of {len(builds)} build(s){NC}")
    print()
    print(
        f"  {'Build':<12} {'Doc':<15} {'Commit':<14} {'Dirty':<6} "
        f"{'Engine':<10} Timestamp"
    )
    print("  " + "-" * 86)
    for b in recent:
        bid = b.get("build_id", "?")
        doc = b.get("doc_type", "?")
        commit = b.get("git_commit") or "nogit"
        dirty = "yes" if b.get("git_dirty") else "no"
        engine = b.get("engine", "?")
        ts = b.get("timestamp", "?")
        color = YELLOW if b.get("git_dirty") else GREEN
        print(
            f"  {color}{bid:<12}{NC} {doc:<15} {commit:<14} {dirty:<6} "
            f"{engine:<10} {ts}"
        )
    return 0


def cmd_show(args: argparse.Namespace) -> int:
    project_root = Path(args.project_root).resolve()
    builds = _load(project_root)
    for b in reversed(builds):
        if b.get("build_id", "").startswith(args.build_id):
            print(json.dumps(b, indent=2))
            return 0
    print(f"ERROR: No build found matching '{args.build_id}'", file=sys.stderr)
    return 1


def main() -> int:
    parser = argparse.ArgumentParser(
        description="List and inspect scitex-writer build IDs."
    )
    parser.add_argument(
        "--project-root",
        default=resolve_project_root(),
        help="Project root (default: SCITEX_WRITER_PROJECT_ROOT env var or cwd)",
    )
    sub = parser.add_subparsers(dest="command", required=True)

    p_list = sub.add_parser("list", help="List recent builds")
    p_list.add_argument("-n", type=int, default=20, help="Show last N builds")
    p_list.set_defaults(func=cmd_list)

    p_show = sub.add_parser("show", help="Show a specific build by ID prefix")
    p_show.add_argument("build_id", help="Build ID (or unique prefix)")
    p_show.set_defaults(func=cmd_show)

    args = parser.parse_args()
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())

# EOF
