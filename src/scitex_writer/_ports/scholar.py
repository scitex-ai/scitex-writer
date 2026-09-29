"""scitex-scholar bridge (optional; no hard dependency).

Resolves bibliography citation keys / DOIs to enriched scholar library
records by reading the user's scholar library via a filesystem symlink
at ``<project_dir>/.scitex/writer/00_shared/scholar/library`` (or the
writer's in-tree ``00_shared/scholar/library``).

Resolution paths, in order:

1. Linear scan of ``<library_root>/MASTER/*/metadata.json``, cached
   in-process with an mtime key. The metadata files ARE the library — no
   separate index is read, and none is maintained here.
2. Return ``None`` — caller falls back to bare bib card.

Every function degrades on missing/dangling symlink, unreadable JSON,
or unknown schema fields.
"""

from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path
from typing import Optional

from scitex_dev import try_import_optional

scitex_scholar = try_import_optional(
    "scitex_scholar", extra="scholar", pkg="scitex-writer"
)
SCHOLAR_AVAILABLE = scitex_scholar is not None


def scholar_library_root(project_dir: Path) -> Optional[Path]:
    """Resolve the project's scholar-library symlink. Returns None on dangle."""
    p = Path(project_dir) / "00_shared" / "scholar" / "library"
    try:
        resolved = p.resolve(strict=True)
    except (OSError, RuntimeError):
        return None
    if not resolved.is_dir():
        return None
    return resolved


def metadata_for_doi(root: Path, doi: str) -> Optional[dict]:
    """Look up a paper by DOI via the cached scholar-library metadata scan."""
    doi_lc = doi.lower()
    for md in _iter_all_metadata(root):
        entry_doi = (md.get("metadata", {}).get("id", {}) or {}).get("doi")
        if entry_doi and entry_doi.lower() == doi_lc:
            return md
    return None


def metadata_for_paper_id(root: Path, paper_id: str) -> Optional[dict]:
    return _hydrate_full_metadata(root, paper_id)


def iter_library_cards(root: Path) -> list[dict]:
    """Return a list of compact library records for a browse view.

    One cached library scan. Each record has ``paper_id``, ``doi``, ``title``,
    ``year``, ``venue`` at minimum; consumers should ``.get()`` anything
    beyond that.
    """
    out = []
    for md in _iter_all_metadata(root):
        m = md.get("metadata", {}) or {}
        id_ = m.get("id", {}) or {}
        basic = m.get("basic", {}) or {}
        pub = m.get("publication", {}) or {}
        out.append(
            {
                "paper_id": md.get("_paper_id"),
                "doi": id_.get("doi"),
                "arxiv_id": id_.get("arxiv_id"),
                "pmid": id_.get("pmid"),
                "title": basic.get("title"),
                "year": basic.get("year"),
                "venue": pub.get("short_journal") or pub.get("journal"),
            }
        )
    out.sort(key=lambda r: (-(r.get("year") or 0), (r.get("title") or "")))
    return out


def _hydrate_full_metadata(root: Path, paper_id: str) -> Optional[dict]:
    """Read MASTER/<paper_id>/metadata.json in full. None if missing."""
    f = root / "MASTER" / paper_id / "metadata.json"
    if not f.is_file():
        return None
    try:
        md = json.loads(f.read_text())
        md["_paper_id"] = paper_id
        return md
    except (OSError, json.JSONDecodeError):
        return None


def _iter_all_metadata(root: Path) -> tuple[dict, ...]:
    """Cached library scan, invalidated when the library dir mtime changes."""
    master = root / "MASTER"
    mtime = master.stat().st_mtime if master.is_dir() else 0.0
    return _cached_master_scan(str(root), mtime)


@lru_cache(maxsize=8)
def _cached_master_scan(root_str: str, mtime_key: float) -> tuple[dict, ...]:
    root = Path(root_str)
    master = root / "MASTER"
    if not master.is_dir():
        return ()
    entries = []
    for f in master.glob("*/metadata.json"):
        try:
            md = json.loads(f.read_text())
            md["_paper_id"] = f.parent.name
            entries.append(md)
        except (OSError, json.JSONDecodeError):
            continue
    return tuple(entries)
