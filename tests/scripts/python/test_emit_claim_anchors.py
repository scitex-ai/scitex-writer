#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# Test file for: scripts/python/emit_claim_anchors.py
#
# THE GAP THIS CLOSES. A PDF reader that overlays claims (scitex-live-paper)
# needs each \vclaim's page and box. Without a <pdf stem>.pdf-anchors.json the
# reader shows every claim as "registered" and a click cannot reach its text.
# \vclaim now records its start/end positions (and the line's left edge) in the
# .aux; emit_claim_anchors.py turns those records into the reader's contract:
#   {"pdf_sha256": ..., "anchors": {id: {"page": 1-based, "bbox": [x0,y0,x1,y1]}}}
# with bbox in PDF points from the bottom-left corner.
#
# No mocks: the parser runs on .aux text in the exact record format, and the
# end-to-end tests compile a real document with the real generated
# claims_rendered.tex (skipped when pdflatex is unavailable).

import hashlib
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

ROOT_DIR = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT_DIR / "scripts" / "python"))

from emit_claim_anchors import (  # noqa: E402
    SP_PER_BP,
    anchors_path_for,
    build_anchors,
    main,
    parse_aux,
)

_SCRIPT = ROOT_DIR / "scripts" / "python" / "emit_claim_anchors.py"

#: One TeX pt in PDF points.
_PT = 72 / 72.27
#: Column left edge and right edge used by the synthetic records (bp).
_LEFT = 134.0
_RIGHT = _LEFT + 345 * _PT


def _sp(bp):
    return round(bp * SP_PER_BP)


def _rec(cid, tag, page, x, y, indent=0.0, width=345.0, ht=8.4, dp=3.6):
    """One .aux record as \\vclaim writes it (x/y given in bp for readability)."""
    return (
        f"\\v@claimpos{{{cid}}}{{{tag}}}{{{page}}}{{{_sp(x)}}}{{{_sp(y)}}}"
        f"{{{indent}pt}}{{{width}pt}}{{{ht}pt}}{{{dp}pt}}\n"
    )


def _line_rec(cid, tag, page, x, y):
    """The line-left-edge record \\vclaim writes from a \\vadjust."""
    return (
        f"\\v@claimpos{{{cid}}}{{{tag}}}{{{page}}}{{{_sp(x)}}}{{{_sp(y)}}}"
        f"{{0pt}}{{0pt}}{{0pt}}{{0pt}}\n"
    )


def _anchors(aux_text):
    return build_anchors(parse_aux(aux_text))


def _rounded(values, ndigits=1):
    return [round(v, ndigits) for v in values]


# ============================================================================
# One-line claims
# ============================================================================


class TestOneLineClaim:
    def test_bbox_spans_start_to_end_mark_and_the_strut(self):
        # Arrange: start and end on the same baseline y=600 bp
        aux = _rec("acc", "1s", 1, 100, 600) + _rec("acc", "1e", 1, 160, 600)

        # Act
        bbox = _anchors(aux)["acc"]["bbox"]

        # Assert
        assert _rounded(bbox) == _rounded([100, 600 - 3.6 * _PT, 160, 600 + 8.4 * _PT])

    def test_page_is_the_shipped_page(self):
        # Arrange
        aux = _rec("acc", "1s", 3, 100, 600) + _rec("acc", "1e", 3, 160, 600)

        # Act
        page = _anchors(aux)["acc"]["page"]

        # Assert
        assert page == 3

    def test_raw_id_with_punctuation_is_the_key(self):
        # Arrange: the contract keys anchors by the raw claims.json id
        aux = _rec("group-a_effect", "1s", 1, 100, 600) + _rec(
            "group-a_effect", "1e", 1, 120, 600
        )

        # Act
        keys = list(_anchors(aux))

        # Assert
        assert keys == ["group-a_effect"]


# ============================================================================
# Claims that wrap across lines, columns and pages
# ============================================================================


@pytest.fixture
def three_line_claim():
    """Starts at x=300 on baseline 600, ends at x=200 two lines lower."""
    aux = (
        _rec("w", "1s", 1, 300, 600)
        + _line_rec("w", "1sl", 1, _LEFT, 596)
        + _rec("w", "1e", 1, 200, 576)
        + _line_rec("w", "1el", 1, _LEFT, 572)
    )
    return _anchors(aux)["w"]


