#!/bin/bash
# -*- coding: utf-8 -*-
# ROLE: engine-vendored — DO NOT edit here. `scitex-writer update-project`
# overwrites this file on every re-vendor; fix it upstream in the
# scitex-writer package instead (local edits are lost, and update-project
# may set it read-only in the consumer workspace after vendoring).
# Timestamp: "2025-11-11 23:12:00 (ywatanabe)"
# File: ./scripts/shell/modules/engines/compile_tectonic.sh
# Tectonic compilation engine

THIS_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

# Source command switching for command detection
source "${THIS_DIR}/../command_switching.src"

compile_with_tectonic() {
    local tex_file="$1"
    local pdf_file="${tex_file%.tex}.pdf"

    echo_info "    Using Tectonic engine"

    # Get tectonic command
    local tectonic_cmd=$(get_cmd_tectonic)
    if [ -z "$tectonic_cmd" ]; then
        echo_error "    Tectonic not available"
        return 1
    fi

    # Build tectonic options
    # --keep-intermediates: the .aux carries the \vclaim position records that
    # emit_claim_anchors.py turns into <pdf stem>.pdf-anchors.json.
    local opts="--keep-logs --keep-intermediates"

    # Output directory (use configured LOG_DIR for clean separation)
    # Tectonic requires absolute paths for --outdir
    local abs_log_dir="$(cd "$(dirname "$LOG_DIR")" && pwd)/$(basename "$LOG_DIR")"
    opts="$opts --outdir=$abs_log_dir"

    # Tectonic resolves \input / \includegraphics against the directory of the
    # .tex it compiles, not the working directory. The generated .tex names
    # files relative to the project root (./01_manuscript/...), the base every
    # other engine resolves from, so put the project root (cwd) on tectonic's
    # search path -- on the command line, never as an absolute path written
    # into the tracked .tex.
    opts="$opts -Z search-path=$(pwd)"

    # Incremental mode (use cache)
    if [ "$SCITEX_WRITER_TECTONIC_INCREMENTAL" = "true" ]; then
        # Set cache directory
        if [ -n "$SCITEX_WRITER_TECTONIC_CACHE_DIR" ]; then
            export TECTONIC_CACHE_DIR="$SCITEX_WRITER_TECTONIC_CACHE_DIR"
            echo_info "    Using cache: $TECTONIC_CACHE_DIR"
        fi
    fi

    # Bundle directory (offline mode)
    if [ -n "$SCITEX_WRITER_TECTONIC_BUNDLE_DIR" ] && [ -d "$SCITEX_WRITER_TECTONIC_BUNDLE_DIR" ]; then
        opts="$opts --bundle=$SCITEX_WRITER_TECTONIC_BUNDLE_DIR"
        echo_info "    Using offline bundle: $SCITEX_WRITER_TECTONIC_BUNDLE_DIR"
    fi

    # Reruns (limit compilation passes to avoid excessive reruns)
    # Default to 1 rerun (2 total passes) which is sufficient for most documents
    # Can be overridden with SCITEX_WRITER_TECTONIC_RERUNS environment variable
    local reruns="${SCITEX_WRITER_TECTONIC_RERUNS:-1}"
    opts="$opts --reruns=$reruns"

    # Verbosity
    if [ "$SCITEX_WRITER_VERBOSE_TECTONIC" != "true" ]; then
        opts="$opts --print=error"
    fi

    # Use relative path for tex file to maintain proper working directory
    # Tectonic will run from current directory (project root) to resolve relative image paths

    # Run compilation
    local start=$(date +%s)
    echo_info "    Running: $tectonic_cmd $opts $tex_file"

    # Optional timeout (set by diff compilation to prevent infinite loops)
    local timeout_prefix=""
    if [ -n "${SCITEX_WRITER_COMPILE_TIMEOUT:-}" ]; then
        timeout_prefix="timeout ${SCITEX_WRITER_COMPILE_TIMEOUT}"
        echo_info "    Timeout: ${SCITEX_WRITER_COMPILE_TIMEOUT}s"
    fi

    # Run tectonic with relative path (maintains project root as working directory)
    local output=$($timeout_prefix $tectonic_cmd $opts "$tex_file" 2>&1)
    local exit_code=$?

    # Check for timeout (exit code 124)
    if [ $exit_code -eq 124 ]; then
        echo_warning "    Compilation timed out after ${SCITEX_WRITER_COMPILE_TIMEOUT}s"
        return 1
    fi

    local end=$(date +%s)

    # Check result
    if [ $exit_code -eq 0 ]; then
        echo_success "    Tectonic compilation: $(($end - $start))s"
        return 0
    else
        echo_error "    Tectonic compilation failed (exit code: $exit_code)"

        # Show errors if verbose or on failure
        if [ "$SCITEX_WRITER_VERBOSE_TECTONIC" = "true" ] || [ $exit_code -ne 0 ]; then
            echo "$output" | grep -i "error\|warning" | head -10
        fi

        # If in auto mode, signal to try fallback
        if [ "$SCITEX_WRITER_ENGINE" = "auto" ]; then
            return 2 # Special code: try next engine
        else
            return 1 # Fatal error
        fi
    fi
}

# Export function
export -f compile_with_tectonic

# EOF
