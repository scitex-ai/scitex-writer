#!/bin/bash
# -*- coding: utf-8 -*-
# Test file for: compilation_compiled_tex_to_compiled_pdf.sh

THIS_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT_DIR="$(cd "$THIS_DIR/../../../.." && pwd)"
MODULE="$ROOT_DIR/scripts/shell/modules/compilation_compiled_tex_to_compiled_pdf.sh"

# Test counter
TESTS_RUN=0
TESTS_PASSED=0
TESTS_FAILED=0

# Colors
GREEN='\033[0;32m'
RED='\033[0;31m'
NC='\033[0m'

assert_eq() {
    local expected="$1"
    local actual="$2"
    local desc="${3:-}"
    ((TESTS_RUN++))
    if [ "$expected" = "$actual" ]; then
        echo -e "${GREEN}✓${NC} $desc"
        ((TESTS_PASSED++))
    else
        echo -e "${RED}✗${NC} $desc (expected '$expected', got '$actual')"
        ((TESTS_FAILED++))
    fi
}

# Source the module for its helper functions. The module guards main() behind a
# "run only when executed directly" check, so sourcing here does NOT trigger a
# compile. config/load_config.sh resolves from the repo root; its stderr is
# irrelevant to the function under test. We override LOG_DIR afterwards.
setup_module() {
    export SCITEX_WRITER_DOC_TYPE="${SCITEX_WRITER_DOC_TYPE:-manuscript}"
    cd "$ROOT_DIR" || return 1
    # shellcheck source=/dev/null
    source "$MODULE" >/dev/null 2>&1 || true
}

# pdf_produced_pagecount reads the engine .log "Output written on ... (N pages"
# line, which is the per-run source of truth for whether a valid PDF exists.
test_pagecount_from_log_multipage() {
    local tmp
    tmp="$(mktemp -d)"
    export LOG_DIR="$tmp"
    printf 'Output written on %s/manuscript.pdf (25 pages, 4602154 bytes).\n' "$tmp" >"$tmp/manuscript.log"
    local n
    n="$(pdf_produced_pagecount "$tmp/manuscript.pdf")"
    assert_eq "25" "$n" "pdf_produced_pagecount reads 25 pages from log"
    rm -rf "$tmp"
}

test_pagecount_from_log_single_page() {
    local tmp
    tmp="$(mktemp -d)"
    export LOG_DIR="$tmp"
    printf 'Output written on %s/manuscript.pdf (1 page, 1234 bytes).\n' "$tmp" >"$tmp/manuscript.log"
    local n
    n="$(pdf_produced_pagecount "$tmp/manuscript.pdf")"
    assert_eq "1" "$n" "pdf_produced_pagecount reads 1 page from log"
    rm -rf "$tmp"
}

test_pagecount_zero_when_no_output_line() {
    local tmp
    tmp="$(mktemp -d)"
    export LOG_DIR="$tmp"
    printf 'This is pdfTeX; a fatal error occurred, no PDF finalized.\n' >"$tmp/manuscript.log"
    local n
    n="$(pdf_produced_pagecount "$tmp/manuscript.pdf")"
    assert_eq "0" "$n" "pdf_produced_pagecount returns 0 when no Output-written line"
    rm -rf "$tmp"
}

test_pagecount_zero_when_no_log() {
    local tmp
    tmp="$(mktemp -d)"
    export LOG_DIR="$tmp"
    local n
    n="$(pdf_produced_pagecount "$tmp/manuscript.pdf")"
    assert_eq "0" "$n" "pdf_produced_pagecount returns 0 when log absent (no PDF, no pdfinfo target)"
    rm -rf "$tmp"
}

# FRESHNESS GATE regression: engine reports success (compile_result=0) but
# produced NO fresh PDF in LOG_DIR this run, while a STALE PDF from a previous
# compile still sits at the final location. cleanup() must FAIL LOUD (return 1)
# instead of passing off the stale PDF as a successful compile.
test_cleanup_fails_when_stale_pdf_and_no_fresh() {
    local tmp
    tmp="$(mktemp -d)"
    export LOG_DIR="$tmp/logs"
    mkdir -p "$LOG_DIR"
    export SCITEX_WRITER_COMPILED_PDF="$tmp/manuscript.pdf"
    printf 'STALE PDF from a previous run\n' >"$SCITEX_WRITER_COMPILED_PDF"
    # No manuscript.pdf inside LOG_DIR -> nothing produced this run.
    ( cleanup 0 ) >/dev/null 2>&1
    local rc=$?
    assert_eq "1" "$rc" "cleanup fails loud when success reported but no fresh PDF (stale present)"
    rm -rf "$tmp"
}

