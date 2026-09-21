#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# ROLE: engine-vendored — DO NOT edit here. `scitex-writer update-project`
# overwrites this file on every re-vendor; fix it upstream in the
# scitex-writer package instead (local edits are lost, and update-project
# may set it read-only in the consumer workspace after vendoring).
# File: scripts/python/_build_id.py
# Purpose: Per-compilation build IDs, PDF metadata injection, build registry.
#
# Build IDs let a compiled PDF be uniquely identified after it leaves the
# repo (e.g. when emailed to a collaborator). The ID is embedded in the
# PDF /Info dictionary via \hypersetup{pdfsubject=build:...} and recorded
# in `.scitex/writer/runtime/builds/builds.json` so later runs can list, diff, or
# reproduce a specific build.

from __future__ import annotations

import hashlib
import json
import os
import re
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

sys.path.insert(0, str(Path(__file__).resolve().parent))
from _project_root import resolve_project_root  # noqa: E402


def _git_head_sha() -> Optional[str]:
    try:
        out = subprocess.check_output(
            ["git", "rev-parse", "--short=12", "HEAD"],
            stderr=subprocess.DEVNULL,
        )
        return out.decode().strip()
    except Exception:
        return None


def _git_is_dirty() -> bool:
    try:
        out = subprocess.check_output(
            ["git", "status", "--porcelain"],
            stderr=subprocess.DEVNULL,
        )
        return bool(out.strip())
    except Exception:
        return False


def generate_build_id() -> str:
    """Short unique per-compilation build ID (6 hex chars)."""
    parts = [
        _git_head_sha() or "nogit",
        "dirty" if _git_is_dirty() else "clean",
        datetime.now(timezone.utc).isoformat(timespec="microseconds"),
    ]
    return hashlib.sha256("|".join(parts).encode()).hexdigest()[:6]


def register_build(
    build_id: str,
    doc_type: str,
    output_tex: Path,
    project_root: Optional[Path] = None,
) -> Optional[Path]:
    """Append a build record to `.scitex/writer/runtime/builds/builds.json`.

    Best-effort: returns None on any failure so registry writes never
    break compilation. Keeps the last 500 entries.
    """
    try:
        if project_root is None:
            project_root = Path(resolve_project_root()).resolve()
        # Canonical location per PS-102: regenerable data under runtime/
        registry_dir = project_root / ".scitex" / "writer" / "runtime" / "builds"
        registry_dir.mkdir(parents=True, exist_ok=True)
        registry_path = registry_dir / "builds.json"

        # Back-compat: migrate legacy builds/ -> runtime/builds/ (one-time)
        legacy = project_root / ".scitex" / "writer" / "builds"
        if legacy.is_dir() and legacy != registry_dir:
            legacy_json = legacy / "builds.json"
            if legacy_json.exists() and not registry_path.exists():
                try:
                    legacy_json.rename(registry_path)
                except OSError:
                    pass  # best-effort migration
            try:
                legacy.rmdir()  # succeeds only if empty after migration
            except OSError:
                pass

        entry = {
            "build_id": build_id,
            "doc_type": doc_type,
            "git_commit": _git_head_sha(),
            "git_dirty": _git_is_dirty(),
            "timestamp": (
                datetime.now(timezone.utc)
                .isoformat(timespec="seconds")
                .replace("+00:00", "Z")
            ),
            "output_tex": str(output_tex),
            "engine": (
                os.getenv("SCITEX_WRITER_SELECTED_ENGINE", "")
                or os.getenv("SCITEX_WRITER_ENGINE", "")
                or "auto"
            ),
        }

        if registry_path.exists():
            try:
                data = json.loads(registry_path.read_text())
            except Exception:
                data = {"builds": []}
        else:
            data = {"builds": []}
        data.setdefault("builds", []).append(entry)
        data["builds"] = data["builds"][-500:]
        registry_path.write_text(json.dumps(data, indent=2) + "\n")
        return registry_path
    except Exception:
        return None


