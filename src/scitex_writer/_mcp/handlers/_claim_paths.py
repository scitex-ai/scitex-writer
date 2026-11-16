#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# File: src/scitex_writer/_mcp/handlers/_claim_paths.py

"""Where a claim's recorded output_file lives — resolution + portability.

Split out of ``_claim.py`` so the clew bridge (``_claim_store.py``) and the
handlers share ONE answer to "which file does this claim point at".
"""

from pathlib import Path
from typing import List, Optional


def _claim_path_roots(project_path: Path) -> List[Path]:
    """Where a claim's RELATIVE output_file may legitimately be anchored.

    Getting this wrong is not a detail — it decides whether a claim's provenance
    is reported as present or missing, and both errors are lies.

    A standalone project anchors at the project dir. But a VENDORED project puts
    the writer engine at ``<repo>/.scitex/writer`` while the pipeline's data
    stays at the REPO ROOT — so ``data/x/summary.json`` resolves only from the
    repo root. Measured on a real 49-claim manuscript: resolving against the
    writer subdir found 0 of 49; against the repo root, 25. An earlier draft of
    this function checked only the project dir and would have declared EVERY
    claim's provenance broken — the same false answer as the bug it replaces,
    pointing the other way.
    """
    roots = [project_path]
    for parent in project_path.parents:
        # Vendored layout: <repo>/.scitex/writer -> the repo root is above .scitex
        if parent.name == ".scitex":
            roots.append(parent.parent)
            break
    for parent in (project_path, *project_path.parents):
        if (parent / ".git").exists():
            if parent not in roots:
                roots.append(parent)
            break
    return roots


def _output_file_exists(
    project_path: Path, output_file: Optional[str]
) -> Optional[bool]:
    """Does the claim's recorded output actually exist?

    None when no output_file is recorded — "unknown", not "missing". Never
    resolved against the process cwd: a claim's provenance must not depend on
    where the server happened to be started.
    """
    if not output_file:
        return None
    candidate = Path(output_file)
    if candidate.is_absolute():
        return candidate.exists()
    return any((root / candidate).exists() for root in _claim_path_roots(project_path))


def resolve_output_file(
    project_path: Path, output_file: Optional[str]
) -> Optional[Path]:
    """Absolute path for a recorded output_file (never cwd-relative).

    The first claim root under which it exists wins; a file that exists under
    NO root is anchored at the project dir, so a dangling pointer stays
    dangling (and is reported as such) instead of silently re-anchoring.
    """
    if not output_file:
        return None
    candidate = Path(output_file)
    if candidate.is_absolute():
        return candidate
    for root in _claim_path_roots(project_path):
        if (root / candidate).exists():
            return (root / candidate).resolve()
    return (project_path / candidate).resolve()


def portable_output_file(project_path: Path, absolute: Optional[str]) -> Optional[str]:
    """Inverse of :func:`resolve_output_file` for display + the derived export.

    Relative to the first claim root that contains it (so a committed export
    stays valid on another host / clone); absolute only when no root does.
    """
    if not absolute:
        return None
    path = Path(absolute)
    if not path.is_absolute():
        return absolute
    for root in _claim_path_roots(project_path.resolve()):
        try:
            return str(path.relative_to(root.resolve()))
        except ValueError:
            continue
    return str(path)


def _dangling_output_error(
    output_file: Optional[str], output_exists: Optional[bool]
) -> Optional[str]:
    """Name the dangling pointer, so a broken claim cannot pass as a bare gap."""
    if output_file and output_exists is False:
        return (
            f"output_file is recorded but does not exist on disk: {output_file}. "
            f"This claim points at provenance it does not have."
        )
    return None


# EOF
