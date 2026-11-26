#!/bin/bash
# -*- coding: utf-8 -*-
# ROLE: engine-vendored — DO NOT edit here. `scitex-writer update-project`
# overwrites this file on every re-vendor; fix it upstream in the
# scitex-writer package instead (local edits are lost, and update-project
# may set it read-only in the consumer workspace after vendoring).
# Timestamp: "2025-11-11 23:18:00 (ywatanabe)"
# File: ./scripts/shell/modules/compilation_compiled_tex_to_compiled_pdf.sh
# Main compilation orchestrator - delegates to engine-specific modules

# shellcheck disable=SC2034  # ORIG_DIR exported from standard module header
ORIG_DIR="$(pwd)"
THIS_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ENGINES_DIR="${THIS_DIR}/engines"
LOG_PATH="$THIS_DIR/.$(basename "$0").log"
echo >"$LOG_PATH"

# shellcheck disable=SC2034  # GIT_ROOT exported from standard module header
GIT_ROOT="$(git rev-parse --show-toplevel 2>/dev/null)"

GRAY='\033[0;90m'
GREEN='\033[0;32m'
YELLOW='\033[0;33m'
RED='\033[0;31m'
NC='\033[0m' # No Color

echo_info() { echo -e "${GRAY}INFO: $1${NC}"; }
log_info() {
    if [ "${SCITEX_LOG_LEVEL:-1}" -ge 2 ]; then
        echo -e "  \033[0;90m→ $1\033[0m"
    fi
}
echo_success() { echo -e "${GREEN}SUCC: $1${NC}"; }
echo_warning() { echo -e "${YELLOW}WARN: $1${NC}"; }
echo_error() { echo -e "${RED}ERRO: $1${NC}"; }
echo_header() { echo_info "=== $1 ==="; }
# ---------------------------------------

# Configurations
# shellcheck source=/dev/null
source ./config/load_config.sh "$SCITEX_WRITER_DOC_TYPE"

# Source engine implementations (use absolute paths to avoid directory confusion)
# shellcheck source=/dev/null
source "${ENGINES_DIR}/compile_tectonic.sh"
# shellcheck source=/dev/null
source "${ENGINES_DIR}/compile_latexmk.sh"
# shellcheck source=/dev/null
source "${ENGINES_DIR}/compile_3pass.sh"

# Logging
touch "$LOG_PATH" >/dev/null 2>&1
echo
log_info "Running $0 ..."

compiled_tex_to_pdf() {
    log_info "    Converting $SCITEX_WRITER_COMPILED_TEX to PDF..."

    # Fail-fast ceiling: enforce a hard compile timeout by DEFAULT so a wedged
    # LaTeX/bibtex run (e.g. a terminal prompt -interaction=nonstopmode cannot
    # answer) NEVER hangs silently. Every engine already honors
    # SCITEX_WRITER_COMPILE_TIMEOUT via a `timeout` prefix + exit-124 check;
    # setting it here at the single dispatch point makes the ceiling opt-OUT
    # rather than opt-in (previously only diff-compile set it). Diff-compile's
    # own (shorter) value is preserved -- `:=` defaults only when UNSET. Opt out
    # with 0/off/none/false (mapped to empty so the engines skip the prefix).
    : "${SCITEX_WRITER_COMPILE_TIMEOUT:=${SCITEX_WRITER_COMPILE_TIMEOUT_DEFAULT:-300}}"
    case "${SCITEX_WRITER_COMPILE_TIMEOUT}" in
    0 | off | none | false | disabled) SCITEX_WRITER_COMPILE_TIMEOUT="" ;;
    esac
    export SCITEX_WRITER_COMPILE_TIMEOUT

    local tex_file="$SCITEX_WRITER_COMPILED_TEX"
    local engine="${SCITEX_WRITER_SELECTED_ENGINE:-3pass}"

    log_info "    Selected engine: $engine"

    # Dispatch to engine-specific implementation
    case "$engine" in
    tectonic)
        compile_with_tectonic "$tex_file"
        ;;
    latexmk)
        compile_with_latexmk "$tex_file"
        ;;
    3pass)
        compile_with_3pass "$tex_file"
        ;;
    *)
        echo_error "    Unknown compilation engine: $engine"
        echo_info "    Falling back to 3-pass compilation"
        compile_with_3pass "$tex_file"
        ;;
    esac

    local ret=$?

    # If compilation failed in auto mode, try next engine
    if [ $ret -eq 2 ] && [ "$SCITEX_WRITER_ENGINE" = "auto" ]; then
        echo_warning "    Engine '$engine' failed, trying fallback..."
        # Note: Fallback logic handled by compile_manuscript.sh
        # This is just a placeholder for future enhancement
    fi

    return $ret
}

