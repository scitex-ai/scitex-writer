#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# ROLE: engine-vendored — DO NOT edit here. `scitex-writer update-project`
# overwrites this file on every re-vendor; fix it upstream in the
# scitex-writer package instead (local edits are lost, and update-project
# may set it read-only in the consumer workspace after vendoring).
# File: scripts/python/check_citations.py
# Purpose: Pre-compile CITATION GATE -- before a research manuscript is
#          compiled, check every \cite key actually used in the document against
#          its bibliography entry and FAIL the build if a cited entry is a
#          scholar STUB (auto-generated placeholder that has not yet been
#          resolved to a real, verified source). A stub reference must never
#          reach a compiled manuscript ("一発アウト"): it is either a
#          hallucinated citation or an unfinished lookup.
#
#          This is the COMPILER-OWNS half of the citation->clew verification
#          contract (neurovista, operator-directed 2026-07-01). It is fully
#          LOCAL -- no clew/scholar dependency -- so it delivers the root-fix
#          immediately and would have failed the neurovista build on the
#          PintoOrellana2023 stub at source. The CLEW-OWNS half (querying clew
#          for per-key scholar verification status) slots in later behind the
#          same report once clew defines its batch lookup; until then this gate
#          catches the stub stamps scholar already writes.
#
#          The gate reads the bib that bibtex actually reads: it parses the
#          \bibliography{}/\addbibresource{} target from the tex and resolves it
#          relative to the tex, FOLLOWING SYMLINKS (real trees point
#          contents/bibliography.bib at a possibly-legacy enriched bib, not
#          necessarily 00_shared). --bib overrides; conventional fallbacks apply
#          only when no \bibliography target is found.
#
#          A STUB is detected by the markers scholar stamps into the entry:
#            * note    contains "Auto-generated stub"   (STUB_NOTE_MARKERS)
#            * journal contains "Pending scitex-scholar metadata lookup"
#                                                        (STUB_JOURNAL_MARKERS)
#          A cited entry matching ANY marker is a stub and gates. "No DOI" is
#          deliberately NOT a sole stub trigger -- many legitimate references
#          (books, arXiv preprints, conference papers) have no DOI, so failing
#          on that alone would be a false positive. Missing-DOI cited entries
#          are surfaced as an informational note only. The marker lists are
#          module constants so scholar's authoritative stamp fields can be
#          extended without touching the logic.
#
#          DEFAULT depends on project type: a *research* project (marked by
#          .scitex/dev/config.yaml `project-type: research`) defaults to
#          `error` (gate ON -> FAIL); any other project defaults to `warn`
#          (loud, non-blocking). CLI/env/config always override the default.
#
# Usage:
#   python check_citations.py [project_dir]
#                             [--tex PATH ...] [--bib PATH]
#                             [--level off|warn|error]
#
# Self-contained: stdlib + optional PyYAML (only to read config files).

import argparse
import glob
import os
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from _severity import resolve_level  # noqa: E402
from _citation_banner import reset_banner, write_banner_tex  # noqa: E402

GREEN = "\033[0;32m"
YELLOW = "\033[1;33m"
RED = "\033[0;31m"
DIM = "\033[0;90m"
BOLD = "\033[1m"
NC = "\033[0m"

PASS_COUNT = 0
WARN_COUNT = 0
FAIL_COUNT = 0

_LEVELS = ("off", "warn", "error", "banner")

# Where the banner-mode compile artifact is written. The flattener
# (compile_tex_structure.py) injects this file after \begin{document} when it
# exists. Path is derivable identically from the project root on both sides.
_BANNER_TEX = ".scitex/writer/.citation_banner.tex"

# Scholar stub stamps (lowercase substring match). Authoritative source is
# scitex-scholar; extend here when scholar adds/renames a stamp field.
STUB_NOTE_MARKERS = ("auto-generated stub",)
STUB_JOURNAL_MARKERS = ("pending scitex-scholar metadata lookup",)

