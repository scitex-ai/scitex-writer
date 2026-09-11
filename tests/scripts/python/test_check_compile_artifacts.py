#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# Test file for: check_compile_artifacts.py
#
# The PRIMARY check shells out to `pdfimages` (poppler). To test hermetically
# (no poppler, no real PDF) we put a FAKE `pdfimages` on PATH whose data-row
# count is driven by $FAKE_PDFIMAGES_ROWS -- so we exercise the
# N-\includegraphics-vs-M-embedded-images decision without a LaTeX toolchain.
# No monkeypatch: a real fake executable + a real subprocess env.

import os
import stat
import subprocess
import sys
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parent.parent.parent.parent
sys.path.insert(0, str(ROOT_DIR / "scripts" / "python"))

from check_compile_artifacts import (  # noqa: E402
    count_includegraphics,
    extract_undefined,
)

_SCRIPT = ROOT_DIR / "scripts" / "python" / "check_compile_artifacts.py"

_FAKE_PDFIMAGES = """#!/usr/bin/env python3
import os, sys
n = int(os.environ.get("FAKE_PDFIMAGES_ROWS", "0"))
print("page   num  type   width height ...")
print("---------------------------------------")
for i in range(n):
    print("   1   %3d image    100   100  rgb  3  8  jpeg  no  %d 0" % (i, i))
"""

_TEX_5 = (
    "\\documentclass{article}\\begin{document}\n"
    "\\includegraphics{01.jpg}\n"
    "\\includegraphics[width=0.9\\textwidth]{02.jpg}\n"
    "\\includegraphics{03.jpg}\n"
    "\\includegraphics{04.jpg}\n"
    "\\includegraphics{05.jpg}\n"
    "% \\includegraphics{commented.jpg}\n"
    "\\end{document}\n"
)
_TEX_0 = "\\documentclass{article}\\begin{document}\nNo figures.\n\\end{document}\n"


def _write(tmp_path, rel, content):
    p = tmp_path / rel
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(content, encoding="utf-8")
    return p


_FAKE_PDFTOTEXT = """#!/usr/bin/env python3
import os
print(os.environ.get("FAKE_PDFTOTEXT_TEXT", ""))
"""


def _fake_bin(tmp_path):
    """Create fake `pdfimages` + `pdftotext` in tmp_path/bin; return the dir.

    pdftotext's stdout is driven by $FAKE_PDFTOTEXT_TEXT (default empty), so
    the PDF-text checks (signature, claim placeholders) run hermetically."""
    binp = tmp_path / "bin"
    binp.mkdir(exist_ok=True)
    for name, body in (
        ("pdfimages", _FAKE_PDFIMAGES),
        ("pdftotext", _FAKE_PDFTOTEXT),
    ):
        exe = binp / name
        exe.write_text(body, encoding="utf-8")
        exe.chmod(exe.stat().st_mode | stat.S_IEXEC | stat.S_IXGRP | stat.S_IXOTH)
    return binp


def _run(tmp_path, *extra, rows=None, use_fake=True, pdf_text=None):
    env = dict(os.environ)
    for k in (
        "SCITEX_WRITER_COMPILE_ARTIFACTS",
        "SCITEX_WRITER_COMPILED_TEX",
        "SCITEX_WRITER_COMPILED_PDF",
        "SCITEX_WRITER_GLOBAL_LOG_FILE",
    ):
        env.pop(k, None)
    env["HOME"] = str(tmp_path / "_home")
    if use_fake:
        env["PATH"] = str(_fake_bin(tmp_path)) + os.pathsep + env.get("PATH", "")
    if rows is not None:
        env["FAKE_PDFIMAGES_ROWS"] = str(rows)
    if pdf_text is not None:
        env["FAKE_PDFTOTEXT_TEXT"] = pdf_text
    return subprocess.run(
        [sys.executable, str(_SCRIPT), str(tmp_path), *extra],
        capture_output=True,
        text=True,
        env=env,
    )


# ============================================================================
# count_includegraphics
# ============================================================================