# Ground-truth page count of the PDF just produced by the engine. pdfTeX writes
# "Output written on <path> (N pages, ...)" to the .log ONLY when it finalized a
# PDF this run, so that line is the per-run source of truth (immune to a stale
# PDF left by a previous successful compile). Falls back to pdfinfo. Prints the
# page count, or 0 if it cannot be established.
pdf_produced_pagecount() {
    local pdf_path="$1"
    local log_file="${LOG_DIR}/$(basename "${pdf_path%.pdf}").log"
    local pages=""
    if [ -f "$log_file" ]; then
        pages=$(grep -oE "Output written on [^(]*\([0-9]+ page" "$log_file" 2>/dev/null | grep -oE "[0-9]+ page" | grep -oE "^[0-9]+" | tail -1)
    fi
    if [ -z "$pages" ] && command -v pdfinfo >/dev/null 2>&1; then
        pages=$(pdfinfo "$pdf_path" 2>/dev/null | awk '/^Pages:/ {print $2}')
    fi
    echo "${pages:-0}"
}

# Exit code for "a PDF WAS produced, but the engine exited non-zero". It is
# deliberately NOT 0: the artifact is usable and must be kept, but the run is not
# clean and every caller -- human or machine -- has to be able to tell the two
# apart. compile_{manuscript,supplementary,revision}.sh keep going on a 3, finish
# the pipeline, and exit 3 themselves; scitex_writer._compile._runner maps it to
# success=True + a loud warning after re-verifying pages>0 in Python.
EXIT_PROMOTED_WITH_WARNINGS=3

# Claim positions: <pdf stem>.pdf-anchors.json beside the PDF, built from the
# \vclaim position records the final LaTeX run wrote to the .aux (see
# scripts/python/emit_claim_anchors.py). A PDF reader uses it to box each claim
# on its page. Loud but not fatal: the PDF itself is fine without it.
emit_claim_anchors() {
    local pdf_file="$1"
    local aux_file="$2"
    local python="${SCITEX_WRITER_PYTHON:-python3}"
    if ! "$python" "${THIS_DIR}/../../python/emit_claim_anchors.py" \
        --aux "$aux_file" --pdf "$pdf_file"; then
        echo_warning "    Claim anchors not written for $pdf_file (see above); PDF readers cannot box its claims."
    fi
}