# The stale PDF must be REMOVED so downstream gates never treat it as valid.
test_cleanup_removes_stale_pdf_when_no_fresh() {
    local tmp
    tmp="$(mktemp -d)"
    export LOG_DIR="$tmp/logs"
    mkdir -p "$LOG_DIR"
    export SCITEX_WRITER_COMPILED_PDF="$tmp/manuscript.pdf"
    printf 'STALE PDF from a previous run\n' >"$SCITEX_WRITER_COMPILED_PDF"
    ( cleanup 0 ) >/dev/null 2>&1
    local present="yes"
    [ -f "$SCITEX_WRITER_COMPILED_PDF" ] || present="no"
    assert_eq "no" "$present" "cleanup removes the stale PDF when no fresh PDF was produced"
    rm -rf "$tmp"
}

# Positive control: a PDF freshly produced in LOG_DIR this run is promoted and
# cleanup() returns success (0).
test_cleanup_succeeds_when_fresh_pdf_produced() {
    local tmp
    tmp="$(mktemp -d)"
    export LOG_DIR="$tmp/logs"
    mkdir -p "$LOG_DIR"
    export SCITEX_WRITER_ROOT_DIR="$tmp"
    export SCITEX_WRITER_DOC_TYPE="manuscript"
    export SCITEX_WRITER_VERSIONS_DIR="$tmp/archive"
    export SCITEX_WRITER_COMPILED_PDF="$tmp/manuscript.pdf"
    # A PDF present in LOG_DIR == produced by THIS run.
    printf 'FRESH PDF produced this run\n' >"$LOG_DIR/manuscript.pdf"
    ( cleanup 0 ) >/dev/null 2>&1
    local rc=$?
    assert_eq "0" "$rc" "cleanup succeeds when a fresh PDF was produced in LOG_DIR this run"
    rm -rf "$tmp"
}

# Promotion writes <pdf stem>.pdf-anchors.json beside the PDF from the run's
# .aux. Regression: the emitter path was built from THIS_DIR at call time, which
# config/load_config.sh had reassigned, so a real compile only warned.
test_cleanup_writes_claim_anchors_beside_the_pdf() {
    local tmp
    tmp="$(mktemp -d)"
    export LOG_DIR="$tmp/logs"
    mkdir -p "$LOG_DIR"
    export SCITEX_WRITER_ROOT_DIR="$tmp"
    export SCITEX_WRITER_DOC_TYPE="manuscript"
    export SCITEX_WRITER_VERSIONS_DIR="$tmp/archive"
    export SCITEX_WRITER_COMPILED_PDF="$tmp/manuscript.pdf"
    printf 'FRESH PDF produced this run\n' >"$LOG_DIR/manuscript.pdf"
    printf '%s\n' \
        '\v@claimpos{acc}{1s}{1}{6578176}{39469056}{0.0pt}{345.0pt}{8.4pt}{3.6pt}' \
        '\v@claimpos{acc}{1e}{1}{9867264}{39469056}{0.0pt}{345.0pt}{8.4pt}{3.6pt}' \
        >"$LOG_DIR/manuscript.aux"
    ( cleanup 0 ) >/dev/null 2>&1
    local found="no"
    grep -q '"acc"' "$tmp/manuscript.pdf-anchors.json" 2>/dev/null && found="yes"
    assert_eq "yes" "$found" "cleanup writes manuscript.pdf-anchors.json with the claim from the .aux"
    rm -rf "$tmp"
}

# Run tests
main() {
    echo "Testing: compilation_compiled_tex_to_compiled_pdf.sh"
    echo "========================================"

    setup_module

    if ! declare -F pdf_produced_pagecount >/dev/null; then
        echo -e "${RED}✗${NC} could not source module / pdf_produced_pagecount undefined"
        exit 1
    fi

    test_pagecount_from_log_multipage
    test_pagecount_from_log_single_page
    test_pagecount_zero_when_no_output_line
    test_pagecount_zero_when_no_log
    test_cleanup_fails_when_stale_pdf_and_no_fresh
    test_cleanup_removes_stale_pdf_when_no_fresh
    test_cleanup_succeeds_when_fresh_pdf_produced
    test_cleanup_writes_claim_anchors_beside_the_pdf

    echo "========================================"
    echo "Results: $TESTS_PASSED/$TESTS_RUN passed"
    [ $TESTS_FAILED -gt 0 ] && exit 1
    exit 0
}

main "$@"

# EOF