BUILD_BLOCK_SENTINEL = "% --- scitex-writer build identifier "


def _writer_version_def(writer_version: Optional[str]) -> str:
    r"""``\def\writer@version{X}`` line (with trailing newline) for the LIVE
    scitex-writer version, or '' when unavailable.

    Mirrors clew's ``\def\clew@version`` in clew_rendered.tex: stamps the
    version that COMPILED the document into a macro the clew presentation-layer
    colophon reads, so it renders "Compiled by SciTeX Writer vX.Y.Z" (parallel
    to clew's "Provenance audited by SciTeX Clew vX.Y.Z"). Fail-safe: '' when
    the version is empty/"unknown" so the colophon degrades to a version-less
    line and the compile is never broken. Sanitized to LaTeX-safe [0-9A-Za-z.-]
    (never trust the string blindly), same posture as render_clew's version read.
    """
    v = "" if writer_version is None else str(writer_version).strip()
    if not v or v.lower() == "unknown":
        return ""
    v = re.sub(r"[^0-9A-Za-z.\-]", "", v)
    if not v:
        return ""
    return "\\def\\writer@version{" + v + "}\n"


def inject_build_metadata(
    content: str, build_id: str, writer_version: Optional[str] = None
) -> str:
    r"""Inject ``\hypersetup{pdfsubject=build:...}`` before ``\begin{document}``.

    hyperref finalizes PDF /Info at ``\begin{document}``, so the metadata
    must appear before then. Also exposes ``\scitexBuildID`` and
    ``\scitexBuildIDFootnote`` macros so document templates can opt into
    a tiny footer, colophon, or watermark without further changes here.

    When ``writer_version`` is given, ALSO stamps ``\def\writer@version{X}`` in
    the same ``\makeatletter`` block so the clew presentation-layer colophon can
    append " vX.Y.Z" to "Compiled by SciTeX Writer" (mirrors clew's
    ``\clew@version``). Always-on + fail-safe (see ``_writer_version_def``).
    """
    # Match the REAL document-body marker at line start, not a \begin{document}
    # appearing inside a comment (e.g. clew_presentation.tex's "overridable
    # before \begin{document})"). A plain str.replace(..., 1) hit that earlier
    # comment occurrence first, injecting the build block mid-preamble and
    # de-commenting the tail.
    marker_re = re.compile(r"(?m)^[ \t]*\\begin\{document\}")
    if marker_re.search(content) is None:
        return content

    # Idempotent: a repeated flatten (e.g. `--dark-mode` reruns the flattener on
    # already-injected content) must NOT stack a second build block before
    # \begin{document}. The sentinel comment is unique to this block.
    if BUILD_BLOCK_SENTINEL in content:
        return content

    block = (
        BUILD_BLOCK_SENTINEL
        + "-" * 38
        + "\n"
        + f"\\providecommand{{\\scitexBuildID}}{{build:{build_id}}}\n"
        + r"\providecommand{\scitexBuildIDFootnote}"
        + r"{\tiny\textcolor{gray}{\scitexBuildID}}"
        + "\n"
        + "\\AtBeginDocument{%\n"
        + "  \\@ifpackageloaded{hyperref}{%\n"
        + f"    \\hypersetup{{pdfsubject={{build:{build_id}}},"
        + "pdfkeywords={scitex-writer}}%\n"
        + "  }{}%\n"
        + "}\n"
        + _writer_version_def(writer_version)
        + "% "
        + "-" * 76
        + "\n"
    )
    # End with a newline (not a space) so the marker stays at LINE START — a
    # later line-anchored injection (dark mode) must still be able to find it.
    return marker_re.sub(
        lambda m: "\\makeatletter " + block + "\\makeatother\n" + m.group(0),
        content,
        count=1,
    )


__all__ = [
    "generate_build_id",
    "register_build",
    "inject_build_metadata",
]

# EOF
