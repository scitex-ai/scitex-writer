#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# ROLE: engine-vendored — DO NOT edit here. `scitex-writer update-project`
# overwrites this file on every re-vendor; fix it upstream in the
# scitex-writer package instead (local edits are lost, and update-project
# may set it read-only in the consumer workspace after vendoring).
# File: scripts/python/check_compile_artifacts.py
# Purpose: POST-compile verification gate. Catches a FALSE-SUCCESS compile --
#          one that exits 0 but produced a DEFICIENT PDF -- and fails loud.
#
#          Motivating incident (2026-06-30): a manuscript compiled exit 0 with
#          a CLEAN log, yet embedded ZERO figures (the \includegraphics targets
#          -- jpg_for_compilation/*.jpg -- were unmaterialized .txt pointers). A
#          missing \includegraphics target emitted NO "File not found" warning,
#          so a log scan alone would NOT have caught it. The decisive check is
#          PDF-LEVEL: the compiled .tex emits N \includegraphics but the output
#          PDF embeds 0 images.
#
#          Checks (severity-gated; default error):
#            PRIMARY (log-independent): N = \includegraphics count in the
#              compiled .tex; M = embedded-image count in the PDF (pdfimages,
#              poppler). N>0 and M==0 -> FAIL; 0<M<N -> WARN. Needs poppler;
#              when absent the image check is skipped with a warning. The
#              compute env that actually compiles has poppler (e.g. Spartan via
#              `module load texlive`); a bare laptop/container may not.
#            SECONDARY (log scan): missing-graphics / "File `..' not found" in
#              the LaTeX .log; and UNDEFINED cross-references / citations -- it
#              LISTS the exact unresolved \ref / \cite keys (the ?? / [?] that
#              render in the PDF), e.g. "undefined reference(s): tab:2_scorecard,
#              tab:3_clinical", falling back to the aggregate "There were
#              undefined references". The intentional scitex self-citation NUDGE
#              ("SciTeX Writer citation not found") is NOT a trigger.
#
#          Severity precedence (highest -> lowest):
#            1. --level {off,warn,error}
#            2. env SCITEX_WRITER_COMPILE_ARTIFACTS
#            3. project ./config.yaml  compile_artifacts.level
#            4. user ~/.scitex/writer/config.yaml compile_artifacts.level
#            5. default error
#
# Usage:
#   python check_compile_artifacts.py [project_dir]
#       [--compiled-tex PATH]  (default env SCITEX_WRITER_COMPILED_TEX)
#       [--pdf PATH]           (default env SCITEX_WRITER_COMPILED_PDF)
#       [--log PATH]           (default env SCITEX_WRITER_GLOBAL_LOG_FILE)
#       [--level off|warn|error]
#
# Self-contained: stdlib + optional PyYAML (config) + optional poppler
# (pdfimages) at runtime.

import argparse
import os
import re
import shutil
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from _severity import resolve_level  # noqa: E402

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

# Secondary log-scan: missing-file/graphic patterns. The scitex self-citation
# nudge is a stdout print (not in the .log) AND intentional -- never a trigger.
_FILE_PATTERNS = (
    (re.compile(r"File [`'][^']+' not found"), "missing file/graphic"),
    (re.compile(r"!\s*LaTeX Error: File [`'][^']+' not found"), "missing input file"),
)

# Undefined cross-reference / citation warnings. LaTeX emits one line PER
# unresolved key, e.g. "LaTeX Warning: Reference `tab:foo' on page 3 undefined
# on input line 42." -- capturing the key lets the gate LIST exactly which
# \ref/\cite are unresolved (the ?? / [?] that must never ship) instead of a
# bare "undefined references". The aggregate line is the catch-all fallback.
_UNDEF_REF_RE = re.compile(r"Reference [`']([^']+)'[^\n]*?undefined")
_UNDEF_CITE_RE = re.compile(r"Citation [`']([^']+)'[^\n]*?undefined")
_UNDEF_AGG_RE = re.compile(r"There were undefined references")

