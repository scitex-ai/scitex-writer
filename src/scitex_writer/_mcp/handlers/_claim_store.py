#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# File: src/scitex_writer/_mcp/handlers/_claim_store.py

"""The ONE claim store: scitex-clew. Writer keeps no independent copy.

Before this module, ``writer_claim_add`` wrote ``00_shared/claims.json`` by
itself and never told clew; clew's claims were a SEPARATE ledger that writer
only read back for colouring. A manuscript therefore had two claim stores that
could disagree, and a ``\\vclaim`` value could not be traced back through the
clew DAG at all. Now:

* every writer claim is registered with ``scitex_clew.add_claim`` — the clew
  store is the source of truth (value, provenance pointers, location);
* ``00_shared/claims.json`` is a DERIVED EXPORT regenerated from the store
  after every mutation (marked ``"_derived_from": "scitex-clew"``) so the
  compile scripts and fresh clones can still read it;
* a LEGACY (writer-authored) ``claims.json`` is migrated into the store on
  first read — loudly — and replaced by the derived export (the original is
  kept as ``claims.json.pre-clew``);
* clew not importable / store unreachable -> :class:`ClewUnavailableError`.
  There is NO fallback to the local JSON: a fallback is exactly the second
  store this module exists to remove.

Writer-only fields (structured ``value`` dict, context, test, source locators,
tolerance) have no native column in clew's claim schema, so they travel in
``claim_value`` as a versioned JSON envelope (``scitex-writer-claim/1``) whose
``display`` member is the LaTeX-ready rendering clew's own consumers show.
clew should grow a native ``metadata`` field so ``claim_value`` can go back to
being only the display string.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import threading
import warnings
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Dict, Iterator, List, Optional, Tuple

from scitex_logging import getLogger

from ._claim_paths import portable_output_file, resolve_output_file
from ._claim_source import (
    check_claim_against_source,
    normalize_source_keys,
    normalize_tolerance,
)

logger = getLogger(__name__)

CLAIMS_FILE = "00_shared/claims.json"
LEGACY_BACKUP = "00_shared/claims.json.pre-clew"
ENVELOPE_SCHEMA = "scitex-writer-claim/1"
EXPORT_VERSION = "2.0"
DERIVED_MARKER = "scitex-clew"
EXPORT_NOTE = (
    "DERIVED EXPORT of the scitex-clew claim store - do not edit. Register "
    "claims with scitex_writer.claim.add / writer_claim_add; the store is the "
    "single source of truth."
)
#: Where \vclaim call sites are searched for a claim's manuscript location.
_TEX_DIRS = (
    "01_manuscript/contents",
    "02_supplementary/contents",
    "03_revision/contents",
)
#: writer claim_type -> clew claim_type (clew has no "citation").
_CLEW_TYPE = {"citation": "text"}
#: fields that define a claim's identity for conflict detection
_COMPARED = (
    "type",
    "value",
    "context",
    "test",
    "session_id",
    "output_file",
    "source_keys",
    "tolerance",
)
_NO_LIMIT = 10**9
_TEX_COMMENT = re.compile(r"(?<!\\)%.*")

# clew resolves its project (scope id, runtime export dir) from the process
# CWD. A writer server handles many projects, so every clew call runs inside
# the project dir, serialised by this lock.
_CWD_LOCK = threading.RLock()


class ClewUnavailableError(RuntimeError):
    """scitex-clew cannot be imported or its store cannot be reached."""


# ---------------------------------------------------------------------------
# clew access — loud, never optional
# ---------------------------------------------------------------------------


def _clew():
    try:
        import scitex_clew
    except ImportError as exc:
        raise ClewUnavailableError(
            "scitex-writer claims are stored in scitex-clew, which is not "
            f"importable ({exc}). Install it (`pip install scitex-clew`, or "
            "`pip install scitex-writer[all]`). There is no local-JSON fallback: "
            "a claim not in the clew store cannot be traced to its source."
        ) from exc
    return scitex_clew


def _store_failure(exc: Exception) -> ClewUnavailableError:
    dsn_state = "set" if os.environ.get("SCITEX_STORE_DSN") else "unset"
    return ClewUnavailableError(
        f"scitex-clew claim store is unreachable ({type(exc).__name__}: {exc}). "
        f"SCITEX_STORE_DSN is {dsn_state}. Claims were NOT read or written; "
        "there is no local-JSON fallback."
    )


@contextmanager
def _in_project(project_path: Path) -> Iterator[Any]:
    clew = _clew()
    with _CWD_LOCK:
        previous = os.getcwd()
        os.chdir(project_path)
        try:
            yield clew
        except ClewUnavailableError:
            raise
        except (ValueError, TypeError):
            raise
        except Exception as exc:  # connection / store errors from the backend
            raise _store_failure(exc) from exc
        finally:
            os.chdir(previous)


# ---------------------------------------------------------------------------
# Envelope (writer fields inside clew's claim_value)
# ---------------------------------------------------------------------------


def encode_envelope(entry: Dict[str, Any], display: str) -> str:
    payload = {
        "schema": ENVELOPE_SCHEMA,
        "display": display,
        "type": entry["type"],
        "value": entry["value"],
        "context": entry.get("context"),
    }
    for key in ("test", "source_keys", "tolerance"):
        if entry.get(key):
            payload[key] = entry[key]
    return json.dumps(payload, sort_keys=True, ensure_ascii=False)


def decode_envelope(claim_value: Optional[str]) -> Optional[Dict[str, Any]]:
    """The writer payload, or None when this clew claim is not a writer claim."""
    if not claim_value or not claim_value.lstrip().startswith("{"):
        return None
    try:
        payload = json.loads(claim_value)
    except ValueError:
        return None
    if not isinstance(payload, dict) or payload.get("schema") != ENVELOPE_SCHEMA:
        return None
    return payload


# ---------------------------------------------------------------------------
# Location of the claim in the manuscript
# ---------------------------------------------------------------------------


def locate_in_tex(project_path: Path, claim_id: str) -> Tuple[Path, Optional[int]]:
    r"""First ``\vclaim[..]{claim_id}`` call site, else the export file itself.

    A claim may be registered before it is cited; it then anchors at
    ``00_shared/claims.json`` with no line until it is re-registered.
    """
    pattern = re.compile(r"\\vclaim(?:\[[^\]]*\])?\{" + re.escape(claim_id) + r"\}")
    for rel in _TEX_DIRS:
        base = project_path / rel
        if not base.is_dir():
            continue
        for tex in sorted(base.rglob("*.tex")):
            try:
                lines = tex.read_text(encoding="utf-8", errors="replace").splitlines()
            except OSError:
                continue
            for lineno, line in enumerate(lines, start=1):
                if pattern.search(_TEX_COMMENT.sub("", line)):
                    return tex, lineno
    return project_path / CLAIMS_FILE, None


# ---------------------------------------------------------------------------
# Registration
# ---------------------------------------------------------------------------


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 16), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _hash_mismatch(given: str, path: Path) -> Optional[str]:
    if not path.is_file():
        return None
    want = given.lower().removeprefix("sha256:").strip()
    have = _sha256(path)
    if have == want or (len(want) >= 16 and have.startswith(want)):
        return None
    return (
        f"output_hash {given!r} does not match the current SHA-256 of "
        f"{path} ({have}). The value was computed from a different version of "
        "the file; re-run the pipeline or re-read the value before registering."
    )


def register(
    project_path: Path,
    claim_id: str,
    entry: Dict[str, Any],
    display: str,
    *,
    tex_file: Optional[str] = None,
    line_number: Optional[int] = None,
    strict_hash: bool = True,
) -> List[str]:
    """Register (or overwrite) one writer claim in clew. Returns warnings.

    Raises ValueError for a claim that contradicts its own provenance (hash or
    located value), ClewUnavailableError when clew/the store is unavailable.
    """
    entry = dict(entry)
    entry["source_keys"] = normalize_source_keys(entry.get("source_keys"))
    entry["tolerance"] = normalize_tolerance(entry.get("tolerance"))
    notices: List[str] = []

    source_abs = resolve_output_file(project_path, entry.get("output_file"))
    if entry.get("output_hash") and source_abs is not None:
        problem = _hash_mismatch(entry["output_hash"], source_abs)
        if problem and strict_hash:
            raise ValueError(problem)
        if problem:
            notices.append(f"{claim_id}: {problem}")

    if entry["source_keys"]:
        failed = [
            r
            for r in check_claim_against_source(
                entry["value"],
                str(source_abs) if source_abs else None,
                entry["source_keys"],
                entry["tolerance"],
            )
            if not r["ok"]
        ]
        if failed:
            raise ValueError(
                f"claim {claim_id!r} disagrees with its source: "
                + "; ".join(f"{r['field']}: {r['detail']}" for r in failed)
            )

    if tex_file:
        tex_path = Path(tex_file)
        tex_path = tex_path if tex_path.is_absolute() else project_path / tex_path
    else:
        tex_path, found_line = locate_in_tex(project_path, claim_id)
        line_number = line_number if line_number is not None else found_line

    with _in_project(project_path) as clew, warnings.catch_warnings(record=True) as w:
        warnings.simplefilter("always")
        clew.add_claim(
            file_path=str(tex_path),
            claim_type=_CLEW_TYPE.get(entry["type"], entry["type"]),
            line_number=line_number,
            claim_value=encode_envelope(entry, display),
            source_file=str(source_abs) if source_abs else None,
            source_session=entry.get("session_id"),
            claim_id=claim_id,
        )
    notices.extend(f"{claim_id}: {warning.message}" for warning in w)
    return notices


def retire(project_path: Path, claim_id: str) -> bool:
    """Soft-retire (clew ``supersede_claim``): kept for audit, out of every view.

    ``remove_claim`` would HIDE the row, and clew's ``add_claim`` does not
    unhide — a claim removed and re-added under the same id would stay
    invisible. Superseding is reversed by re-registration.
    """
    with _in_project(project_path) as clew:
        return bool(clew.supersede_claim(claim_id))


# ---------------------------------------------------------------------------
# Reading
# ---------------------------------------------------------------------------


def load_store_claims(project_path: Path) -> Dict[str, Dict[str, Any]]:
    """Every active writer claim of this project, straight from the clew store."""
    with _in_project(project_path) as clew:
        rows = clew.list_claims(file_path_prefix=str(project_path), limit=_NO_LIMIT)
    claims: Dict[str, Dict[str, Any]] = {}
    for row in rows:
        payload = decode_envelope(row.claim_value)
        if payload is None:
            continue  # a clew-native claim, not one of writer's \vclaim values
        entry: Dict[str, Any] = {
            "type": payload.get("type"),
            "value": payload.get("value"),
            "context": payload.get("context"),
            "session_id": row.source_session,
            "output_file": portable_output_file(project_path, row.source_file),
            "output_hash": row.source_hash,
            "file_path": portable_output_file(project_path, row.file_path),
            "line_number": row.line_number,
            "status": row.status,
        }
        for key in ("test", "source_keys", "tolerance"):
            if payload.get(key):
                entry[key] = payload[key]
        claims[row.claim_id] = entry
    return dict(sorted(claims.items()))


def _comparable(entry: Dict[str, Any]) -> Dict[str, Any]:
    return {k: (entry.get(k) or None) for k in _COMPARED}


def write_export(project_path: Path, claims: Dict[str, Dict[str, Any]]) -> Path:
    """Regenerate the derived ``00_shared/claims.json`` (only if it changed)."""
    path = project_path / CLAIMS_FILE
    body = {
        "version": EXPORT_VERSION,
        "_derived_from": DERIVED_MARKER,
        "_note": EXPORT_NOTE,
        # Definitions only: the volatile verification STATUS stays in the
        # store, so a committed export does not churn on every `clew verify`.
        "claims": {
            cid: {k: v for k, v in entry.items() if k != "status"}
            for cid, entry in claims.items()
        },
    }
    text = json.dumps(body, indent=2, ensure_ascii=False, sort_keys=False) + "\n"
    if not path.exists() or path.read_text(encoding="utf-8") != text:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")
    return path


def sync(
    project_path: Path, render: Any
) -> Tuple[Dict[str, Dict[str, Any]], List[str]]:
    """Load claims from clew, migrating/importing any claims.json content first.

    ``render`` renders a claim entry to its display string (the envelope's
    ``display``) — passed in to keep this module free of the format layer.

    Returns ``(claims, notices)``. Every notice is ALSO logged at WARNING:
    a migration that only shows up in a return value nobody prints is silent.
    """
    project_path = project_path.resolve()
    store = load_store_claims(project_path)
    notices: List[str] = []
    path = project_path / CLAIMS_FILE

    if path.exists():
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except ValueError as exc:
            raise ValueError(f"{path} is not valid JSON: {exc}") from exc
        derived = data.get("_derived_from") == DERIVED_MARKER
        file_claims = data.get("claims", {}) or {}
        missing = [cid for cid in file_claims if cid not in store]

        if not derived:
            backup = project_path / LEGACY_BACKUP
            if not backup.exists():
                backup.write_text(path.read_text(encoding="utf-8"), encoding="utf-8")
            notices.append(
                f"MIGRATING legacy writer-owned {CLAIMS_FILE} into the "
                f"scitex-clew store ({len(missing)} of {len(file_claims)} "
                f"claim(s) newly registered: {', '.join(missing) or '-'}). The "
                f"original is kept at {LEGACY_BACKUP}; {CLAIMS_FILE} becomes a "
                "derived export of the store."
            )
        if missing:
            if derived:
                notices.append(
                    f"IMPORTING {len(missing)} claim(s) recorded in the derived "
                    f"{CLAIMS_FILE} but absent from the clew store (fresh clone "
                    f"or new host?): {', '.join(missing)}. Their source hashes are "
                    "taken NOW, not at original registration."
                )
            for cid in missing:
                entry = dict(file_claims[cid])
                entry.setdefault("type", "value")
                notices.extend(
                    register(
                        project_path,
                        cid,
                        entry,
                        render(entry),
                        line_number=entry.get("line_number"),
                        strict_hash=False,
                    )
                )
            store = load_store_claims(project_path)

        for cid, file_entry in file_claims.items():
            if cid in missing or cid not in store:
                continue
            if _comparable(file_entry) != _comparable(store[cid]):
                notices.append(
                    f"{CLAIMS_FILE} disagrees with the clew store for claim "
                    f"{cid!r}; the STORE wins and the file is regenerated. "
                    "Edit claims through writer_claim_add, not the file."
                )

    if store or path.exists():
        write_export(project_path, store)
    for notice in notices:
        logger.warning("scitex-writer claims: %s", notice)
    return store, notices


__all__ = [
    "CLAIMS_FILE",
    "ClewUnavailableError",
    "ENVELOPE_SCHEMA",
    "decode_envelope",
    "encode_envelope",
    "load_store_claims",
    "locate_in_tex",
    "register",
    "retire",
    "sync",
    "write_export",
]

# EOF