# Citation commands whose {..} argument holds comma-separated cite keys.
_CITE_CMD = (
    r"\\(?:cite|citep|citet|citeauthor|citeyear|citeyearpar|citealt|citealp|"
    r"citenum|Cite|Citep|Citet|Citeauthor|parencite|Parencite|textcite|"
    r"Textcite|autocite|Autocite|footcite|fullcite|smartcite)"
)
# Optional [..] pre/post-notes, then the mandatory {key,key,...}.
_CITE_RE = re.compile(_CITE_CMD + r"\s*(?:\[[^\]]*\]\s*){0,2}\{([^}]*)\}")

# Directories whose .tex is never built, skipped when the source set falls back
# to scanning the project: retired sources kept for reference (legacy/),
# versioned snapshots (paths.archive_dir, ./0N_*/archive), and build output.
_NON_SOURCE_DIRS = frozenset(
    {"legacy", "archive", "logs", "builds", "export", "_minted", ".git"}
)

# \bibliography{a,b} (bibtex) and \addbibresource{a.bib} (biblatex).
_BIB_CMD_RE = re.compile(r"\\(?:bibliography|addbibresource)\s*\{([^}]*)\}")

# Conventional fallbacks, tried (and symlink-resolved) when no \bibliography
# command is found in the tex. contents/bibliography.bib is the compile-tree
# entry point and is typically a symlink into the real (possibly legacy) bib.
_FALLBACK_BIBS = (
    "01_manuscript/contents/bibliography.bib",
    "00_shared/bib_files/bibliography.bib",
)


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


def _strip_tex_comments(tex):
    r"""Drop LaTeX line comments so a commented-out \cite is not counted.

    A percent is a comment start unless escaped (\%). Keep everything before an
    unescaped %.
    """
    out = []
    for line in tex.splitlines():
        idx = 0
        cut = None
        while idx < len(line):
            ch = line[idx]
            if ch == "\\":
                idx += 2  # skip escaped char (covers \%)
                continue
            if ch == "%":
                cut = idx
                break
            idx += 1
        out.append(line if cut is None else line[:cut])
    return "\n".join(out)


def extract_cited_keys(tex):
    r"""Return the set of cite keys referenced by \cite-family commands in tex.

    Commented-out citations are ignored. Whitespace and empty keys are dropped,
    and so are macro parameter placeholders: ``\\cite{#1}`` inside a
    ``\\newcommand`` body names the macro's argument, not a bibliography key
    (``#`` is BibTeX's concatenation operator and never part of a real key).
    """
    keys = set()
    for group in _CITE_RE.findall(_strip_tex_comments(tex)):
        for raw in group.split(","):
            key = raw.strip()
            if key and "#" not in key:
                keys.add(key)
    return keys


def iter_bib_entries(bib_text):
    """Yield (cite_key, fields_dict) for each @type{key, ...} entry.

    A dependency-free scanner: finds each ``@type{key,`` header, then captures
    the entry body by brace balancing. Field values are read for both
    ``field = {value}`` and ``field = "value"`` forms. Keys and field names are
    matched case-insensitively (BibTeX is case-insensitive on both).
    """
    header = re.compile(r"@(\w+)\s*\{\s*([^,\s]+)\s*,", re.IGNORECASE)
    for m in header.finditer(bib_text):
        entry_type = m.group(1).lower()
        if entry_type in ("comment", "string", "preamble"):
            continue
        cite_key = m.group(2).strip()
        # Capture the body by brace balancing from the opening '{'.
        open_brace = bib_text.index("{", m.start())
        depth = 0
        i = open_brace
        while i < len(bib_text):
            c = bib_text[i]
            if c == "{":
                depth += 1
            elif c == "}":
                depth -= 1
                if depth == 0:
                    break
            i += 1
        body = bib_text[open_brace + 1 : i]
        yield cite_key, _parse_fields(body)


