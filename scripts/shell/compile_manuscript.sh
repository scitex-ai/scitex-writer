#!/bin/bash
# -*- coding: utf-8 -*-
# ROLE: engine-vendored — DO NOT edit here. `scitex-writer update-project`
# overwrites this file on every re-vendor; fix it upstream in the
# scitex-writer package instead (local edits are lost, and update-project
# may set it read-only in the consumer workspace after vendoring).
# Timestamp: "2025-11-11 06:58:09 (ywatanabe)"
# File: ./scripts/shell/compile_manuscript.sh

# shellcheck disable=SC1091  # Don't follow sourced files

export ORIG_DIR
ORIG_DIR="$(pwd)"
THIS_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
LOG_PATH="$THIS_DIR/.$(basename "$0").log"
echo >"$LOG_PATH"

# Resolve project root from script location (safe for nested repos)
# Allow override via SCITEX_WRITER_PROJECT_ROOT (the retired unprefixed name is
# still read for one migration cycle, so it overrides here too)
PROJECT_ROOT="${SCITEX_WRITER_PROJECT_ROOT:-${PROJECT_ROOT:-$(cd "$THIS_DIR/../.." && pwd)}}"
export PROJECT_ROOT
# Both names go out: the refreshed vendored helpers read the prefixed name, and
# a workspace whose helpers have not been refreshed yet still reads this one.
export SCITEX_WRITER_PROJECT_ROOT="$PROJECT_ROOT"

# Change to project root to ensure relative paths work
cd "$PROJECT_ROOT" || exit 1

# Timestamp tracking
STAGE_START_TIME=0
COMPILATION_START_TIME=$(date +%s)

# New logging functions (clean format)
log_stage_start() {
    local stage_name="$1"
    STAGE_START_TIME=$(date +%s)
    echo -e "\033[0;34m▸\033[0m \033[1m${stage_name}\033[0m"
}

log_stage_end() {
    local stage_name="$1"
    local end_time
    end_time=$(date +%s)
    local elapsed=$((end_time - STAGE_START_TIME))
    echo -e "\033[0;32m✓\033[0m ${stage_name} \033[0;90m(${elapsed}s)\033[0m"
}

log_success() {
    echo -e "  \033[0;32m✓\033[0m $1"
}

log_warning() {
    echo -e "  \033[0;33m⚠\033[0m $1"
}

log_error() {
    echo -e "  \033[0;31m✗\033[0m $1"
}

log_info() {
    if [ "${SCITEX_LOG_LEVEL:-1}" -ge 2 ]; then
        echo -e "  \033[0;90m→ $1\033[0m"
    fi
}

# Compatibility aliases
echo_success() { log_success "$1"; }
echo_warning() { log_warning "$1"; }
echo_error() { log_error "$1"; }
echo_info() { log_info "$1"; }
echo_header() { log_stage_start "$1"; }

# Configurations
export SCITEX_WRITER_DOC_TYPE="manuscript"
source "$PROJECT_ROOT/config/load_config.sh" "$SCITEX_WRITER_DOC_TYPE"
echo

# Log
touch "$LOG_PATH" >/dev/null 2>&1
mkdir -p "$LOG_DIR" && touch "$SCITEX_WRITER_GLOBAL_LOG_FILE"

# Shell options
set -e
set -o pipefail

# Deafult values for arguments
do_p2t=false
no_figs=false
no_tables=false
do_verbose=false
do_crop_tif=false
export do_force=false # Reserved for force-rebuild logic; exported so --force flag is visible to sub-scripts
no_diff=false
draft_mode=false
dark_mode=${SCITEX_WRITER_DARK_MODE:-false}
clew_overlay=false
# Set when the PDF stage promoted a real PDF despite a non-zero engine exit.
# Drives the WITH WARNINGS banner and the script's exit 3.
compile_warned=false

# Colors for usage output
GRAY='\033[0;90m'
BOLD_CYAN='\033[1;36m'
GREEN='\033[0;32m'
YELLOW='\033[0;33m'
NC='\033[0m'