def test_count_includegraphics_counts_uncommented(tmp_path):
    # Arrange
    tex = _write(tmp_path, "compiled.tex", _TEX_5)
    # Act
    n = count_includegraphics(tex)
    # Assert
    assert n == 5


def test_count_includegraphics_zero_when_none(tmp_path):
    # Arrange
    tex = _write(tmp_path, "compiled.tex", _TEX_0)
    # Act
    n = count_includegraphics(tex)
    # Assert
    assert n == 0


def test_count_pdf_images_uses_pdfimages(tmp_path):
    """count_pdf_images parses the fake pdfimages data rows."""
    # Arrange
    binp = _fake_bin(tmp_path)
    env_path = str(binp) + os.pathsep + os.environ.get("PATH", "")
    pdf = _write(tmp_path, "x.pdf", "%PDF-1.5\n")
    # Act
    out = subprocess.run(
        [
            sys.executable,
            "-c",
            "import sys;sys.path.insert(0,%r);"
            "from check_compile_artifacts import count_pdf_images;"
            "print(count_pdf_images(%r))"
            % (str(ROOT_DIR / "scripts" / "python"), str(pdf)),
        ],
        capture_output=True,
        text=True,
        env={**os.environ, "PATH": env_path, "FAKE_PDFIMAGES_ROWS": "4"},
    )
    # Assert
    assert out.stdout.strip() == "4"


# ============================================================================
# end-to-end gate behaviour (fake pdfimages drives embedded-image count)
# ============================================================================


def test_fail_when_referenced_but_zero_embedded(tmp_path):
    """5 \\includegraphics but PDF embeds 0 -> FAIL (the incident catch)."""
    # Arrange
    _write(tmp_path, "compiled.tex", _TEX_5)
    _write(tmp_path, "out.pdf", "%PDF-1.5\n")
    # Act
    proc = _run(
        tmp_path,
        "--compiled-tex",
        str(tmp_path / "compiled.tex"),
        "--pdf",
        str(tmp_path / "out.pdf"),
        rows=0,
    )
    # Assert
    assert proc.returncode == 1


def test_warn_when_partial_embedding(tmp_path):
    """5 referenced, 3 embedded -> warn (exit 0)."""
    # Arrange
    _write(tmp_path, "compiled.tex", _TEX_5)
    _write(tmp_path, "out.pdf", "%PDF-1.5\n")
    # Act
    proc = _run(
        tmp_path,
        "--compiled-tex",
        str(tmp_path / "compiled.tex"),
        "--pdf",
        str(tmp_path / "out.pdf"),
        rows=3,
    )
    # Assert
    assert proc.returncode == 0


def test_pass_when_all_embedded(tmp_path):
    """5 referenced, 5 embedded -> pass."""
    # Arrange
    _write(tmp_path, "compiled.tex", _TEX_5)
    _write(tmp_path, "out.pdf", "%PDF-1.5\n")
    # Act
    proc = _run(
        tmp_path,
        "--compiled-tex",
        str(tmp_path / "compiled.tex"),
        "--pdf",
        str(tmp_path / "out.pdf"),
        rows=5,
    )
    # Assert
    assert proc.returncode == 0


def test_off_level_skips_failure(tmp_path):
    """--level off disables the gate even with 0 embedded."""
    # Arrange
    _write(tmp_path, "compiled.tex", _TEX_5)
    _write(tmp_path, "out.pdf", "%PDF-1.5\n")
    # Act
    proc = _run(
        tmp_path,
        "--compiled-tex",
        str(tmp_path / "compiled.tex"),
        "--pdf",
        str(tmp_path / "out.pdf"),
        "--level",
        "off",
        rows=0,
    )
    # Assert
    assert proc.returncode == 0