def _parse_fields(body):
    """Parse ``name = {value}`` / ``name = "value"`` pairs from an entry body."""
    fields = {}
    field_re = re.compile(
        r"(\w+)\s*=\s*(?:\{(.*?)\}|\"(.*?)\")", re.IGNORECASE | re.DOTALL
    )
    for fm in field_re.finditer(body):
        name = fm.group(1).lower()
        value = fm.group(2) if fm.group(2) is not None else (fm.group(3) or "")
        fields[name] = value.strip()
    return fields


def stub_reason(fields):
    """Return a human reason string if the entry is a scholar stub, else None."""
    note = fields.get("note", "").lower()
    for marker in STUB_NOTE_MARKERS:
        if marker in note:
            return f'note="{fields.get("note", "")}"'
    journal = fields.get("journal", "").lower()
    for marker in STUB_JOURNAL_MARKERS:
        if marker in journal:
            return f'journal="{fields.get("journal", "")}"'
    return None


def _load_text(paths):
    """Concatenate the text of every existing path in ``paths``."""
    chunks = []
    for p in paths:
        try:
            chunks.append(Path(p).read_text(encoding="utf-8", errors="replace"))
        except OSError:
            continue
    return "\n".join(chunks)


def _is_buildable_source(path, project_dir):
    """False for a .tex that is never compiled (see _NON_SOURCE_DIRS).

    Only the directories BELOW the project root count, so a project that itself
    lives under e.g. ~/archive/ is still scanned. ``*_diff.tex`` (latexdiff
    output) is excluded too: it carries both the old and the new citations.
    """
    rel = Path(path).relative_to(project_dir)
    if any(part in _NON_SOURCE_DIRS for part in rel.parts[:-1]):
        return False
    return not rel.name.endswith("_diff.tex")


def _resolve_tex_paths(project_dir, tex_args, environ=None):
    """Resolve the tex sources to scan for citations.

    Precedence: explicit --tex args (globs allowed) > SCITEX_WRITER_COMPILED_TEX
    env > every buildable *.tex under the project (last resort: legacy/,
    archive/, logs/, ... and latexdiff output are skipped). Returns a sorted
    list. ``environ`` defaults to ``os.environ``.
    """
    if tex_args:
        found = []
        for pat in tex_args:
            found.extend(sorted(glob.glob(pat)))
        return found
    env = os.environ if environ is None else environ
    env_tex = (env.get("SCITEX_WRITER_COMPILED_TEX") or "").strip()
    if env_tex and Path(env_tex).is_file():
        return [env_tex]
    project_dir = Path(project_dir)
    return sorted(
        str(p)
        for p in project_dir.rglob("*.tex")
        if _is_buildable_source(p, project_dir)
    )


def _resolve_one_bib(raw, base_dirs):
    """Resolve a single \\bibliography argument to a real, existing file.

    Tries the argument (with and without a .bib suffix) under each base dir, and
    returns the FIRST that exists -- symlink-resolved (Path.resolve follows the
    whole chain, so contents/bibliography.bib -> ... -> the real enriched bib).
    Returns None if nothing resolves.
    """
    candidates = [raw]
    if not raw.lower().endswith(".bib"):
        candidates.append(raw + ".bib")
    for base in base_dirs:
        for cand in candidates:
            p = (base / cand) if not os.path.isabs(cand) else Path(cand)
            if p.is_file():
                return p.resolve()
    return None


