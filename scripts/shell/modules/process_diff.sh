#!/bin/bash
# -*- coding: utf-8 -*-
# ROLE: engine-vendored — DO NOT edit here. `scitex-writer update-project`
# overwrites this file on every re-vendor; fix it upstream in the
# scitex-writer package instead (local edits are lost, and update-project
# may set it read-only in the consumer workspace after vendoring).
# Timestamp: "2026-01-19 (ywatanabe)"
# File: ./scripts/shell/modules/process_diff.sh
# Description: Generate diff between current and previous git commit (or arbitrary commits)
#
# SUPERSEDED (2.29.0) — NOTHING ON THE COMPILE PATH CALLS THIS ANY MORE.
# The compile scripts now delegate the diff stage to the installed Python engine
# via `modules/run_python_pipeline.sh diff` (-> `scitex-writer compile diff`),
# which refuses to diff a version against itself instead of silently emitting an
# unmarked "nothing changed" PDF. Kept for one release cycle only.

ORIG_DIR="$(pwd)"
THIS_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ENGINES_DIR="${THIS_DIR}/engines"
LOG_PATH="$THIS_DIR/.$(basename "$0").log"
echo >"$LOG_PATH"

GRAY='\033[0;90m'
GREEN='\033[0;32m'
YELLOW='\033[0;33m'
RED='\033[0;31m'
NC='\033[0m'

echo_info() { echo -e "${GRAY}INFO: $1${NC}"; }
log_info() {
    if [ "${SCITEX_LOG_LEVEL:-1}" -ge 2 ]; then
        echo -e "  \033[0;90m→ $1\033[0m"
    fi
}
echo_success() { echo -e "${GREEN}SUCC: $1${NC}"; }
echo_warning() { echo -e "${YELLOW}WARN: $1${NC}"; }
echo_error() { echo -e "${RED}ERRO: $1${NC}"; }

# shellcheck source=/dev/null
source ./config/load_config.sh "$SCITEX_WRITER_DOC_TYPE"

# shellcheck source=/dev/null
source "$(dirname "${BASH_SOURCE[0]}")/command_switching.src"

touch "$LOG_PATH" >/dev/null 2>&1
echo
log_info "Running $0 ..."

# Get .tex content from a specific git commit
# Usage: get_tex_from_commit <commit> <tex_path>
get_tex_from_commit() {
    local commit="$1"
    local tex_path="$2"
    git show "${commit}:${tex_path}" 2>/dev/null
}

# Get the previous commit that modified the compiled .tex file
# Returns the commit hash, or empty if no previous commit
get_previous_commit() {
    local tex_path="$1"
    # Get the second-to-last commit that touched this file (skip HEAD)
    git log --format="%H" -n 2 -- "$tex_path" 2>/dev/null | tail -n 1
}

# Create a temporary file with .tex content from a git commit
# Usage: create_temp_tex_from_commit <commit> <tex_path>
# Returns: path to temp file
create_temp_tex_from_commit() {
    local commit="$1"
    local tex_path="$2"
    local temp_file
    temp_file=$(mktemp --suffix=.tex)

    if get_tex_from_commit "$commit" "$tex_path" >"$temp_file" 2>/dev/null; then
        echo "$temp_file"
    else
        rm -f "$temp_file"
        echo ""
    fi
}

# latexdiff names its two inputs in the header (`%DIF DEL <file> <mtime>` /
# `%DIF ADD <file> <mtime>`). The old side is a mktemp file, so the header
# carried a build-host path (e.g. /home/<user>/.cache/tmp/tmp.XXXX.tex) into
# the tracked *_diff.tex. Name each side by commit and project-relative path
# instead; the mtime stays. Only the first DEL and ADD header lines are touched.
portable_diff_header() {
    local diff_tex="$1"
    local old_label="$2"
    local new_label="$3"
    local tmp
    tmp="$(mktemp)" || return 1
    OLD_LABEL="$old_label" NEW_LABEL="$new_label" awk '
        NR <= 20 && /^%DIF (DEL|ADD) / && !seen[$2]++ {
            label = ($2 == "DEL") ? ENVIRON["OLD_LABEL"] : ENVIRON["NEW_LABEL"]
            rest = substr($0, length("%DIF DEL ") + 1)
            sub(/^[^ \t]+/, "", rest)
            print "%DIF " $2 " " label rest
            next
        }
        { print }
    ' "$diff_tex" >"$tmp" && cat "$tmp" >"$diff_tex"
    local rc=$?
    rm -f "$tmp"
    return $rc
}