# Cap names listed in one report line.
_MAX_NAMES = 25

# TERTIARY (PDF-text) checks. Both verify the OUTPUT, not the input: the
# motivating incident (2026-06-30) shipped a PDF whose signature was silently
# dropped and whose claim marks never materialized, with exit 0 and only a
# stdout WARN. The compiled .tex says what SHOULD be in the PDF; pdftotext
# says what IS.
#
# Signature: _inline_signature_footer marks its injection with this sentinel
# comment in the compiled .tex, and the footer typesets a fixed prefix
# ("Compiled by SciTeX Writer v<version>"). Sentinel present + prefix absent
# from the PDF text = the colophon was inlined but did not render. The
# sentinel must be searched in the RAW .tex -- it IS a comment, so the
# comment-stripped text used for \includegraphics counting never contains it.
_SIGNATURE_SENTINEL = "% SciTeX signature footer (inlined at compile time)"
_SIGNATURE_PDF_TEXT = "Compiled by SciTeX Writer"

# Claim placeholders: an undefined \vclaim falls back to typesetting a literal
# "[claim:<id>]" into the PDF (the silent-failure path check_claim_citations
# guards at the .tex level). This is the PDF-level backstop: if any literal
# placeholder made it into the rendered text, the manuscript is citing a claim
# that resolved to nothing, whatever the .tex-level checks believed.
_CLAIM_PLACEHOLDER_RE = re.compile(r"\[claim:[^\]\s]{1,80}\]")

# Raw macro dump: a preamble block whose @-macros were tokenized with @ still
# catcode 12 does not DEFINE anything -- it TYPESETS, putting a page of LaTeX
# internals into the PDF ahead of the title page.
#
# Measured 2026-08-18 on a stock scaffold: claims_rendered.tex was inlined into
# the BODY argument of \IfFileExists, so its own \makeatletter ran after the
# body had already been tokenized, and page 1 of manuscript.pdf read
#   claim@maybecolor[2]ifunde<fi>nedclew@hex@12ifunde<fi>nedifclewpresmarkers...
#
# THE DETECTOR IS "@ BETWEEN LETTERS", NOT A LIST OF MACRO NAMES. Two reasons,
# both measured on that PDF. First, the macros that survive as control
# sequences are exactly the ones WITHOUT @ (\providecommand, \makeatletter),
# so a name list matches nothing -- only the @-bearing names leak, because the
# @ is what breaks them. Second, LIGATURES CORRUPT THE NEEDLE: "ifundefined"
# extracts as "ifunde\x1cned" because the fi ligature is one glyph, so a plain
# substring search for the word silently finds nothing and the gate reports
# clean. An @ flanked by letters survives ligature substitution and is not
# something a rendered manuscript otherwise contains.
_MACRO_AT_RE = re.compile(r"[A-Za-z0-9]*[A-Za-z]@[A-Za-z][A-Za-z0-9@]*")

# The one legitimate source of @-between-letters in a manuscript. Excluded by
# subtraction rather than by a cleverer single pattern, so the rule above stays
# readable and the exception stays visible.
_EMAIL_RE = re.compile(r"[\w.+-]+@[\w-]+\.[\w.-]+")


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


def _strip_comments(text):
    """Drop LaTeX comments (unescaped % to EOL) so commented \\includegraphics
    and commented warnings are not counted."""
    out = []
    for line in text.split("\n"):
        m = re.search(r"(?<!\\)%", line)
        out.append(line[: m.start()] if m else line)
    return "\n".join(out)


def count_includegraphics(compiled_tex):
    """Count un-commented \\includegraphics in the compiled .tex."""
    try:
        text = Path(compiled_tex).read_text(encoding="utf-8", errors="replace")
    except OSError:
        return None
    return len(re.findall(r"\\includegraphics\b", _strip_comments(text)))