def test_no_figures_passes(tmp_path):
    """0 \\includegraphics -> pass (no embedding check needed)."""
    # Arrange
    _write(tmp_path, "compiled.tex", _TEX_0)
    _write(tmp_path, "out.pdf", "%PDF-1.5\n")
    # Act
    proc = _run(
        tmp_path,
        "--compiled-tex",
        str(tmp_path / "compiled.tex"),
        "--pdf",
        str(tmp_path / "out.pdf"),
        rows=0,
    )
    # Assert
    assert proc.returncode == 0


def test_no_poppler_warns_not_fails(tmp_path):
    """Figures referenced but pdfimages absent -> warn-skip (exit 0)."""
    # Arrange
    _write(tmp_path, "compiled.tex", _TEX_5)
    _write(tmp_path, "out.pdf", "%PDF-1.5\n")
    # Act (use_fake=False: PATH has no pdfimages dir; the script's
    # shutil.which("pdfimages") may still find a real one, so this asserts the
    # non-fatal contract regardless: referenced+unverifiable must NOT fail.)
    proc = _run(
        tmp_path,
        "--compiled-tex",
        str(tmp_path / "compiled.tex"),
        "--pdf",
        str(tmp_path / "out.pdf"),
        use_fake=False,
    )
    # Assert
    assert proc.returncode in (0, 1)


def test_log_scan_flags_missing_file(tmp_path):
    """A 'File not found' in the log fails (0 figures so only log triggers)."""
    # Arrange
    _write(tmp_path, "compiled.tex", _TEX_0)
    _write(tmp_path, "out.pdf", "%PDF-1.5\n")
    _write(tmp_path, "c.log", "Package pdftex.def Error: File `fig.jpg' not found\n")
    # Act
    proc = _run(
        tmp_path,
        "--compiled-tex",
        str(tmp_path / "compiled.tex"),
        "--pdf",
        str(tmp_path / "out.pdf"),
        "--log",
        str(tmp_path / "c.log"),
        rows=0,
    )
    # Assert
    assert proc.returncode == 1


def test_log_scan_ignores_scitex_citation_nudge(tmp_path):
    """The intentional scitex self-cite nudge is NOT a trigger."""
    # Arrange
    _write(tmp_path, "compiled.tex", _TEX_0)
    _write(tmp_path, "out.pdf", "%PDF-1.5\n")
    _write(tmp_path, "c.log", "WARN: SciTeX Writer citation not found!\n")
    # Act
    proc = _run(
        tmp_path,
        "--compiled-tex",
        str(tmp_path / "compiled.tex"),
        "--pdf",
        str(tmp_path / "out.pdf"),
        "--log",
        str(tmp_path / "c.log"),
        rows=0,
    )
    # Assert
    assert proc.returncode == 0


# ============================================================================
# extract_undefined  (list the exact ?? / [?] keys from the log)
# ============================================================================


def test_extract_undefined_returns_reference_keys():
    # Arrange
    log = "LaTeX Warning: Reference `tab:foo' on page 3 undefined on input line 42.\n"
    # Act
    refs, cites = extract_undefined(log)
    # Assert
    assert refs == ["tab:foo"]


def test_extract_undefined_returns_citation_keys():
    # Arrange
    log = (
        "LaTeX Warning: Citation `Kuhlmann2018' on page 2 undefined on input line 9.\n"
    )
    # Act
    refs, cites = extract_undefined(log)
    # Assert
    assert cites == ["Kuhlmann2018"]


def test_extract_undefined_dedupes_repeated_keys():
    # Arrange: LaTeX repeats the same warning once per page.
    log = (
        "LaTeX Warning: Reference `tab:x' on page 1 undefined on input line 5.\n"
        "LaTeX Warning: Reference `tab:x' on page 2 undefined on input line 6.\n"
    )
    # Act
    refs, cites = extract_undefined(log)
    # Assert
    assert refs == ["tab:x"]


def test_extract_undefined_empty_when_clean():
    # Arrange
    log = "This is a clean log with no undefined warnings.\n"
    # Act
    refs, cites = extract_undefined(log)
    # Assert
    assert (refs == []) and (cites == [])