# Get short commit hash for display
get_short_hash() {
    local commit="${1:-HEAD}"
    git rev-parse --short=7 "$commit" 2>/dev/null || echo "unknown"
}

take_diff_tex() {
    local diff_from="${SCITEX_DIFF_FROM:-}"
    local diff_to="${SCITEX_DIFF_TO:-HEAD}"

    log_info "    Creating diff document..."

    if [ ! -f "$SCITEX_WRITER_COMPILED_TEX" ]; then
        echo_warning "    $SCITEX_WRITER_COMPILED_TEX not found."
        return 1
    fi

    # Determine the "from" commit
    local previous_tex=""
    local old_hash=""
    local new_hash=""

    if [ -n "$diff_from" ]; then
        # Explicit --diff-from specified
        old_hash=$(get_short_hash "$diff_from")
        previous_tex=$(create_temp_tex_from_commit "$diff_from" "$SCITEX_WRITER_COMPILED_TEX")
    else
        # Default: diff from last commit
        local prev_commit
        prev_commit=$(get_previous_commit "$SCITEX_WRITER_COMPILED_TEX")
        if [ -n "$prev_commit" ]; then
            old_hash=$(get_short_hash "$prev_commit")
            previous_tex=$(create_temp_tex_from_commit "$prev_commit" "$SCITEX_WRITER_COMPILED_TEX")
        fi
    fi

    # Determine the "to" version
    if [ "$diff_to" = "HEAD" ]; then
        new_hash=$(get_short_hash HEAD)
        # Check for uncommitted changes
        if ! git diff --quiet HEAD -- 2>/dev/null; then
            new_hash="${new_hash}+"
        fi
    else
        new_hash=$(get_short_hash "$diff_to")
    fi

    # If no previous version found, use current as both (no diff)
    if [ -z "$previous_tex" ] || [ ! -f "$previous_tex" ]; then
        echo_warning "    No previous version found in git history"
        echo_warning "    Creating empty diff (current vs current)"
        previous_tex="$SCITEX_WRITER_COMPILED_TEX"
        old_hash="none"
    fi

    # Get latexdiff command
    local latexdiff_cmd
    latexdiff_cmd=$(get_cmd_latexdiff "$ORIG_DIR")

    if [ -z "$latexdiff_cmd" ]; then
        echo_error "    latexdiff not found (native, module, or container)"
        [ -f "$previous_tex" ] && [ "$previous_tex" != "$SCITEX_WRITER_COMPILED_TEX" ] && rm -f "$previous_tex"
        return 1
    fi

    # Run latexdiff
    $latexdiff_cmd \
        --encoding=utf8 \
        --type=UNDERLINE \
        --disable-citation-markup \
        --append-safecmd="cite,cite,citet" \
        "$previous_tex" "$SCITEX_WRITER_COMPILED_TEX" 2> >(grep -v 'gocryptfs not found' | grep -v 'Wide character in print' >&2) >"$SCITEX_WRITER_DIFF_TEX"

    # Cleanup temp file
    [ -f "$previous_tex" ] && [ "$previous_tex" != "$SCITEX_WRITER_COMPILED_TEX" ] && rm -f "$previous_tex"

    if [ -f "$SCITEX_WRITER_DIFF_TEX" ] && [ -s "$SCITEX_WRITER_DIFF_TEX" ]; then
        portable_diff_header "$SCITEX_WRITER_DIFF_TEX" \
            "${old_hash}:${SCITEX_WRITER_COMPILED_TEX#./}" \
            "${new_hash}:${SCITEX_WRITER_COMPILED_TEX#./}"
        echo_success "    $SCITEX_WRITER_DIFF_TEX created (${old_hash} → ${new_hash})"

        # Add signature with git commit metadata
        if [ -f "./scripts/shell/modules/add_diff_signature.sh" ]; then
            # shellcheck source=/dev/null
            source ./scripts/shell/modules/add_diff_signature.sh
            add_diff_signature "$SCITEX_WRITER_DIFF_TEX" "$old_hash" "$new_hash"
        fi

        return 0
    else
        echo_warning "    $SCITEX_WRITER_DIFF_TEX not created or is empty"
        return 1
    fi
}