def count_pdf_images(pdf_path):
    """Embedded-image count via `pdfimages -list` (poppler), or None if poppler
    is unavailable / the call fails. Counts data rows (skip the 2 header lines)."""
    if shutil.which("pdfimages") is None:
        return None
    try:
        proc = subprocess.run(
            ["pdfimages", "-list", str(pdf_path)],
            capture_output=True,
            text=True,
            timeout=60,
        )
    except (OSError, subprocess.TimeoutExpired):
        return None
    if proc.returncode != 0:
        return None
    # Data rows start with "<page> <num> ...", e.g. "   1   0 image ...".
    rows = [ln for ln in proc.stdout.splitlines() if re.match(r"\s*\d+\s+\d+\s", ln)]
    return len(rows)


def _dedupe(names):
    """Order-preserving de-dup (LaTeX repeats a warning per page)."""
    seen = set()
    out = []
    for n in names:
        if n not in seen:
            seen.add(n)
            out.append(n)
    return out


def extract_undefined(text):
    """Return (undefined_refs, undefined_cites) key names from a LaTeX log.

    Each is an order-preserving, de-duplicated list of the keys LaTeX reported
    as undefined (the ?? / [?] that render in the PDF).
    """
    return (
        _dedupe(_UNDEF_REF_RE.findall(text)),
        _dedupe(_UNDEF_CITE_RE.findall(text)),
    )


def _fmt_names(names):
    """Comma-join names, capped at _MAX_NAMES with a '(+N more)' suffix."""
    shown = ", ".join(names[:_MAX_NAMES])
    extra = len(names) - _MAX_NAMES
    return shown + (f" (+{extra} more)" if extra > 0 else "")


def _scan_log(log_path, report):
    """Secondary: scan the LaTeX log for deficiency signals (not the self-cite
    nudge). ``report`` is log_fail or log_warn per resolved level."""
    if not log_path or not Path(log_path).exists():
        return
    try:
        text = Path(log_path).read_text(encoding="utf-8", errors="replace")
    except OSError:
        return
    for pattern, label in _FILE_PATTERNS:
        if pattern.search(text):
            report(f"log: {label}")
    # Undefined \ref / \cite -- list the exact keys (?? / [?] in the PDF).
    refs, cites = extract_undefined(text)
    if refs:
        report(f"{len(refs)} undefined reference(s) [?? in PDF]: {_fmt_names(refs)}")
    if cites:
        report(f"{len(cites)} undefined citation(s) [[?] in PDF]: {_fmt_names(cites)}")
    # Aggregate fallback: catch "There were undefined references" even if the
    # per-key warnings were absent (e.g. a truncated / hint-only log).
    if not refs and not cites and _UNDEF_AGG_RE.search(text):
        report("log: there were undefined references (unresolved \\ref/\\cite)")


def check_table_total(tex_log, report):
    """Compare the table count displayed on the final pass with the actual counter."""
    if not tex_log or os.environ.get("SCITEX_WRITER_DRAFT_MODE") == "true":
        return
    try:
        text = Path(tex_log).read_text(encoding="utf-8", errors="replace")
    except OSError:
        return
    totals = re.findall(r"(?m)^SCITEX-WRITER-TABLE-TOTAL: (\d+)/(\d+)\s*$", text)
    if totals:
        shown, actual = totals[-1]
        if shown == actual:
            log_pass(f"front matter reports the compiled table total ({actual})")
        else:
            report(f"front matter shows {shown} tables but the compile counted {actual}")
            log_detail("run a full Writer compile so the table count can settle.")


def extract_pdf_text(pdf_path):
    """PDF text via `pdftotext` (poppler), or None when unavailable/failed.

    Same availability contract as count_pdf_images: poppler lives on the env
    that actually compiles; a bare container may lack it, and every consumer
    of this helper must degrade to a WARN-skip, never a silent pass."""
    if shutil.which("pdftotext") is None:
        return None
    try:
        proc = subprocess.run(
            ["pdftotext", str(pdf_path), "-"],
            capture_output=True,
            text=True,
            timeout=60,
        )
    except (OSError, subprocess.TimeoutExpired):
        return None
    if proc.returncode != 0:
        return None
    return proc.stdout