# --help text lives in modules/usage_manuscript.sh (defines usage()).
# shellcheck source=/dev/null
source "$PROJECT_ROOT/scripts/shell/modules/usage_manuscript.sh"

parse_arguments() {
    while [[ "$#" -gt 0 ]]; do
        # Normalize option: replace underscores with hyphens for matching
        local normalized_opt
        normalized_opt=$(echo "$1" | tr '_' '-')

        case $normalized_opt in
        -h | --help) usage ;;
        -p2t | --ppt2tif) do_p2t=true ;;
        -nf | --no-figs) no_figs=true ;;
        -nt | --no-tables) no_tables=true ;;
        -nd | --no-diff) no_diff=true ;;
        -d | --draft) draft_mode=true ;;
        -dm | --dark-mode) dark_mode=true ;;
        -c | --crop-tif) do_crop_tif=true ;;
        -v | --verbose) do_verbose=true ;;
        -q | --quiet) do_verbose=false ;;
        --force) do_force=true ;;
        --clew-overlay) clew_overlay=true ;;
        *)
            echo "Unknown option: $1"
            usage
            ;;
        esac
        shift
    done
}

main() {
    parse_arguments "$@"

    # Log command options
    options_display=""
    $do_p2t && options_display="${options_display} --ppt2tif"
    $no_figs && options_display="${options_display} --no_figs"
    $no_tables && options_display="${options_display} --no_tables"
    $no_diff && options_display="${options_display} --no_diff"
    $draft_mode && options_display="${options_display} --draft"
    $dark_mode && options_display="${options_display} --dark_mode"
    $do_crop_tif && options_display="${options_display} --crop_tif"
    $do_verbose && options_display="${options_display} --verbose"
    $clew_overlay && options_display="${options_display} --clew-overlay"

    # Show options only in verbose mode
    if [ "${SCITEX_LOG_LEVEL:-1}" -ge 2 ] && [ -n "$options_display" ]; then
        log_info "Options:$options_display"
    fi

    # Verbosity
    export SCITEX_WRITER_VERBOSE_PDFLATEX=$do_verbose
    export SCITEX_WRITER_VERBOSE_BIBTEX=$do_verbose

    # Draft mode (single-pass compilation)
    export SCITEX_WRITER_DRAFT_MODE=$draft_mode

    # Dark mode (black background, white text)
    export SCITEX_WRITER_DARK_MODE=$dark_mode

    # Clew overlay (--clew-overlay): an alias onto the clew presentation master
    # switch. `on` makes render_clew_toggles.py enable the provenance marks +
    # badge/legend/signature/explainer, so \vclaim marks color by clew verdict
    # with zero author edits. Only set when requested — never clobber an
    # existing SCITEX_WRITER_CLEW_PRESENTATION coming from config/env when off.
    if [ "$clew_overlay" = true ]; then
        export SCITEX_WRITER_CLEW_PRESENTATION=on
    fi

    # Refuse to compile on a Spartan login node (prohibited heavy compute) —
    # fail loud with the srun hint BEFORE the toolchain probe, which would
    # otherwise mis-report the login-node guard's [BLOCKED] as "pdflatex broken".
    "$PROJECT_ROOT/scripts/shell/modules/check_spartan_login.sh" || exit 1

    # Check dependencies
    log_stage_start "Dependency Check"
    "$PROJECT_ROOT/scripts/shell/modules/check_dependancy_commands.sh"
    log_stage_end "Dependency Check"

    # Provenance / symlink checks (paper_symlink, media_provenance) at their
    # configured severity -- an error-level violation aborts before compile work
    # (off/warn never block).
    log_stage_start "Provenance Checks"
    if ! "$PROJECT_ROOT/scripts/shell/modules/run_provenance_checks.sh"; then
        log_error "Provenance check failed (a check is set to error and found a violation)"
        exit 1
    fi
    log_stage_end "Provenance Checks"

    # Regenerate claims_rendered.tex from claims.json (\vclaim SSoT) so a stale
    # file can never ship outdated values; fails loud if rendering errors.
    log_stage_start "Claims Render"
    if ! "$PROJECT_ROOT/scripts/shell/modules/render_claims.sh"; then
        log_error "Claims render failed (claims.json present but rendering errored) -- fix claims.json; compiling would ship a stale claims_rendered.tex"
        exit 1
    fi
    log_stage_end "Claims Render"

    # Emit clew_rendered.tex from clew's runtime claims.json (JSON->TeX; clew is
    # renderer-agnostic) so the clew presentation layer has its data. No-op when
    # clew has no export; fails loud if the export is present but malformed.
    log_stage_start "Clew Render"
    if ! "$PROJECT_ROOT/scripts/shell/modules/render_clew.sh"; then
        log_error "Clew render failed (clew claims.json present but rendering errored) -- fix .scitex/clew/runtime/claims.json; compiling would ship a stale clew_rendered.tex"
        exit 1
    fi
    log_stage_end "Clew Render"

    # Merge bibliography files if multiple exist
    log_stage_start "Bibliography Merge"
    "$PROJECT_ROOT/scripts/shell/modules/merge_bibliographies.sh"
    log_stage_end "Bibliography Merge"

    # Apply citation style from config
    log_stage_start "Citation Style"
    "$PROJECT_ROOT/scripts/shell/modules/apply_citation_style.sh"
    log_stage_end "Citation Style"

    # Run independent processing in parallel for speed
    log_stage_start "Asset Processing"

    # Create temp files for parallel job outputs
    local temp_dir
    temp_dir=$(mktemp -d)
    local fig_log="$temp_dir/figures.log"
    local tbl_log="$temp_dir/tables.log"
    local wrd_log="$temp_dir/words.log"

    # Figures/tables delegate to the INSTALLED scitex-writer Python engine
    # (run_python_pipeline.sh); the shell modules they replace shipped silent
    # bugs (math escaping, multi-panel figures emitted as panel-a, no-op crop).
    (
        "$PROJECT_ROOT/scripts/shell/modules/run_python_pipeline.sh" figures "$no_figs" "$do_p2t" "$do_verbose" "$do_crop_tif" >"$fig_log" 2>&1
        echo $? >"$temp_dir/fig_exit"
    ) &
    local fig_pid=$!

    (
        "$PROJECT_ROOT/scripts/shell/modules/run_python_pipeline.sh" tables "$no_tables" >"$tbl_log" 2>&1
        echo $? >"$temp_dir/tbl_exit"
    ) &
    local tbl_pid=$!

    # Wait for figures and tables to finish before counting
    wait $fig_pid $tbl_pid

    # Run word count after figures/tables are ready (needs compiled files)
    "$PROJECT_ROOT/scripts/shell/modules/count_words.sh" >"$wrd_log" 2>&1
    echo $? >"$temp_dir/wrd_exit"

    # Display outputs only in verbose mode
    if [ "${SCITEX_LOG_LEVEL:-1}" -ge 2 ]; then
        log_info "Figure Processing:"
        sed 's/^/    /' "$fig_log"

        log_info "Table Processing:"
        sed 's/^/    /' "$tbl_log"

        log_info "Word Count:"
        sed 's/^/    /' "$wrd_log"
    fi

    # Check exit codes
    local fig_exit
    local tbl_exit
    local wrd_exit
    fig_exit=$(cat "$temp_dir/fig_exit")
    tbl_exit=$(cat "$temp_dir/tbl_exit")
    wrd_exit=$(cat "$temp_dir/wrd_exit")

    # Extract summary lines for normal mode
    if [ "${SCITEX_LOG_LEVEL:-1}" -lt 2 ]; then
        # Show only key results (remove file paths from grep output)
        # "Compiled N figures/tables" is the Python engine's summary wording.
        grep -hE "(figures compiled|tables compiled|Compiled [0-9]+ (figures|tables)|Word counts updated)" "$fig_log" "$tbl_log" "$wrd_log" 2>/dev/null | sed 's/^/  /' || true
    fi

    rm -rf "$temp_dir"

    # Fail if any job failed
    if [ "$fig_exit" -ne 0 ] || [ "$tbl_exit" -ne 0 ] || [ "$wrd_exit" -ne 0 ]; then
        log_error "Asset processing failed (fig=$fig_exit, tbl=$tbl_exit, wrd=$wrd_exit)"
        exit 1
    fi

    log_stage_end "Asset Processing"

    # Compile documents
    log_stage_start "TeX Compilation (Structure)"
    "$PROJECT_ROOT/scripts/shell/modules/compilation_structure_tex_to_compiled_tex.sh"
    log_stage_end "TeX Compilation (Structure)"

    # Engine Selection
    log_stage_start "Engine Selection"
    source "$PROJECT_ROOT/scripts/shell/modules/select_compilation_engine.sh"

    # Get engine from config or default to auto
    SELECTED_ENGINE="${SCITEX_WRITER_ENGINE:-auto}"

    if [ "$SELECTED_ENGINE" = "auto" ]; then
        # Auto-detection: try engines in order
        SELECTED_ENGINE=$(auto_detect_engine)
        echo_info "Auto-detected engine: $SELECTED_ENGINE"
    else
        # Explicit selection: verify availability
        if ! verify_engine "$SELECTED_ENGINE" >/dev/null 2>&1; then
            echo_warning "Requested engine '$SELECTED_ENGINE' not available"
            echo_info "Falling back to auto-detection..."
            SELECTED_ENGINE=$(auto_detect_engine)
            echo_info "Selected engine: $SELECTED_ENGINE"
        else
            echo_info "Using requested engine: $SELECTED_ENGINE"
        fi
    fi

    # Export for downstream modules
    export SCITEX_WRITER_SELECTED_ENGINE="$SELECTED_ENGINE"
    echo_info "$(get_engine_info "$SELECTED_ENGINE")"
    log_stage_end "Engine Selection"

    # TeX to PDF. Three outcomes, three behaviours:
    #   0 -> clean.
    #   3 -> a VALID PDF (pages > 0) was produced and promoted, but the engine
    #        exited non-zero — typically a non-fatal bibtex error on a stub entry
    #        (latexmk exit 12). Discarding a good manuscript over a warning-grade
    #        bib problem is worse than shipping it with a warning, so KEEP GOING —
    #        but remember: the banner says WITH WARNINGS and this script exits 3.
    #   * -> FAIL LOUD: the PDF was NOT (re)created (engine failure, or a pdfTeX
    #        Fatal error that produced NO PDF). Never exit 0 with only a printed
    #        ERRO, or callers treat a stale/absent PDF as a fresh success.
    log_stage_start "PDF Generation"
    pdf_status=0
    "$PROJECT_ROOT/scripts/shell/modules/compilation_compiled_tex_to_compiled_pdf.sh" || pdf_status=$?
    if [ "$pdf_status" -eq 3 ]; then
        compile_warned=true
        log_warning "PDF was produced and promoted, but the engine exited non-zero (above)."
    elif [ "$pdf_status" -ne 0 ]; then
        log_error "PDF generation failed — manuscript.pdf was not (re)created. Aborting."
        exit 1
    fi
    log_stage_end "PDF Generation"

    # Post-compile verification: FAIL LOUD on a deficient PDF (figures
    # referenced but not embedded, log deficiency signals). off/warn never
    # block. Catches a false-success compile that exits 0 with a broken PDF.
    log_stage_start "Compile Verification"
    if ! "$PROJECT_ROOT/scripts/shell/modules/run_compile_verification.sh"; then
        log_error "Compile verification failed — the PDF is deficient (see above). Aborting."
        exit 1
    fi
    log_stage_end "Compile Verification"

    # Post-compile overflow check: surface off-page content (wide tables/figures,
    # over-tall pages) AUTOMATICALLY from the LaTeX .log, so overflow no longer
    # needs a manual `scitex-writer check-overflow` call. warn (default) reports
    # and continues; error blocks; off is a loud no-op. A missing .log is
    # reported, not fatal.
    log_stage_start "Overflow Check"
    if ! "$PROJECT_ROOT/scripts/shell/modules/run_overflow_check.sh"; then
        log_error "Overflow check failed — content overflows the page (overflow.level=error). Aborting."
        exit 1
    fi
    log_stage_end "Overflow Check"

    # Manuscript Hints feed (ADVISORY): aggregate the signals the compile
    # already produced (undefined \ref/\cite in the log, unverified clew claims)
    # into .scitex/writer/hints.json — the data layer the writer UI's Details
    # pane renders as quiet inline hints ("the paper reacts to your work").
    # Runs BEFORE Cleanup so the log + claims are still present. NEVER fatal:
    # a hints feed must not break a compile.
    log_stage_start "Manuscript Hints"
    "${SCITEX_WRITER_PYTHON:-python3}" \
        "$PROJECT_ROOT/scripts/python/manuscript_hints.py" "$PROJECT_ROOT" \
        || echo_warning "Manuscript hints feed skipped (non-fatal)"
    log_stage_end "Manuscript Hints"

    # Diff (skip if --no_diff). The Python diff engine REFUSES to diff a version
    # against itself; a failing diff is loud but never aborts the compile.
    if [ "$no_diff" = false ]; then
        log_stage_start "Diff Generation"
        if ! "$PROJECT_ROOT/scripts/shell/modules/run_python_pipeline.sh" diff; then
            log_warning "Diff generation failed (above); PDF unaffected. Use --no_diff to skip."
        fi
        log_stage_end "Diff Generation"
    else
        echo_info "Skipping diff generation (--no_diff specified)"
    fi

    # Versioning (Python archive engine; a dirty tree is skipped, not archived)
    log_stage_start "Archive/Versioning"
    "$PROJECT_ROOT/scripts/shell/modules/run_python_pipeline.sh" archive
    log_stage_end "Archive/Versioning"

    # Cleanup
    log_stage_start "Cleanup"
    "$PROJECT_ROOT/scripts/shell/modules/cleanup.sh"
    log_stage_end "Cleanup"

    # Final steps
    log_stage_start "Directory Tree"
    "$PROJECT_ROOT/scripts/shell/modules/custom_tree.sh"
    log_stage_end "Directory Tree"

    # Final summary. A run that promoted a PDF despite a non-zero engine exit is
    # NOT a clean pass: it gets a yellow WITH WARNINGS banner and exit 3, so the
    # difference is visible to a human AND to a caller reading $?.
    echo ""
    local final_time
    final_time=$(date +%s)
    local total_compilation_time=$((final_time - COMPILATION_START_TIME))
    if [ "$compile_warned" = true ]; then
        echo -e "\033[1;33m━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\033[0m"
        echo -e "\033[1;33m  Compilation Complete — WITH WARNINGS\033[0m"
        echo -e "\033[0;33m  The PDF is usable but the engine reported an error\033[0m"
        echo -e "\033[0;33m  (usually a bibtex stub/duplicate entry). FIX BEFORE SUBMISSION.\033[0m"
    else
        echo -e "\033[1;32m━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\033[0m"
        echo -e "\033[1;32m  Compilation Complete\033[0m"
    fi
    echo -e "\033[0;32m  Total time: ${total_compilation_time}s\033[0m"
    echo -e "\033[0;32m  Output: $SCITEX_WRITER_COMPILED_PDF\033[0m"
    echo -e "\033[0;90m  Log: $SCITEX_WRITER_GLOBAL_LOG_FILE\033[0m"
    if [ "$compile_warned" = true ]; then
        echo -e "\033[1;33m━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\033[0m"
        echo ""
        return 3
    fi
    echo -e "\033[1;32m━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\033[0m"
    echo ""
}

main "$@" 2>&1 | tee -a "$LOG_PATH" "$SCITEX_WRITER_GLOBAL_LOG_FILE"

# EOF