def resolve_bib_paths(project_dir, tex_paths, bib_arg):
    r"""Resolve the bibliography file(s) that bibtex actually reads.

    The compile tree points \cite resolution at whatever
    ``\bibliography{}`` / ``\addbibresource{}`` names -- and in real projects
    that is a SYMLINK (e.g. contents/bibliography.bib -> a legacy enriched bib),
    NOT necessarily 00_shared. So we parse the bib command from the tex, resolve
    its path relative to the tex file (then the project root), and follow the
    symlink. Precedence: explicit --bib > \bibliography targets from the tex >
    conventional fallbacks. All results are symlink-resolved and de-duplicated.
    """
    if bib_arg:
        p = Path(bib_arg)
        return [p.resolve()] if p.is_file() else []

    project_dir = Path(project_dir)
    resolved = []
    seen = set()

    def _add(path):
        if path is not None and path not in seen:
            seen.add(path)
            resolved.append(path)

    for tex in tex_paths:
        tex_dir = Path(tex).resolve().parent
        text = _load_text([tex])
        for m in _BIB_CMD_RE.finditer(text):
            for raw in m.group(1).split(","):
                raw = raw.strip()
                if raw:
                    _add(_resolve_one_bib(raw, [tex_dir, project_dir]))

    if not resolved:
        for fb in _FALLBACK_BIBS:
            _add(_resolve_one_bib(fb, [project_dir]))
    return resolved


def _is_research_project(project_dir):
    """True iff .scitex/dev/config.yaml marks this a ``project-type: research``.

    Mirrors check_clew_verify._is_research_project so both gates share one
    research-mode signal. PyYAML optional; falls back to a textual marker scan.
    """
    cfg = Path(project_dir) / ".scitex" / "dev" / "config.yaml"
    if not cfg.is_file():
        return False
    try:
        text = cfg.read_text(encoding="utf-8")
    except OSError:
        return False
    try:
        import yaml

        data = yaml.safe_load(text) or {}
        if isinstance(data, dict):
            return str(data.get("project-type", "")).strip().lower() == "research"
    except Exception:
        pass
    for line in text.splitlines():
        stripped = line.strip()
        if stripped.startswith("project-type:"):
            return stripped.split(":", 1)[1].strip().strip("\"'").lower() == "research"
    return False


def audit_citations(cited_keys, entries):
    """Classify each cited key against the bibliography.

    Returns (stubs, missing, no_doi):
      stubs   -> list of (key, reason) whose entry is a scholar stub
      missing -> sorted list of cited keys with no bibliography entry
      no_doi  -> sorted list of cited keys whose entry has no DOI (info only)
    """
    stubs = []
    missing = []
    no_doi = []
    for key in sorted(cited_keys):
        fields = entries.get(key)
        if fields is None:
            missing.append(key)
            continue
        reason = stub_reason(fields)
        if reason is not None:
            stubs.append((key, reason))
        elif not fields.get("doi", "").strip():
            no_doi.append(key)
    return stubs, missing, no_doi


