#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# File: src/scitex_writer/_mcp/handlers/_claim_fields.py

"""Writer claim fields <-> scitex-clew claim columns.

A writer claim is stored as ONE clew claim, using clew's native columns:

* ``claim_value`` -- the LaTeX-ready display string (nature style);
* ``value``       -- the located fields only (what clew checks; see
  :func:`checked_value`);
* ``source_keys`` / ``tolerance`` -- clew's own locator and tolerance columns,
  so ``clew verify`` re-reads each located value itself;
* ``metadata``    -- what clew has no column for: the writer type, the full
  writer value dict (rendering data), context, test. Schema
  ``scitex-writer-claim/2``.

Rows written by writer < 2.44 packed every field into ``claim_value`` as a
``scitex-writer-claim/1`` JSON envelope. They are still read
(:func:`writer_payload`).
"""

from __future__ import annotations

import json
from typing import Any, Dict, Optional

from ._claim_source import WHOLE_VALUE

#: clew ``metadata`` schema of a writer claim (the fields clew has no column for)
METADATA_SCHEMA = "scitex-writer-claim/2"
#: Pre-native rows: every writer field packed into ``claim_value`` (read only).
ENVELOPE_SCHEMA = "scitex-writer-claim/1"
#: writer-only fields kept in clew ``metadata`` (beside type and value)
_METADATA_FIELDS = ("context", "test")


def checked_value(value: Any, source_keys: Optional[Dict[str, Any]]) -> Any:
    """The part of a writer value that clew checks: the LOCATED fields.

    clew's ``value`` means "the numbers this claim asserts", and ``clew
    verify`` requires each of them to be written in the display text. A
    writer value dict also carries rendering data (``unit``, ``template``,
    numbers a template does not print), so only the fields that
    ``source_keys`` locates are handed to clew. ``"."`` locates the whole
    (scalar) value. No locator -> None: clew then reads the number from the
    display text, and the claim is "registered, not checkable" unless clew
    finds that number in the source unambiguously.
    """
    if not source_keys:
        return None
    if WHOLE_VALUE in source_keys or not isinstance(value, dict):
        return value
    return {field: value[field] for field in source_keys if field in value}


def clew_fields(entry: Dict[str, Any], display: str) -> Dict[str, Any]:
    """The ``scitex_clew.add_claim`` keyword arguments carrying a claim's data."""
    source_keys = entry.get("source_keys") or None
    metadata = {
        "schema": METADATA_SCHEMA,
        "type": entry["type"],
        "value": entry["value"],
    }
    metadata.update({k: entry[k] for k in _METADATA_FIELDS if entry.get(k)})
    return {
        "claim_value": display,
        "value": checked_value(entry["value"], source_keys),
        "source_keys": source_keys,
        "tolerance": entry.get("tolerance") or None,
        "metadata": metadata,
    }


def decode_envelope(claim_value: Optional[str]) -> Optional[Dict[str, Any]]:
    """A pre-native ``scitex-writer-claim/1`` payload, else None."""
    if not claim_value or not claim_value.lstrip().startswith("{"):
        return None
    try:
        payload = json.loads(claim_value)
    except ValueError:
        return None
    if not isinstance(payload, dict) or payload.get("schema") != ENVELOPE_SCHEMA:
        return None
    return payload


def writer_payload(row: Any) -> Optional[Dict[str, Any]]:
    """The writer fields of a clew claim row; None for a clew-native claim.

    Reads clew's native columns (``metadata`` schema ``scitex-writer-claim/2``)
    and, for rows registered before those were used, the ``claim_value``
    envelope.
    """
    metadata = getattr(row, "metadata", None)
    if isinstance(metadata, dict) and metadata.get("schema") == METADATA_SCHEMA:
        payload = {
            "type": metadata.get("type"),
            "value": metadata.get("value"),
            "source_keys": row.source_keys,
            "tolerance": row.tolerance,
        }
        payload.update({k: metadata.get(k) for k in _METADATA_FIELDS})
        return payload
    return decode_envelope(row.claim_value)


__all__ = [
    "ENVELOPE_SCHEMA",
    "METADATA_SCHEMA",
    "checked_value",
    "clew_fields",
    "decode_envelope",
    "writer_payload",
]

# EOF