class TestWrappedClaim:
    def test_three_lines_give_first_middle_and_last_line_x_extents(
        self, three_line_claim
    ):
        # Arrange
        rects = three_line_claim["rects"]

        # Act
        extents = [_rounded([r["bbox"][0], r["bbox"][2]]) for r in rects]

        # Assert: rest of line 1, the full middle line, start of the last line
        assert extents == [
            _rounded([300, _RIGHT]),
            _rounded([_LEFT, _RIGHT]),
            _rounded([_LEFT, 200]),
        ]

    def test_bbox_is_the_union_of_the_line_boxes(self, three_line_claim):
        # Arrange
        rects = [r["bbox"] for r in three_line_claim["rects"]]

        # Act
        union = [
            min(b[0] for b in rects),
            min(b[1] for b in rects),
            max(b[2] for b in rects),
            max(b[3] for b in rects),
        ]

        # Assert
        assert three_line_claim["bbox"] == union

    def test_two_lines_have_no_middle_box(self):
        # Arrange: the next baseline is 12 pt lower (strut 8.4 + 3.6 pt)
        aux = (
            _rec("w", "1s", 1, 300, 600)
            + _line_rec("w", "1sl", 1, _LEFT, 596)
            + _rec("w", "1e", 1, 200, 600 - 12 * _PT)
            + _line_rec("w", "1el", 1, _LEFT, 584)
        )

        # Act
        rects = _anchors(aux)["w"]["rects"]

        # Assert
        assert len(rects) == 2

    def test_list_indent_shifts_the_line_edges(self):
        # Arrange: inside an itemize, \@totalleftmargin=25pt, \linewidth=320pt
        aux = (
            _rec("l", "1s", 1, 300, 600, indent=25.0, width=320.0)
            + _line_rec("l", "1sl", 1, _LEFT, 596)
            + _rec("l", "1e", 1, 250, 588, indent=25.0, width=320.0)
            + _line_rec("l", "1el", 1, _LEFT, 584)
        )

        # Act
        first, last = (r["bbox"] for r in _anchors(aux)["l"]["rects"])

        # Assert: first line ends at the list's right edge, last starts at its left
        assert _rounded([first[2], last[0]]) == _rounded(
            [_LEFT + 25 * _PT + 320 * _PT, _LEFT + 25 * _PT]
        )

    def test_claim_continuing_on_the_next_page_gets_a_box_on_each(self):
        # Arrange: starts at the bottom of page 1, ends at the top of page 2
        aux = (
            _rec("p", "1s", 1, 300, 100)
            + _line_rec("p", "1sl", 1, _LEFT, 96)
            + _rec("p", "1e", 2, 200, 700)
            + _line_rec("p", "1el", 2, _LEFT, 696)
        )

        # Act
        anchor = _anchors(aux)["p"]

        # Assert: anchored where it starts; each page boxes its own line
        assert (anchor["page"], [r["page"] for r in anchor["rects"]]) == (1, [1, 2])

    def test_wrap_without_line_edges_falls_back_to_the_marks_box(self):
        # Arrange: a claim in math broke across lines; no sl/el records exist
        aux = _rec("m", "1s", 1, 300, 600) + _rec("m", "1e", 1, 200, 588)

        # Act
        bbox = _anchors(aux)["m"]["bbox"]

        # Assert
        assert _rounded(bbox) == _rounded([200, 588 - 3.6 * _PT, 300, 600 + 8.4 * _PT])


# ============================================================================
# Several occurrences of one claim
# ============================================================================


@pytest.fixture
def repeated_claim():
    """Typeset first in a float shipped on page 2, then twice on page 1."""
    aux = (
        _rec("c", "1s", 2, 100, 700)
        + _rec("c", "1e", 2, 150, 700)
        + _rec("c", "2s", 1, 100, 300)
        + _rec("c", "2e", 1, 150, 300)
        + _rec("c", "3s", 1, 100, 500)
        + _rec("c", "3e", 1, 150, 500)
    )
    return _anchors(aux)["c"]


