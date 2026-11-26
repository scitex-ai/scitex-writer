#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# ROLE: engine-vendored — DO NOT edit here. `scitex-writer update-project`
# overwrites this file on every re-vendor; fix it upstream in the
# scitex-writer package instead (local edits are lost, and update-project
# may set it read-only in the consumer workspace after vendoring).
# File: scripts/python/emit_claim_anchors.py
r"""Write ``<stem>.pdf-anchors.json``: where each ``\vclaim`` sits in the PDF.

WHY. A PDF reader that overlays claims (scitex-live-paper) needs, for every
claim id, the page and the box the claim text occupies. Without that file every
claim is shown only as "registered" and clicking it cannot reach its text.

HOW. ``\vclaim`` (``00_shared/claims_rendered.tex``) records positions while
the page is shipped out: ``\pdfsavepos`` before and after the claim text, each
followed by a ``\write`` to the ``.aux`` file. In a paragraph it also records
the left edge of the line in a ``\vadjust``, so a claim that wraps can be boxed
line by line. One ``.aux`` line per record::

    \v@claimpos{<id>}{<n><kind>}{<page>}{<x sp>}{<y sp>}{<indent>}{<width>}{<ht>}{<dp>}

``<n>`` numbers the occurrences; ``<kind>`` is ``s``/``e`` (claim start/end)
or ``sl``/``el`` (left edge of the start/end line). ``<page>`` is the physical
PDF page (1-based); x/y are scaled points from the bottom-left page corner;
indent and width are the line's ``\@totalleftmargin`` and ``\linewidth``; ht
and dp are the strut of the current font size.

OUTPUT (the scitex-live-paper ``pdf-anchors.json`` contract)::

    {"pdf_sha256": "<hex of the PDF bytes>",
     "anchors": {"<claim id>": {"page": 1, "bbox": [x0, y0, x1, y1], ...}}}

``page`` is 1-based and ``bbox`` is in PDF points from the bottom-left corner.
Each anchor also carries ``rects`` (one box per line or line block, any page)
and ``occurrences`` (one ``{page, bbox}`` per place the claim is printed);
readers that only know ``page``/``bbox`` ignore them. When a claim is printed
more than once the anchor is the earliest occurrence in reading order.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
from pathlib import Path

SCHEMA = "scitex-writer.pdf-anchors/v1"

#: Scaled points per PDF point (bp): 65536 sp per TeX pt, 72.27 pt per 72 bp.
SP_PER_BP = 65536 * 72.27 / 72

#: Two records closer than this (in bp) vertically are on the same line.
SAME_LINE_BP = 1.0

_RECORD = re.compile(
    r"\\v@claimpos\{(?P<id>[^{}]*)\}\{(?P<n>\d+)(?P<kind>sl|el|s|e)\}"
    r"\{(?P<page>\d+)\}\{(?P<x>-?\d+)\}\{(?P<y>-?\d+)\}"
    r"\{(?P<indent>-?[\d.]+)pt\}\{(?P<width>-?[\d.]+)pt\}"
    r"\{(?P<ht>-?[\d.]+)pt\}\{(?P<dp>-?[\d.]+)pt\}"
)


def _pt_to_bp(value: str) -> float:
    return float(value) * 72 / 72.27


def parse_aux(text: str) -> dict:
    """Records grouped by occurrence: ``{(claim_id, n): {kind: record}}``.

    The first record of each (id, n, kind) wins: TeX ships a box once, so a
    repeat can only come from a copied box, and the first is the original.
    """
    occurrences: dict = {}
    for match in _RECORD.finditer(text):
        claim_id = match["id"].strip()
        record = {
            "page": int(match["page"]),
            "x": int(match["x"]) / SP_PER_BP,
            "y": int(match["y"]) / SP_PER_BP,
            "indent": _pt_to_bp(match["indent"]),
            "width": _pt_to_bp(match["width"]),
            "ht": _pt_to_bp(match["ht"]),
            "dp": _pt_to_bp(match["dp"]),
        }
        slot = occurrences.setdefault((claim_id, int(match["n"])), {})
        slot.setdefault(match["kind"], record)
    return occurrences


def _round(box):
    return [round(value, 2) for value in box]


def occurrence_rects(records: dict) -> list:
    """Boxes ``[(page, [x0, y0, x1, y1]), ...]`` covering one printed claim.

    One line: the box from the start to the end mark. Wrapped: the rest of the
    first line, the full lines in between, and the start of the last line,
    using the line's left edge (``sl``/``el``) plus its list indent and width.
    A claim that continues on another page or column gets its first-line box
    there and its last-line box where it ends. Empty when the claim was not
    shipped out whole (no start or no end mark).
    """
    start, end = records.get("s"), records.get("e")
    if start is None or end is None:
        return []
    ht, dp = start["ht"], start["dp"]
    end_ht, end_dp = end["ht"], end["dp"]

    def line_left(mark, line_kind):
        line = records.get(line_kind)
        return None if line is None else line["x"] + mark["indent"]

    same_page = start["page"] == end["page"]
    if same_page and abs(start["y"] - end["y"]) < SAME_LINE_BP:
        x0, x1 = sorted((start["x"], end["x"]))
        return [(start["page"], [x0, start["y"] - dp, x1, start["y"] + ht])]

    start_left = line_left(start, "sl")
    end_left = line_left(end, "el")
    start_right = None if start_left is None else start_left + start["width"]
    rects = []
    # Rest of the first line.
    if start_right is not None and start_right > start["x"]:
        rects.append(
            (start["page"], [start["x"], start["y"] - dp, start_right, start["y"] + ht])
        )
    # Full lines between, when the end is lower in the same column.
    same_column = same_page and end["y"] < start["y"] and start_left is not None
    if same_column:
        top, bottom = start["y"] - dp, end["y"] + end_ht
        if top - bottom > SAME_LINE_BP:
            rects.append((start["page"], [start_left, bottom, start_right, top]))
    # Start of the last line.
    last_left = (
        end_left if end_left is not None else start_left if same_column else None
    )
    if last_left is not None and end["x"] > last_left:
        rects.append(
            (end["page"], [last_left, end["y"] - end_dp, end["x"], end["y"] + end_ht])
        )
    if not rects:
        # No line edges (e.g. a claim in math that broke across lines): the
        # box spanned by the two marks still contains the claim's start and end.
        if same_page:
            x0, x1 = sorted((start["x"], end["x"]))
            y0 = min(start["y"] - dp, end["y"] - end_dp)
            y1 = max(start["y"] + ht, end["y"] + end_ht)
            rects.append((start["page"], [x0, y0, x1, y1]))
    return rects


def _union(boxes):
    return [
        min(b[0] for b in boxes),
        min(b[1] for b in boxes),
        max(b[2] for b in boxes),
        max(b[3] for b in boxes),
    ]


def build_anchors(occurrences: dict) -> dict:
    """``{claim_id: anchor}`` with the earliest occurrence as page/bbox."""
    printed: dict = {}
    for (claim_id, _n), records in occurrences.items():
        rects = [
            (page, box)
            for page, box in occurrence_rects(records)
            if box[0] < box[2] and box[1] < box[3]
        ]
        if not rects:
            continue
        page = rects[0][0]
        bbox = _union([box for p, box in rects if p == page])
        order = (page, -bbox[3], bbox[0])
        printed.setdefault(claim_id, []).append((order, page, bbox, rects))

    anchors = {}
    for claim_id in sorted(printed):
        items = sorted(printed[claim_id], key=lambda item: item[0])
        _order, page, bbox, rects = items[0]
        anchors[claim_id] = {
            "page": page,
            "bbox": _round(bbox),
            "rects": [{"page": p, "bbox": _round(box)} for p, box in rects],
            "occurrences": [{"page": p, "bbox": _round(b)} for _o, p, b, _r in items],
        }
    return anchors


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(131_072), b""):
            digest.update(chunk)
    return digest.hexdigest()


def anchors_path_for(pdf: Path) -> Path:
    """``manuscript.pdf`` -> ``manuscript.pdf-anchors.json`` beside it."""
    return pdf.with_name(f"{pdf.stem}.pdf-anchors.json")


def emit(aux: Path, pdf: Path, out: Path) -> dict:
    """Write the anchors file for ``pdf`` from ``aux``; return its payload."""
    occurrences = parse_aux(aux.read_text(encoding="utf-8", errors="replace"))
    payload = {
        "schema": SCHEMA,
        "pdf": pdf.name,
        "pdf_sha256": sha256_file(pdf),
        "anchors": build_anchors(occurrences),
    }
    tmp = out.with_name(out.name + ".tmp")
    tmp.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    tmp.replace(out)
    return payload


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument(
        "--aux", required=True, type=Path, help="the final LaTeX run's .aux"
    )
    parser.add_argument(
        "--pdf", required=True, type=Path, help="the PDF the .aux belongs to"
    )
    parser.add_argument("--out", type=Path, help="default: <pdf stem>.pdf-anchors.json")
    args = parser.parse_args(argv)

    out = args.out or anchors_path_for(args.pdf)
    if not args.pdf.is_file():
        print(f"ERRO:     claim anchors: no PDF at {args.pdf}", file=sys.stderr)
        return 1
    if not args.aux.is_file():
        out.unlink(missing_ok=True)
        print(
            f"ERRO:     claim anchors: no .aux at {args.aux}; "
            f"{out.name} not written (the engine did not keep it)",
            file=sys.stderr,
        )
        return 1
    payload = emit(args.aux, args.pdf, out)
    print(f"INFO:     Claim anchors: {len(payload['anchors'])} claim(s) -> {out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())

# EOF