def _read_raw_tex(compiled_tex):
    """Raw compiled-.tex text (comments INTACT -- the signature sentinel is a
    comment), or None when unreadable."""
    if not compiled_tex:
        return None
    try:
        return Path(compiled_tex).read_text(encoding="utf-8", errors="replace")
    except OSError:
        return None


def check_signature_rendered(raw_tex, pdf_text, report):
    """TERTIARY: the inlined signature footer must actually render.

    Applicability comes from the compiled .tex itself: the injector marks its
    work with _SIGNATURE_SENTINEL, so sentinel-absent means the opt-in feature
    is off and there is nothing to verify (pass). Sentinel-present demands the
    footer's fixed text in the PDF."""
    if raw_tex is None:
        log_warn("could not read compiled .tex -- skipping signature check")
        return
    if _SIGNATURE_SENTINEL not in raw_tex:
        log_pass("signature footer not enabled (opt-in) -- nothing to verify")
        return
    if pdf_text is None:
        log_warn(
            "signature footer inlined; cannot verify it rendered "
            "(pdftotext/poppler unavailable or PDF unreadable)"
        )
        return
    if _SIGNATURE_PDF_TEXT in pdf_text:
        log_pass("signature footer rendered in the PDF")
    else:
        report(
            f"signature footer was inlined into the compiled .tex but "
            f"'{_SIGNATURE_PDF_TEXT}' is absent from the PDF text -- the "
            f"colophon did not render (silent drop)."
        )
        log_detail(
            "2026-06-30 incident signature drop: the compile logged only a "
            "stdout WARN and exited 0."
        )


def check_claim_placeholders(pdf_text, report):
    """TERTIARY: no literal '[claim:<id>]' may reach the rendered PDF.

    An undefined \\vclaim typesets that placeholder instead of a value. The
    .tex-level reconciliation (check_claim_citations) should catch it first;
    this is the output-level backstop that holds even if the .tex checks were
    skipped or wrong."""
    if pdf_text is None:
        # Poppler-absent skip is already reported by the signature check when
        # applicable; a second WARN here would be noise without new signal.
        return
    hits = _dedupe(_CLAIM_PLACEHOLDER_RE.findall(pdf_text))
    if hits:
        report(
            f"{len(hits)} claim placeholder(s) rendered literally in the PDF "
            f"(undefined \\vclaim): {_fmt_names(hits)}"
        )
        log_detail(
            "fix: register the claim id(s) in claims.json / re-run "
            "render_claims so the macro resolves to a value."
        )
    else:
        log_pass("no literal [claim:...] placeholders in the PDF text")


def check_no_raw_macro_dump(pdf_text, report):
    """TERTIARY: no LaTeX internals may be TYPESET into the rendered PDF.

    Distinct from every other check here: those ask whether something that
    SHOULD be in the PDF is missing. This asks whether something that should
    never be in a PDF is present -- a preamble block that typeset itself
    instead of defining macros. The existing checks cannot see it. It carries
    no signature sentinel and no [claim:...] placeholder, so a manuscript whose
    first page is solid macro noise passed this gate clean."""
    if pdf_text is None:
        # Poppler-absent skip is already reported by the signature check.
        return
    without_emails = _EMAIL_RE.sub(" ", pdf_text)
    # Report the WHOLE offending token, not a fixed-width slice: the message is
    # what a human reads to find the block, and "m@maybecolor[2]ifunde" starting
    # mid-word is measurably harder to trace back than "claim@maybecolor".
    hits = _dedupe(_MACRO_AT_RE.findall(without_emails))
    if hits:
        report(
            f"{len(hits)} LaTeX internal(s) TYPESET into the PDF instead of "
            f"being defined -- a preamble block dumped as raw text: "
            f"{_fmt_names(hits)}"
        )
        log_detail(
            "fix: the block was inlined into a MACRO-ARGUMENT BODY (typically "
            "\\IfFileExists{f}{\\input f}{}), so its \\makeatletter ran after "
            "the body was already tokenized and @ was still catcode 12. Use a "
            "plain top-level \\input; the flattener already skips a missing "
            "non-style file before LaTeX runs."
        )
    else:
        log_pass("no raw LaTeX internals typeset into the PDF")