cleanup() {
    local compile_result=${1:-1}
    local promoted_with_warnings=false

    # Use fallback if SCITEX_WRITER_COMPILED_PDF is not set or empty
    local pdf_file="${SCITEX_WRITER_COMPILED_PDF}"
    if [ -z "$pdf_file" ]; then
        pdf_file="./01_manuscript/manuscript.pdf"
    fi

    # PDF is generated in LOG_DIR, move to final location
    local pdf_basename
    pdf_basename=$(basename "$pdf_file")
    local pdf_in_logs="${LOG_DIR}/${pdf_basename}"

    # Track whether a PDF was produced by THIS run (present in logs/). A stale
    # PDF from a previous compile is NOT fresh, so it can never be mistaken for
    # a valid new output below.
    local fresh_pdf=false
    if [ -f "$pdf_in_logs" ]; then
        # Move PDF from logs/ to final location
        mv "$pdf_in_logs" "$pdf_file"
        fresh_pdf=true
        log_info "    Moved PDF: $pdf_in_logs -> $pdf_file"
    fi

    if [ "$compile_result" -ne 0 ]; then
        # A non-zero engine exit is NOT always fatal: latexmk returns non-zero
        # on a non-fatal bibtex warning (e.g. a malformed/stub .bib entry ->
        # "repeated entry" / "skipping whatever remains" -> exit 12) even when
        # pdfTeX finalized a complete PDF. Losing a valid multi-page PDF over
        # one stub reference is worse than shipping it with a warning. So: if a
        # PDF was freshly produced this run with pages>0, PROMOTE it and
        # downgrade to WARN; otherwise fail loud (delete stale, return 1).
        local produced_pages=0
        if [ "$fresh_pdf" = true ] && [ -f "$pdf_file" ]; then
            produced_pages=$(pdf_produced_pagecount "$pdf_file")
        fi
        if [ "$fresh_pdf" = true ] && [ "${produced_pages:-0}" -gt 0 ] 2>/dev/null; then
            echo_warning "    Engine exited non-zero (code: $compile_result) but a valid PDF was produced (${produced_pages} pages)."
            echo_warning "    Promoting $pdf_file anyway — this is usually a non-fatal bib/citation warning (e.g. a stub entry)."
            echo_warning "    → Fix before submission: inspect ${LOG_DIR}/${pdf_basename%.pdf}.{log,blg} for the offending entry."
            # Fall through to the promotion/symlink path below, but REMEMBER that
            # this run was not clean: cleanup() returns 3, never 0, so the compile
            # cannot be reported as a clean pass.
            promoted_with_warnings=true
        else
            echo_error "    PDF compilation failed (exit code: $compile_result)"
            # Remove stale PDF from previous compilation to avoid false positive
            [ -f "$pdf_file" ] && rm -f "$pdf_file"
            return 1
        fi
    fi

    # FRESHNESS GATE: a compile is a success only if THIS run actually
    # (re)created the PDF. Every engine writes the PDF into LOG_DIR and the block
    # above MOVES it to $pdf_file, setting fresh_pdf=true. If fresh_pdf is still
    # false here, no PDF was produced this run -- so any $pdf_file present is
    # STALE from a PREVIOUS compile. This happens when an engine returns exit 0
    # without emitting output (e.g. a silent latexmk/tectonic no-op, or a
    # container that failed to mount) yet an old PDF is still on disk. Reporting
    # that stale PDF as success is a silent failure: the user believes they got a
    # fresh PDF but it is the old one. Fail loud instead. (The 3-pass engine also
    # guards this at the engine level via an mtime check; this is the central
    # backstop that additionally covers latexmk / tectonic and the finalization
    # point where the PDF is promoted.)
    if [ "$fresh_pdf" != true ]; then
        echo_error "    PDF was not (re)created this run: $pdf_file"
        echo_error "      The build likely failed -- a stale PDF from a previous run is present."
        echo_error "      Refusing to pass off a stale PDF as a fresh compile."
        echo_error "      Inspect the real error in: ${LOG_DIR}/${pdf_basename%.pdf}.log"
        # Remove the stale PDF so downstream gates never treat it as valid output.
        [ -f "$pdf_file" ] && rm -f "$pdf_file"
        return 1
    fi

    if [ -f "$pdf_file" ]; then
        local size
        size=$(du -h "$pdf_file" | cut -f1)
        echo_success "    $pdf_file ready (${size})"

        emit_claim_anchors "$pdf_file" "${LOG_DIR}/${pdf_basename%.pdf}.aux"

        # Create/update stable symlink to latest archive version (prevents corruption during compilation)
        local latest_path="${SCITEX_WRITER_ROOT_DIR}/${SCITEX_WRITER_DOC_TYPE}-latest.pdf"

        # Find the latest archived version (highest version number).
        # Glob directly + filter _diff.pdf via bash so we avoid `ls | grep` (SC2010).
        local archive_dir="${SCITEX_WRITER_VERSIONS_DIR}"
        local latest_archive=""
        local _cand
        local _candidates=()
        for _cand in "$archive_dir"/"${SCITEX_WRITER_DOC_TYPE}"_v[0-9]*.pdf; do
            [ -e "$_cand" ] || continue
            case "$_cand" in *_diff.pdf) continue ;; esac
            _candidates+=("$_cand")
        done
        if [ ${#_candidates[@]} -gt 0 ]; then
            latest_archive=$(printf '%s\n' "${_candidates[@]}" | sort -V | tail -1)
        fi

        if [ -n "$latest_archive" ]; then
            # Create relative symlink to archive
            ln -sf "archive/$(basename "$latest_archive")" "$latest_path"
            echo_success "    Symlink updated: $latest_path -> archive/$(basename "$latest_archive")"
        else
            # User-confirmed fallback: current PDF if no archive exists yet
            ln -sf "$(basename "$pdf_file")" "$latest_path"
            echo_success "    Symlink updated: $latest_path -> $(basename "$pdf_file") (no archive yet)"
        fi
        # Note: For rsync, use -L flag to follow symlinks: rsync -avL ...

        sleep 1

        if [ "$promoted_with_warnings" = true ]; then
            return "$EXIT_PROMOTED_WITH_WARNINGS"
        fi
        return 0
    else
        echo_error "    $pdf_file was not created despite successful compilation"
        return 1
    fi
}

main() {
    compiled_tex_to_pdf
    local compile_result=$?
    cleanup "$compile_result"
}

# Only auto-run when executed directly, not when sourced (so tests can source
# the file and exercise pdf_produced_pagecount / cleanup in isolation).
if [ "${BASH_SOURCE[0]}" = "${0}" ]; then
    main
fi

# EOF