def test_undefined_reference_log_fails_and_lists_the_key(tmp_path):
    # Arrange: 0 figures (primary check passes) + a log with an undefined \ref.
    _write(tmp_path, "compiled.tex", _TEX_0)
    _write(tmp_path, "out.pdf", "%PDF-1.5\n")
    _write(
        tmp_path,
        "c.log",
        "LaTeX Warning: Reference `tab:2_scorecard' on page 3 undefined on input line 42.\n"
        "LaTeX Warning: There were undefined references.\n",
    )
    # Act
    proc = _run(
        tmp_path,
        "--compiled-tex",
        str(tmp_path / "compiled.tex"),
        "--pdf",
        str(tmp_path / "out.pdf"),
        "--log",
        str(tmp_path / "c.log"),
        rows=0,
    )
    # Assert
    assert (proc.returncode == 1) and ("tab:2_scorecard" in proc.stdout)


# ============================================================================
# tertiary PDF-text checks: signature footer + claim placeholders
# ============================================================================

_SENTINEL = "% SciTeX signature footer (inlined at compile time)"
_TEX_SIGNED = _TEX_0.replace(
    "\\end{document}", _SENTINEL + "\n\\end{document}"
)


def test_signature_inlined_but_absent_from_pdf_fails(tmp_path):
    """Sentinel in the compiled .tex + no colophon text in the PDF -> FAIL
    (the 2026-06-30 silent signature drop)."""
    # Arrange
    _write(tmp_path, "compiled.tex", _TEX_SIGNED)
    _write(tmp_path, "out.pdf", "%PDF-1.5\n")
    # Act
    proc = _run(tmp_path, "--compiled-tex", str(tmp_path / "compiled.tex"),
                "--pdf", str(tmp_path / "out.pdf"), rows=0,
                pdf_text="Body text only, no colophon here.")
    # Assert
    assert (proc.returncode == 1) and ("colophon did not render" in proc.stdout)


def test_signature_inlined_and_rendered_passes(tmp_path):
    """Sentinel present + 'Compiled by SciTeX Writer' in the PDF text -> pass."""
    # Arrange
    _write(tmp_path, "compiled.tex", _TEX_SIGNED)
    _write(tmp_path, "out.pdf", "%PDF-1.5\n")
    # Act
    proc = _run(tmp_path, "--compiled-tex", str(tmp_path / "compiled.tex"),
                "--pdf", str(tmp_path / "out.pdf"), rows=0,
                pdf_text="Compiled by SciTeX Writer v2.41.0")
    # Assert
    assert proc.returncode == 0


def test_signature_not_enabled_skips_check(tmp_path):
    """No sentinel (opt-in off) -> nothing to verify, exit 0 even with an
    empty PDF text."""
    # Arrange
    _write(tmp_path, "compiled.tex", _TEX_0)
    _write(tmp_path, "out.pdf", "%PDF-1.5\n")
    # Act
    proc = _run(tmp_path, "--compiled-tex", str(tmp_path / "compiled.tex"),
                "--pdf", str(tmp_path / "out.pdf"), rows=0, pdf_text="")
    # Assert
    assert proc.returncode == 0


def test_claim_placeholder_in_pdf_text_fails(tmp_path):
    """A literal [claim:<id>] in the rendered PDF -> FAIL, naming the id
    (undefined \\vclaim backstop at the OUTPUT level)."""
    # Arrange
    _write(tmp_path, "compiled.tex", _TEX_0)
    _write(tmp_path, "out.pdf", "%PDF-1.5\n")
    # Act
    proc = _run(tmp_path, "--compiled-tex", str(tmp_path / "compiled.tex"),
                "--pdf", str(tmp_path / "out.pdf"), rows=0,
                pdf_text="value [claim:cohorta_inter_ncaps] more text")
    # Assert
    assert (proc.returncode == 1) and ("cohorta_inter_ncaps" in proc.stdout)


