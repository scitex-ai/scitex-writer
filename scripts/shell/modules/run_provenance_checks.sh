#!/bin/bash
# -*- coding: utf-8 -*-
# ROLE: engine-vendored — DO NOT edit here. `scitex-writer update-project`
# overwrites this file on every re-vendor; fix it upstream in the
# scitex-writer package instead (local edits are lost, and update-project
# may set it read-only in the consumer workspace after vendoring).
# File: scripts/shell/modules/run_provenance_checks.sh
#
# Run the config-driven pre-compile checks at their RESOLVED severity
# (off|warn|error via CLI/env/config). Each underlying script
# (scripts/python/check_{paper_symlink,media_provenance,caption_footnote,
#  clew_verify}.py) resolves its own level and exits non-zero ONLY at
# error-level with a violation. So:
#   off   -> no-op (exit 0)
#   warn  -> reports, exit 0 (does NOT block the compile)
#   error -> exit 1 (blocks the compile, fail-loud)
# This is what makes `paper_symlink: error` / `media_provenance: error` /
# `caption_footnote: error` actually enforce at compile time -- previously the
# compile ran none of them. caption_footnote defaults to error (a \footnote in
# a \caption{} is always a fatal compile pattern). clew_verify is the
# provenance GATE (ADR-0021): it re-verifies every clew-registered claim
# against its bound source and defaults to error for research projects
# (.scitex/dev/config.yaml project-type: research), off otherwise. citations is
# the CITATION GATE: it fails the build when a cited reference is an unresolved
# scholar stub (auto-generated placeholder), also error for research / warn
# otherwise -- the compiler-owns half of the citation->clew verification
# contract (a stub \cite can never reach a compiled research manuscript).
# figure_media is the FIGURE-MEDIA GATE: it fails the build when a figure is
# DECLARED (a caption .tex) but has NO rendered media asset, so the compile can
# no longer silently substitute a "Missing Figure" placeholder. It runs BEFORE
# process_figures.sh (which creates the placeholder), so at error-level the
# placeholder path is never reached; defaults to error for research projects,
# warn otherwise (the public template ships example captions without media).
# ref_integrity is the REFERENCE-INTEGRITY GATE: it validates every figure/table
# \ref, every \cite against the merged bib, and every supple- xref against the
# supplement .aux, reporting ALL problems at once (file:line) BEFORE the
# expensive LaTeX run -- catching ?-refs and undefined \cites up front instead
# of buried in the log. Runs automatically (opt-out = level=off); defaults to
# error for research projects, warn otherwise (a normal single-target compile in
# a non-research project still succeeds with a loud warning).
# table_decimals is the DECIMAL-CONSISTENCY safety-net (card
# writer-table-decimal-alignment SECONDARY): it reads the COMPILED table .tex and
# warns when a numeric column's cells disagree on decimal places. The PRIMARY fix
# (PR #185) makes csv_to_latex.py per-column decimal-pad, but that auto-pad runs
# ONLY on the pandas backend -- the external csv2latex binary (chosen BEFORE
# pandas) and the AWK fallback do not pad, and hand-authored .tex tables are never
# converted. Reading the compiled output means it never re-flags what the auto-pad
# already normalized; it fires exactly on the un-normalized paths. Defaults to
# warn (a safety net; the auto-pad is the systemic prevention).
# citation_trust is the CITATION-TRUSTWORTHINESS check: it resolves every cited
# entry against the real bibliographic record via scitex-scholar
# (verify_cites -> CrossRef/OpenAlex/arXiv/SemanticScholar) and flags citations
# that are not provably real (hallucinated -> error, unverified/stub/unlinked ->
# warning). Defaults to WARN -- a network-dependent check must never block a
# compile by default -- and FAILS LOUDLY (never silently passes) when it cannot
# run: no scitex-scholar extra, no network, or an unresolvable bib is reported as
# "citations could NOT be verified", never as a pass. Verdicts are cached in
# .scitex/writer/runtime/citation_trust.json (scholar has no cache of its own),
# keyed by cite key + bib-entry content hash, so repeated compiles are network-free
# until an entry actually changes.
# claim_values is the VALUE-VS-SOURCE gate: for every \vclaim registered with
# source_keys (a JSON Pointer into a json/yaml source, or a csv/tsv cell) it
# re-reads the value from the claim's source file and compares it with the
# claim value within the declared (or precision-implied) tolerance -- the
# value-level complement of clew_verify's hash check. Claims come from the
# scitex-clew store (no JSON fallback; an unreachable store fails loudly).
# Defaults to error.
#
# Returns the worst exit code across the checks (0 unless a check errored).

THIS_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# Honor the PROJECT_ROOT the caller (compile_*.sh) already resolved + exported;
# fall back to the install-relative root when run standalone.
PROJECT_ROOT="${PROJECT_ROOT:-$(cd "$THIS_DIR/../../.." && pwd)}"
PY="${SCITEX_WRITER_PYTHON:-python3}"

rc=0
for chk in check_paper_symlink check_media_provenance check_figure_media check_ref_integrity check_caption_footnote check_table_decimals check_clew_verify check_clew_completeness check_claim_values check_citations check_citation_trust check_version_freshness; do
    script="$THIS_DIR/../../python/${chk}.py"
    [ -f "$script" ] || continue
    "$PY" "$script" "$PROJECT_ROOT" || rc=$?
done

exit "$rc"