compile_diff_tex() {
    log_info "    Compiling diff document..."

    local tex_file="$SCITEX_WRITER_DIFF_TEX"

    # shellcheck source=/dev/null
    source "${ENGINES_DIR}/compile_tectonic.sh"
    # shellcheck source=/dev/null
    source "${ENGINES_DIR}/compile_latexmk.sh"
    # shellcheck source=/dev/null
    source "${ENGINES_DIR}/compile_3pass.sh"

    local engine="${SCITEX_WRITER_SELECTED_ENGINE:-latexmk}"

    # Set timeout for diff compilation to prevent infinite loops
    # latexdiff output can cause latexmk to loop endlessly on complex changes
    export SCITEX_WRITER_COMPILE_TIMEOUT="${SCITEX_WRITER_DIFF_TIMEOUT:-120}"
    log_info "    Using engine: $engine (diff timeout: ${SCITEX_WRITER_COMPILE_TIMEOUT}s)"

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
        echo_warning "    Unknown engine '$engine', using latexmk"
        compile_with_latexmk "$tex_file"
        ;;
    esac
    local result=$?

    unset SCITEX_WRITER_COMPILE_TIMEOUT

    if [ $result -ne 0 ]; then
        echo_warning "    Diff PDF not generated. Use --no_diff to skip."
        echo_warning "    To increase timeout: export SCITEX_WRITER_DIFF_TIMEOUT=300"
    fi

    return $result
}

cleanup() {
    local compile_result=${1:-1}
    local pdf_basename
    pdf_basename=$(basename "$SCITEX_WRITER_DIFF_PDF")
    local pdf_in_logs="${LOG_DIR}/${pdf_basename}"

    if [ -f "$pdf_in_logs" ]; then
        mv "$pdf_in_logs" "$SCITEX_WRITER_DIFF_PDF"
        echo_info "    Moved PDF: $pdf_in_logs -> $SCITEX_WRITER_DIFF_PDF"
    fi

    if [ "$compile_result" -ne 0 ]; then
        echo_error "    Diff PDF compilation failed (exit code: $compile_result)"
        # Remove stale PDF from previous compilation to avoid false positive
        [ -f "$SCITEX_WRITER_DIFF_PDF" ] && rm -f "$SCITEX_WRITER_DIFF_PDF"
        return 1
    fi

    if [ -f "$SCITEX_WRITER_DIFF_PDF" ]; then
        local size
        size=$(du -h "$SCITEX_WRITER_DIFF_PDF" | cut -f1)
        echo_success "    $SCITEX_WRITER_DIFF_PDF ready (${size})"
        sleep 1
    else
        echo_error "    $SCITEX_WRITER_DIFF_PDF not created despite successful compilation"
        return 1
    fi
}

main() {
    local start_time compile_result=1
    start_time=$(date +%s)

    if take_diff_tex; then
        compile_diff_tex
        compile_result=$?
    fi

    cleanup $compile_result
    echo_info "    Total time: $(($(date +%s) - start_time))s"
}

main "$@"

# EOF