class TestOccurrences:
    def test_anchor_is_the_earliest_in_reading_order(self, repeated_claim):
        # Arrange
        bbox = repeated_claim["bbox"]

        # Act
        place = (repeated_claim["page"], bbox[1] < 500 < bbox[3])

        # Assert: page 1, and the higher of its two occurrences
        assert place == (1, True)

    def test_every_occurrence_is_listed_in_reading_order(self, repeated_claim):
        # Arrange
        occurrences = repeated_claim["occurrences"]

        # Act
        pages = [o["page"] for o in occurrences]

        # Assert
        assert pages == [1, 1, 2]

    def test_occurrence_without_its_end_is_dropped(self):
        # Arrange: the start was shipped but the end never was
        aux = _rec("x", "1s", 1, 100, 600)

        # Act
        anchors = _anchors(aux)

        # Assert
        assert anchors == {}

    def test_unrelated_aux_lines_are_ignored(self):
        # Arrange
        aux = (
            "\\relax\n\\newlabel{fig:a}{{1}{2}}\n"
            + _rec("a", "1s", 1, 1, 2)
            + _rec("a", "1e", 1, 5, 2)
        )

        # Act
        keys = list(_anchors(aux))

        # Assert
        assert keys == ["a"]


# ============================================================================
# The command line and the output file
# ============================================================================


@pytest.fixture
def emitted(tmp_path):
    """Run the CLI on a one-claim .aux; return (pdf, exit code, payload)."""
    pdf = tmp_path / "manuscript.pdf"
    pdf.write_bytes(b"%PDF-1.5 bytes to hash\n")
    aux = tmp_path / "manuscript.aux"
    aux.write_text(_rec("a", "1s", 1, 100, 600) + _rec("a", "1e", 1, 150, 600))
    rc = main(["--aux", str(aux), "--pdf", str(pdf)])
    return pdf, rc, json.loads(anchors_path_for(pdf).read_text())


class TestCli:
    def test_exit_code_is_zero(self, emitted):
        # Arrange
        _pdf, rc, _payload = emitted

        # Act
        ok = rc == 0

        # Assert
        assert ok

    def test_file_is_named_after_the_pdf(self, emitted):
        # Arrange
        pdf, _rc, _payload = emitted

        # Act
        name = anchors_path_for(pdf).name

        # Assert
        assert name == "manuscript.pdf-anchors.json"

    def test_pdf_sha256_is_the_hash_of_the_pdf_bytes(self, emitted):
        # Arrange
        pdf, _rc, payload = emitted

        # Act
        expected = hashlib.sha256(pdf.read_bytes()).hexdigest()

        # Assert
        assert payload["pdf_sha256"] == expected

    def test_anchor_has_the_contract_fields(self, emitted):
        # Arrange
        _pdf, _rc, payload = emitted

        # Act
        anchor = payload["anchors"]["a"]

        # Assert
        assert {"page", "bbox"} <= set(anchor)

    def test_missing_aux_fails_loud(self, tmp_path):
        # Arrange
        pdf = tmp_path / "manuscript.pdf"
        pdf.write_bytes(b"%PDF\n")

        # Act
        result = subprocess.run(
            [
                sys.executable,
                str(_SCRIPT),
                "--aux",
                str(tmp_path / "none.aux"),
                "--pdf",
                str(pdf),
            ],
            capture_output=True,
            text=True,
        )

        # Assert
        assert (result.returncode, "no .aux" in result.stderr) == (1, True)

    def test_missing_aux_removes_a_stale_anchors_file(self, tmp_path):
        # Arrange: a stale anchors file from an earlier compile
        pdf = tmp_path / "manuscript.pdf"
        pdf.write_bytes(b"%PDF\n")
        stale = anchors_path_for(pdf)
        stale.write_text("{}")

        # Act
        main(["--aux", str(tmp_path / "none.aux"), "--pdf", str(pdf)])

        # Assert
        assert not stale.exists()

    def test_no_claims_writes_empty_anchors(self, tmp_path):
        # Arrange: a document without \vclaim still gets a fresh file, so an
        # older one cannot be read against the new PDF
        pdf = tmp_path / "manuscript.pdf"
        pdf.write_bytes(b"%PDF\n")
        aux = tmp_path / "manuscript.aux"
        aux.write_text("\\relax\n")

        # Act
        main(["--aux", str(aux), "--pdf", str(pdf)])

        # Assert
        assert json.loads(anchors_path_for(pdf).read_text())["anchors"] == {}