def main():
    parser = argparse.ArgumentParser(
        description="Pre-compile citation gate: FAIL when a cited reference is a "
        "scholar stub (unresolved/placeholder). Defaults ON (error) for research "
        "projects, warn otherwise. `banner` level compiles anyway but stamps a "
        "red page-1 banner."
    )
    parser.add_argument("project_dir", nargs="?", default=".")
    parser.add_argument(
        "--tex",
        action="append",
        default=None,
        help="Tex file(s)/glob(s) to scan for \\cite keys (repeatable). "
        "Defaults to $SCITEX_WRITER_COMPILED_TEX, else every buildable *.tex "
        "under the project (legacy/, archive/, logs/ and *_diff.tex skipped).",
    )
    parser.add_argument(
        "--bib",
        default=None,
        help="Bibliography .bib to read entries from. Default: resolve the "
        "\\bibliography{}/\\addbibresource{} target from the tex (symlink-"
        "followed), else conventional fallbacks.",
    )
    parser.add_argument(
        "--level",
        choices=list(_LEVELS),
        default=None,
        help="Severity: off, warn, error, or banner. Overrides env and config.",
    )
    args = parser.parse_args()

    project_dir = Path(args.project_dir).resolve()
    research = _is_research_project(project_dir)
    default = "error" if research else "warn"
    level = resolve_level(
        "citations",
        args.level,
        project_dir,
        default=default,
        env_var="SCITEX_WRITER_CITATIONS",
    )
    kind = "research" if research else "non-research"
    print(f"\n{BOLD}=== Citation Gate (level={level}, {kind}) ==={NC}\n")

    # Always clear a stale banner artifact from a previous compile first, so a
    # now-clean (or non-banner) run can never re-inject an old banner.
    reset_banner(project_dir)

    if level == "off":
        print(
            f"  {DIM}[INFO]{NC} citation gate is disabled (level=off). "
            f"Set citations.level or --level to enable."
        )
        _summary()
        return 0

    report = log_fail if level == "error" else log_warn

    tex_paths = _resolve_tex_paths(project_dir, args.tex)
    cited_keys = extract_cited_keys(_load_text(tex_paths))
    if not cited_keys:
        log_warn("no \\cite keys found in the scanned tex -- nothing to check.")
        log_detail(f"scanned: {len(tex_paths)} tex file(s)")
        _summary()
        return 1 if FAIL_COUNT > 0 else 0

    bib_paths = resolve_bib_paths(project_dir, tex_paths, args.bib)
    if not bib_paths:
        log_warn(
            "no bibliography resolved (no \\bibliography target found and no "
            "fallback bib exists) -- nothing to check."
        )
        _summary()
        return 1 if FAIL_COUNT > 0 else 0
    for bp in bib_paths:
        log_detail(f"reading bib: {bp}")

    # Merge entries across all resolved bibs; first occurrence of a key wins
    # (matches bibtex, which uses the first entry it sees for a key).
    entries = {}
    for bp in bib_paths:
        for key, fields in iter_bib_entries(
            bp.read_text(encoding="utf-8", errors="replace")
        ):
            entries.setdefault(key, fields)
    stubs, missing, no_doi = audit_citations(cited_keys, entries)

    if stubs:
        report(
            f"{len(stubs)} cited reference(s) are unresolved scholar stubs -- "
            f"replace with a real, verified source before compiling:"
        )
        for key, reason in stubs:
            log_detail(f"\\cite{{{key}}} -> STUB ({reason})")
        if level == "banner":
            # Accepted-risk draft mode: the compile PROCEEDS but a red page-1
            # banner (written here, injected by the flattener) makes the
            # unresolved citations impossible to miss. clew_unreachable stays
            # False until the clew-verified half is wired in.
            path = write_banner_tex(project_dir, stubs, clew_unreachable=False)
            log_detail(f"banner mode: wrote red page-1 banner -> {path}")
        else:
            log_detail(
                "fix: resolve each key via scitex-scholar (DOI + real metadata), "
                "or remove the citation. Override with citations.level if intended."
            )
    else:
        log_pass(f"all {len(cited_keys)} cited reference(s) are non-stub entries")

    # Missing entries and missing-DOI are informational (bibtex already flags
    # undefined citations; DOI-less entries are often legitimate). Never a FAIL.
    if missing:
        log_warn(f"{len(missing)} cited key(s) have no bibliography entry:")
        for key in missing:
            log_detail(f"\\cite{{{key}}} -> no entry in the resolved bib(s)")
    if no_doi:
        log_detail(
            f"note: {len(no_doi)} cited entry(ies) have no DOI (not a failure): "
            + ", ".join(no_doi[:10])
            + (" ..." if len(no_doi) > 10 else "")
        )

    _summary()
    return 1 if FAIL_COUNT > 0 else 0


def _summary():
    print()
    print(
        f"{BOLD}Summary:{NC} {GREEN}{PASS_COUNT} passed{NC}, "
        f"{YELLOW}{WARN_COUNT} warnings{NC}, {RED}{FAIL_COUNT} errors{NC}"
    )


if __name__ == "__main__":
    sys.exit(main())