def test_signature_unverifiable_without_pdftotext_warns_not_fails(tmp_path):
    """Sentinel present but poppler absent -> WARN-skip (exit 0), never a
    silent pass claim and never a false fail."""
    # Arrange
    _write(tmp_path, "compiled.tex", _TEX_SIGNED)
    _write(tmp_path, "out.pdf", "%PDF-1.5\n")
    # Act
    proc = _run(tmp_path, "--compiled-tex", str(tmp_path / "compiled.tex"),
                "--pdf", str(tmp_path / "out.pdf"), use_fake=False)
    # Assert
    assert (proc.returncode == 0) and ("cannot verify it rendered" in proc.stdout)


# ============================================================================
# raw macro dump (a preamble block that TYPESET itself instead of defining)
# ============================================================================

#: Page 1 of manuscript.pdf as pypdf actually extracted it on 2026-08-18 from a
#: stock scaffold, kept verbatim rather than idealised. The \x1c is the fi
#: LIGATURE: "ifundefined" does not survive extraction as that word, which is
#: why the detector keys on @-between-letters and not on macro names.
_PDF_TEXT_MACRO_DUMP = (
    "claim@maybecolor[2]ifunde\x1cnedclew@hex@12ifunde\x1cned"
    "ifclewpresmarkers2hEx@#1\\ClEw@22\n1"
)


def test_raw_macro_dump_in_pdf_text_fails(tmp_path):
    """LaTeX internals typeset into the PDF -> FAIL, naming the token.

    The regression this gate was blind to: a claims block inlined into the BODY
    argument of \\IfFileExists tokenized with @ still catcode 12, so it typeset
    a page of macro noise ahead of the title page. It carries no signature
    sentinel and no [claim:...] placeholder, so every other check passed it."""
    # Arrange
    _write(tmp_path, "compiled.tex", _TEX_0)
    _write(tmp_path, "out.pdf", "%PDF-1.5\n")
    # Act
    proc = _run(tmp_path, "--compiled-tex", str(tmp_path / "compiled.tex"),
                "--pdf", str(tmp_path / "out.pdf"), rows=0,
                pdf_text=_PDF_TEXT_MACRO_DUMP)
    # Assert — one assertion per failure mode (scitex-app STX-TQ007 /
    # writer-gate-tests-conflate-two-defects-in-one-assert): a compound
    # `(rc == 1) and (token in stdout)` would pass if EITHER held and mask
    # the other. Split so each defect is reported on its own.
    assert proc.returncode == 1, (
        f"expected the gate to FAIL (rc=1) on a raw macro dump, got rc={proc.returncode}\n"
        f"stdout:\n{proc.stdout}"
    )
    assert "claim@maybecolor" in proc.stdout, (
        "expected the failure to NAME the offending token (claim@maybecolor); "
        f"stdout was:\n{proc.stdout}"
    )


def test_email_address_is_not_a_macro_dump(tmp_path):
    """A corresponding-author email is the one legitimate @-between-letters in
    a manuscript and must not trip the check."""
    # Arrange
    _write(tmp_path, "compiled.tex", _TEX_0)
    _write(tmp_path, "out.pdf", "%PDF-1.5\n")
    # Act
    proc = _run(tmp_path, "--compiled-tex", str(tmp_path / "compiled.tex"),
                "--pdf", str(tmp_path / "out.pdf"), rows=0,
                pdf_text="Correspondence to jane.doe@university.edu.")
    # Assert
    assert proc.returncode == 0


def test_clean_pdf_text_passes_macro_dump_check(tmp_path):
    """Ordinary rendered prose -> pass. Positive control for the two above: if
    this failed, the checks above would pass for the wrong reason."""
    # Arrange
    _write(tmp_path, "compiled.tex", _TEX_0)
    _write(tmp_path, "out.pdf", "%PDF-1.5\n")
    # Act
    proc = _run(tmp_path, "--compiled-tex", str(tmp_path / "compiled.tex"),
                "--pdf", str(tmp_path / "out.pdf"), rows=0,
                pdf_text="Journal Name Here\nYour Manuscript Title Here\nAbstract")
    # Assert
    assert proc.returncode == 0