# ============================================================================
# End to end: the real generated \vclaim macros under pdflatex
# ============================================================================

_LONG = (
    "this claim is deliberately long enough that it has to wrap across at least "
    "two lines of the paragraph so that its anchor needs one box per line"
)


def _claims_tex():
    from scitex_writer._mcp.handlers._claim_render import claims_rendered_tex

    claims = {
        "short_value": {"type": "value", "value": {"value": 42, "unit": "ms"}},
        "long-text": {"type": "value", "value": {"value": _LONG}},
        "on_page_two": {"type": "value", "value": {"value": 7}},
    }
    return claims_rendered_tex(claims, "test")


@pytest.fixture
def compiled(tmp_path):
    """Compile a document using the generated macros; return (pdf, payload)."""
    if shutil.which("pdflatex") is None:
        pytest.skip("pdflatex not available")
    work = tmp_path
    (work / "claims_rendered.tex").write_text(_claims_tex(), encoding="utf-8")
    (work / "doc.tex").write_text(
        "\\documentclass{article}\n"
        "\\usepackage{xcolor}\n"
        "\\usepackage{hyperref}\n"
        "\\input{claims_rendered.tex}\n"
        "\\begin{document}\n"
        "Short: \\vclaim{short_value} done.\n\n"
        "Some leading words before it: \\vclaim{long-text} and after.\n\n"
        "\\begin{itemize}\\item In a list \\vclaim{short_value}.\\end{itemize}\n"
        "\\newpage\n"
        "\\vclaim{on_page_two} starts this paragraph.\n"
        "\\end{document}\n",
        encoding="utf-8",
    )
    for _ in range(2):
        subprocess.run(
            ["pdflatex", "-interaction=nonstopmode", "-halt-on-error", "doc.tex"],
            cwd=str(work),
            capture_output=True,
            text=True,
            env={"PATH": os.environ.get("PATH", os.defpath), "HOME": str(work)},
        )
    pdf = work / "doc.pdf"
    main(["--aux", str(work / "doc.aux"), "--pdf", str(pdf)])
    return pdf, json.loads(anchors_path_for(pdf).read_text())


def _text_in(pdf, rect):
    """Text under one anchor box, read by an independent PDF library."""
    pymupdf = pytest.importorskip("pymupdf")
    with pymupdf.open(str(pdf)) as doc:
        page = doc[rect["page"] - 1]
        x0, y0, x1, y1 = rect["bbox"]
        height = page.rect.height
        text = page.get_textbox(pymupdf.Rect(x0, height - y1, x1, height - y0))
    return " ".join(text.split())


class TestEndToEnd:
    def test_each_claim_is_anchored_on_the_page_it_is_printed(self, compiled):
        # Arrange
        _pdf, payload = compiled

        # Act
        pages = {cid: a["page"] for cid, a in payload["anchors"].items()}

        # Assert
        assert pages == {"short_value": 1, "long-text": 1, "on_page_two": 2}

    def test_a_repeated_claim_lists_both_occurrences(self, compiled):
        # Arrange
        _pdf, payload = compiled

        # Act
        count = len(payload["anchors"]["short_value"]["occurrences"])

        # Assert
        assert count == 2

    def test_wrapped_claim_first_box_starts_right_of_and_above_the_last(self, compiled):
        # Arrange
        _pdf, payload = compiled
        rects = payload["anchors"]["long-text"]["rects"]

        # Act
        first, last = rects[0]["bbox"], rects[-1]["bbox"]

        # Assert
        assert (len(rects) >= 2, first[0] > last[0], first[1] > last[1]) == (
            True,
            True,
            True,
        )

    def test_one_line_box_holds_only_the_claim_text(self, compiled):
        # Arrange
        pdf, payload = compiled

        # Act
        text = _text_in(pdf, payload["anchors"]["short_value"]["rects"][0])

        # Assert
        assert text == "42 ms"

    def test_wrapped_boxes_hold_exactly_the_claim_text(self, compiled):
        # Arrange
        pdf, payload = compiled

        # Act
        text = " ".join(
            _text_in(pdf, r) for r in payload["anchors"]["long-text"]["rects"]
        )

        # Assert: hyphenation may split a word across the line boxes
        assert text.replace("- ", "").replace("-", "") == _LONG.replace("-", "")


# EOF