def main():
    parser = argparse.ArgumentParser(
        description="Post-compile verification gate: fail loud on a deficient "
        "PDF (figures referenced but not embedded; log deficiency signals)."
    )
    parser.add_argument("project_dir", nargs="?", default=".")
    parser.add_argument(
        "--compiled-tex", default=os.environ.get("SCITEX_WRITER_COMPILED_TEX")
    )
    parser.add_argument("--pdf", default=os.environ.get("SCITEX_WRITER_COMPILED_PDF"))
    parser.add_argument(
        "--log", default=os.environ.get("SCITEX_WRITER_GLOBAL_LOG_FILE")
    )
    parser.add_argument("--tex-log", help="Final LaTeX engine log")
    parser.add_argument("--level", choices=list(_LEVELS), default=None)
    args = parser.parse_args()

    project_dir = Path(args.project_dir).resolve()
    level = resolve_level(
        "compile_artifacts",
        args.level,
        project_dir,
        default="error",
        env_var="SCITEX_WRITER_COMPILE_ARTIFACTS",
    )

    print(f"\n{BOLD}=== Compile Artifacts Gate (level={level}) ==={NC}\n")
    if level == "off":
        print(f"  {DIM}[INFO]{NC} compile-artifacts gate disabled (level=off).")
        print(
            f"\n{BOLD}Summary:{NC} {GREEN}0 passed{NC}, "
            f"{YELLOW}0 warnings{NC}, {RED}0 errors{NC}"
        )
        return 0

    report = log_fail if level == "error" else log_warn

    # --- PRIMARY: \includegraphics (N) vs embedded images (M) ---
    n_graphics = count_includegraphics(args.compiled_tex) if args.compiled_tex else None
    if n_graphics is None:
        log_warn("could not read compiled .tex -- skipping figure-embedding check")
    elif n_graphics == 0:
        log_pass("no figures referenced (\\includegraphics count = 0)")
    else:
        m_images = count_pdf_images(args.pdf) if args.pdf else None
        if m_images is None:
            log_warn(
                f"{n_graphics} figure(s) referenced; cannot verify embedding "
                f"(pdfimages/poppler unavailable or PDF unreadable)"
            )
            log_detail("install poppler-utils to enable the PDF embedding check.")
        elif m_images == 0:
            report(
                f"{n_graphics} \\includegraphics referenced but the PDF embeds "
                f"ZERO images -- figures did not materialize (silent miss)."
            )
            log_detail(
                "fix: build the figure images (caption_and_media/jpg_for_compilation/"
                "*.jpg) before compiling; .txt pointers do not embed."
            )
        elif m_images < n_graphics:
            log_warn(
                f"{n_graphics} \\includegraphics referenced but only {m_images} "
                f"image(s) embedded -- some figures may be missing."
            )
        else:
            log_pass(f"{n_graphics} figure(s) referenced, {m_images} embedded")

    # --- SECONDARY: log deficiency scan ---
    _scan_log(args.log, report)
    check_table_total(args.tex_log, report)

    # --- TERTIARY: PDF-text completeness (signature, claim placeholders) ---
    pdf_text = extract_pdf_text(args.pdf) if args.pdf else None
    check_signature_rendered(_read_raw_tex(args.compiled_tex), pdf_text, report)
    check_claim_placeholders(pdf_text, report)
    check_no_raw_macro_dump(pdf_text, report)

    print()
    print(
        f"{BOLD}Summary:{NC} {GREEN}{PASS_COUNT} passed{NC}, "
        f"{YELLOW}{WARN_COUNT} warnings{NC}, {RED}{FAIL_COUNT} errors{NC}"
    )
    return 1 if FAIL_COUNT > 0 else 0


if __name__ == "__main__":
    sys.exit(main())
