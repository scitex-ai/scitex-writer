#!/bin/bash
# -*- coding: utf-8 -*-
# ROLE: engine-vendored — DO NOT edit here. `scitex-writer update-project`
# overwrites this file on every re-vendor; fix it upstream in the
# scitex-writer package instead (local edits are lost, and update-project
# may set it read-only in the consumer workspace after vendoring).
# Timestamp: "2025-09-27 15:10:53 (ywatanabe)"
# File: ./paper/scripts/shell/compile_revision

# shellcheck disable=SC1091  # Don't follow sourced files

export ORIG_DIR
ORIG_DIR="$(pwd)"
THIS_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
LOG_PATH="$THIS_DIR/.$(basename "$0").log"

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

GRAY='\033[0;90m'
GREEN='\033[0;32m'
YELLOW='\033[0;33m'
RED='\033[0;31m'
BOLD_CYAN='\033[1;36m'
NC='\033[0m' # No Color

echo_info() { echo -e "${GRAY}INFO: $1${NC}"; }
echo_success() { echo -e "${GREEN}SUCC: $1${NC}"; }
echo_warning() { echo -e "${YELLOW}WARN: $1${NC}"; }
echo_error() { echo -e "${RED}ERRO: $1${NC}"; }
echo_header() { echo_info "=== $1 ==="; }
# ---------------------------------------

# Timestamp tracking functions
STAGE_START_TIME=0
COMPILATION_START_TIME=$(date +%s)

log_stage_start() {
    local stage_name="$1"
    STAGE_START_TIME=$(date +%s)
    local timestamp
    timestamp=$(date '+%H:%M:%S')
    echo_info "[$timestamp] Starting: $stage_name"
}

log_stage_end() {
    local stage_name="$1"
    local end_time
    end_time=$(date +%s)
    local elapsed=$((end_time - STAGE_START_TIME))
    local total_elapsed=$((end_time - COMPILATION_START_TIME))
    local timestamp
    timestamp=$(date '+%H:%M:%S')
    echo_success "[$timestamp] Completed: $stage_name (${elapsed}s elapsed, ${total_elapsed}s total)"
}

################################################################################
# Description: Compiles revision response document
# Processes reviewer comments and author responses with diff highlighting
################################################################################

# Configurations
export SCITEX_WRITER_DOC_TYPE="revision"
source ./config/load_config.sh "$SCITEX_WRITER_DOC_TYPE"
echo

# Log
touch "$LOG_PATH" >/dev/null 2>&1
mkdir -p "$LOG_DIR" && touch "$SCITEX_WRITER_GLOBAL_LOG_FILE"

# Shell options
set -e
set -o pipefail

# Default values for arguments
no_figs=false
no_tables=false
do_verbose=false
draft_mode=false
dark_mode=${SCITEX_WRITER_DARK_MODE:-false}
clew_overlay=false
# Set when the PDF stage promoted a real PDF despite a non-zero engine exit.
compile_warned=false

usage() {
    echo ""
    echo -e "${BOLD_CYAN}━━━ compile_revision.sh ━━━${NC}"
    echo -e "${GRAY}Compile revision response letter${NC}"
    echo ""
    echo -e "${BOLD_CYAN}━━━ Structure ━━━${NC}"
    echo -e "  ${GREEN}03_revision/${NC}"
    echo -e "    contents/"
    echo -e "      ${YELLOW}introduction.tex${NC}    ${GRAY}# Response letter introduction${NC}"
    echo -e "      ${YELLOW}conclusion.tex${NC}      ${GRAY}# Response letter conclusion${NC}"
    echo -e "      editor/               ${GRAY}# Editor comments & responses${NC}"
    echo -e "        ${YELLOW}E_01_comments.tex${NC}   ${GRAY}# Copy of editor's email/comment${NC}"
    echo -e "        ${YELLOW}E_01_response.tex${NC}   ${GRAY}# Author's response${NC}"
    echo -e "        ${YELLOW}E_01_revision.tex${NC}   ${GRAY}# Actual manuscript changes (with \\\\DIFadd{}, \\\\DIFdel{})${NC}"
    echo -e "      reviewer1/            ${GRAY}# Reviewer 1 comments & responses${NC}"
    echo -e "        ${YELLOW}R1_01_comments.tex${NC}  ${GRAY}# Copy of reviewer's comment${NC}"
    echo -e "        ${YELLOW}R1_01_response.tex${NC}  ${GRAY}# Author's response${NC}"
    echo -e "        ${YELLOW}R1_01_revision.tex${NC}  ${GRAY}# Actual manuscript changes${NC}"
    echo -e "      reviewer2/            ${GRAY}# Reviewer 2 comments & responses${NC}"
    echo -e "        ${YELLOW}R2_01_comments.tex${NC}  ${GRAY}# Copy of reviewer's comment${NC}"
    echo -e "        ${YELLOW}R2_01_response.tex${NC}  ${GRAY}# Author's response${NC}"
    echo -e "        ${YELLOW}R2_01_revision.tex${NC}  ${GRAY}# Actual manuscript changes${NC}"
    echo -e "    ${GRAY}revision.pdf${NC}        ${GRAY}# Output${NC}"
    echo ""
    echo -e "${BOLD_CYAN}━━━ File Types ━━━${NC}"
    echo -e "  ${GREEN}*_comments.tex${NC}  Copy of reviewer/editor email or comment"
    echo -e "  ${GREEN}*_response.tex${NC}  Author's response explaining changes"
    echo -e "  ${GREEN}*_revision.tex${NC}  Actual manuscript changes with diff markup:"
    echo -e "    ${GRAY}\\\\DIFadd{added text}${NC}     ${GRAY}# Shows added text${NC}"
    echo -e "    ${GRAY}\\\\DIFdel{deleted text}${NC}   ${GRAY}# Shows deleted text${NC}"
    echo ""
    echo -e "${BOLD_CYAN}━━━ Editable Files ━━━${NC}"
    echo -e "${GREEN}00_shared:${NC}"
    echo -e "  ${GRAY}$PROJECT_ROOT/00_shared/${NC}title.tex"
    echo -e "  ${GRAY}$PROJECT_ROOT/00_shared/${NC}authors.tex"
    echo -e "  ${GRAY}$PROJECT_ROOT/00_shared/${NC}keywords.tex"
    echo -e "  ${GRAY}$PROJECT_ROOT/00_shared/${NC}journal_name.tex"
    echo -e "  ${GRAY}$PROJECT_ROOT/00_shared/bib_files/${NC}*.bib"
    echo ""
    echo -e "${GREEN}03_revision:${NC}"
    echo -e "  ${GRAY}$PROJECT_ROOT/03_revision/contents/${NC}introduction.tex"
    echo -e "  ${GRAY}$PROJECT_ROOT/03_revision/contents/${NC}conclusion.tex"
    echo -e "  ${GRAY}$PROJECT_ROOT/03_revision/contents/editor/${NC}E_*_comments.tex"
    echo -e "  ${GRAY}$PROJECT_ROOT/03_revision/contents/editor/${NC}E_*_response.tex"
    echo -e "  ${GRAY}$PROJECT_ROOT/03_revision/contents/editor/${NC}E_*_revision.tex"
    echo -e "  ${GRAY}$PROJECT_ROOT/03_revision/contents/reviewer1/${NC}R1_*_comments.tex"
    echo -e "  ${GRAY}$PROJECT_ROOT/03_revision/contents/reviewer1/${NC}R1_*_response.tex"
    echo -e "  ${GRAY}$PROJECT_ROOT/03_revision/contents/reviewer1/${NC}R1_*_revision.tex"
    echo -e "  ${GRAY}$PROJECT_ROOT/03_revision/contents/reviewer2/${NC}R2_*_comments.tex"
    echo -e "  ${GRAY}$PROJECT_ROOT/03_revision/contents/reviewer2/${NC}R2_*_response.tex"
    echo -e "  ${GRAY}$PROJECT_ROOT/03_revision/contents/reviewer2/${NC}R2_*_revision.tex"
    echo ""
    echo -e "${BOLD_CYAN}━━━ Options ━━━${NC}"
    echo "  -nf,  --no_figs       Skip figure processing (~4s faster)"
    echo "  -nt,  --no_tables     Skip table processing (~4s faster)"
    echo "  -d,   --draft         Single-pass compilation (~5s faster)"
    echo "  -dm,  --dark_mode     Dark mode: black background, white text"
    echo "  -q,   --quiet         Minimal output"
    echo "  --clew-overlay        Color \\vclaim values by clew provenance status"
    echo "  -h,   --help          Show this help"
    echo ""
    echo -e "${GRAY}Note: Options accept both hyphens and underscores${NC}"
    echo -e "${GRAY}Note: Revision documents skip diff generation (changes shown inline)${NC}"
    echo ""
    echo -e "${BOLD_CYAN}━━━ Document Structure (base.tex) ━━━${NC}"
    echo -e "  ${GRAY}$PROJECT_ROOT/03_revision/${NC}base.tex"
    echo -e "  Controls section order via \\\\input{} commands:"
    echo -e "    ${GRAY}\\\\input{./03_revision/contents/${NC}introduction${GRAY}}${NC}"
    echo -e "    ${GRAY}\\\\input{./03_revision/contents/editor/${NC}E_01_comments${GRAY}}${NC}   ${GRAY}# Reviewer's comment${NC}"
    echo -e "    ${GRAY}\\\\input{./03_revision/contents/editor/${NC}E_01_response${GRAY}}${NC}   ${GRAY}# Your response${NC}"
    echo -e "    ${GRAY}\\\\input{./03_revision/contents/editor/${NC}E_01_revision${GRAY}}${NC}   ${GRAY}# Manuscript changes${NC}"
    echo -e "    ${GRAY}\\\\input{./03_revision/contents/reviewer1/${NC}R1_01_comments${GRAY}}${NC}"
    echo -e "    ${GRAY}\\\\input{./03_revision/contents/reviewer1/${NC}R1_01_response${GRAY}}${NC}"
    echo -e "    ${GRAY}\\\\input{./03_revision/contents/reviewer1/${NC}R1_01_revision${GRAY}}${NC}"
    echo -e "    ${GRAY}\\\\input{./03_revision/contents/${NC}conclusion${GRAY}}${NC}"
    echo -e "  To add/remove sections: edit base.tex \\\\input{} lines"
    echo -e "  Comment out with %% to disable a section"
    echo ""
    echo -e "${BOLD_CYAN}━━━ Managing Bibliography ━━━${NC}"
    echo -e "  Place .bib files in: ${YELLOW}$PROJECT_ROOT/00_shared/bib_files/${NC}"
    echo -e "  Multiple .bib files auto-merge with deduplication"
    echo -e "  Citation style: ${YELLOW}$PROJECT_ROOT/config/config_revision.yaml${NC}"
    echo -e "  Styles: ${GREEN}unsrtnat${NC}, ${GREEN}plainnat${NC}, ${GREEN}apalike${NC}, ${GREEN}IEEEtran${NC}, ${GREEN}naturemag${NC}"
    echo ""
    exit 0
}

parse_arguments() {
    while [[ "$#" -gt 0 ]]; do
        # Normalize option: replace underscores with hyphens for matching
        local normalized_opt
        normalized_opt=$(echo "$1" | tr '_' '-')

        case $normalized_opt in
        -h | --help) usage ;;
        -nf | --no-figs) no_figs=true ;;
        -nt | --no-tables) no_tables=true ;;
        -d | --draft) draft_mode=true ;;
        -dm | --dark-mode) dark_mode=true ;;
        --clew-overlay) clew_overlay=true ;;
        -v | --verbose) do_verbose=true ;;
        -q | --quiet) do_verbose=false ;;
        *)
            echo "Unknown option: $1"
            usage
            ;;
        esac
        shift
    done
}

{
    parse_arguments "$@"

    # Log command options
    options_display=""
    $no_figs && options_display="${options_display} --no_figs"
    $no_tables && options_display="${options_display} --no_tables"
    $draft_mode && options_display="${options_display} --draft"
    $dark_mode && options_display="${options_display} --dark_mode"
    $do_verbose && options_display="${options_display} --verbose"
    $clew_overlay && options_display="${options_display} --clew-overlay"
    echo_info "Running $0${options_display}..."

    # Verbosity
    export SCITEX_WRITER_VERBOSE_PDFLATEX=$do_verbose
    export SCITEX_WRITER_VERBOSE_BIBTEX=$do_verbose

    # Draft mode (single-pass compilation)
    export SCITEX_WRITER_DRAFT_MODE=$draft_mode

    # Dark mode (black background, white text)
    export SCITEX_WRITER_DARK_MODE=$dark_mode

    # Clew overlay (--clew-overlay): alias onto the clew presentation master
    # switch so \vclaim marks color by clew verdict. Only set when requested,
    # never clobbering an existing SCITEX_WRITER_CLEW_PRESENTATION when off.
    if [ "$clew_overlay" = true ]; then
        export SCITEX_WRITER_CLEW_PRESENTATION=on
    fi

    # Refuse to compile on a Spartan login node (prohibited heavy compute) —
    # fail loud with the srun hint before the toolchain probe.
    ./scripts/shell/modules/check_spartan_login.sh || exit 1

    # 1. Check dependencies
    log_stage_start "Dependency Check"
    if ! ./scripts/shell/modules/check_dependancy_commands.sh; then
        echo -e "${RED}ERRO: Dependency check failed${NC}"
        exit 1
    fi
    log_stage_end "Dependency Check"

    # Provenance / symlink checks at their configured severity (error blocks).
    log_stage_start "Provenance Checks"
    if ! ./scripts/shell/modules/run_provenance_checks.sh; then
        echo -e "${RED}ERRO: Provenance check failed (a check is set to error and found a violation)${NC}"
        exit 1
    fi
    log_stage_end "Provenance Checks"

    # Regenerate claims_rendered.tex from claims.json (\vclaim SSoT) so a stale
    # file can never ship outdated values; fails loud if rendering errors.
    log_stage_start "Claims Render"
    if ! ./scripts/shell/modules/render_claims.sh; then
        echo -e "${RED}ERRO: Claims render failed (claims.json present but rendering errored) -- fix claims.json; compiling would ship a stale claims_rendered.tex${NC}"
        exit 1
    fi
    log_stage_end "Claims Render"

    # 2. Merge bibliography files if multiple exist
    log_stage_start "Bibliography Merge"
    ./scripts/shell/modules/merge_bibliographies.sh
    log_stage_end "Bibliography Merge"

    # 3. Apply citation style from config
    log_stage_start "Citation Style"
    ./scripts/shell/modules/apply_citation_style.sh
    log_stage_end "Citation Style"

    # 3. Check revision structure
    log_stage_start "Revision Structure Check"
    echo_info "Checking revision response structure..."

    # Expected structure with simplified naming (allowing optional descriptive suffixes):
    # Editor: E_01_comments[_description].tex, E_01_response[_description].tex, ...
    # Reviewer1: R1_01_comments[_description].tex, R1_01_response[_description].tex, ...
    # Reviewer2: R2_01_comments[_description].tex, R2_01_response[_description].tex, ...
    # Examples:
    #   E_01_comments_about-methodology.tex
    #   R1_02_response_statistical-analysis.tex

    check_revision_files() {
        local dir="$1"
        local prefix="$2" # E, R1, or R2
        local name="$3"   # editor, reviewer1, reviewer2 for display

        if [ ! -d "$dir" ]; then
            echo -e "${YELLOW}WARN: Directory $dir not found${NC}"
            return 1
        fi

        echo -e "${BLUE}  Checking $name responses...${NC}"

        # Check for comment/response pairs with simplified naming (supporting descriptive suffixes)
        local found_files=0
        for comment_file in "$dir"/"${prefix}"_*_comments*.tex; do
            if [ -f "$comment_file" ]; then
                # Extract the base ID (e.g., E_01, R1_02)
                local base_id
                base_id=$(basename "$comment_file" | sed -E "s/(${prefix}_[0-9]+)_comments.*/\1/")

                # Look for corresponding response file (may have different description)
                local response_found=false
                for response_file in "$dir"/"${base_id}"_response*.tex; do
                    if [ -f "$response_file" ]; then
                        echo -e "${GREEN}    ✓ $(basename "$comment_file") & $(basename "$response_file")${NC}"
                        found_files=$((found_files + 1))
                        response_found=true
                        break
                    fi
                done

                if [ "$response_found" = false ]; then
                    echo -e "${YELLOW}    ⚠ Missing response for: $(basename "$comment_file")${NC}"
                fi
            fi
        done

        if [ $found_files -eq 0 ]; then
            echo -e "${YELLOW}    No comment/response pairs found in $dir${NC}"
        else
            echo -e "${GREEN}    Found $found_files comment/response pair(s)${NC}"
        fi

        return 0
    }

    # Check each reviewer directory with simplified prefixes
    check_revision_files "./03_revision/contents/editor" "E" "Editor"
    check_revision_files "./03_revision/contents/reviewer1" "R1" "Reviewer 1"
    check_revision_files "./03_revision/contents/reviewer2" "R2" "Reviewer 2"
    log_stage_end "Revision Structure Check"

    # Run independent processing in parallel for speed
    parallel_start=$(date +%s)
    timestamp=$(date '+%H:%M:%S')
    echo_info "[$timestamp] Starting: Parallel Processing (Figures, Tables)"

    # Create temp files for parallel job outputs
    temp_dir=$(mktemp -d)
    fig_log="$temp_dir/figures.log"
    tbl_log="$temp_dir/tables.log"

    # Figures/tables delegate to the INSTALLED scitex-writer Python engine.
    (
        ./scripts/shell/modules/run_python_pipeline.sh figures "$no_figs" false false false >"$fig_log" 2>&1
        echo $? >"$temp_dir/fig_exit"
    ) &
    fig_pid=$!

    (
        ./scripts/shell/modules/run_python_pipeline.sh tables "$no_tables" >"$tbl_log" 2>&1
        echo $? >"$temp_dir/tbl_exit"
    ) &
    tbl_pid=$!

    # Wait for all parallel jobs
    wait $fig_pid $tbl_pid

    # Display outputs in order
    echo_info "  Figure Processing:"
    sed 's/^/    /' "$fig_log"

    echo_info "  Table Processing:"
    sed 's/^/    /' "$tbl_log"

    # Check exit codes
    fig_exit=$(cat "$temp_dir/fig_exit")
    tbl_exit=$(cat "$temp_dir/tbl_exit")

    rm -rf "$temp_dir"

    # Fail if any job failed
    if [ "$fig_exit" -ne 0 ] || [ "$tbl_exit" -ne 0 ]; then
        echo_error "Parallel processing failed (fig=$fig_exit, tbl=$tbl_exit)"
        exit 1
    fi

    parallel_end=$(date +%s)
    parallel_elapsed=$((parallel_end - parallel_start))
    total_elapsed=$((parallel_end - COMPILATION_START_TIME))
    timestamp=$(date '+%H:%M:%S')
    echo_success "[$timestamp] Completed: Parallel Processing (${parallel_elapsed}s elapsed, ${total_elapsed}s total)"

    # Compile structure
    log_stage_start "TeX Compilation (Structure)"
    ./scripts/shell/modules/compilation_structure_tex_to_compiled_tex.sh
    log_stage_end "TeX Compilation (Structure)"

    # Compile to PDF. Exit 3 = a VALID PDF was produced and promoted but the
    # engine exited non-zero (non-fatal bibtex/stub error): keep the PDF, keep
    # going, and report WITH WARNINGS (exit 3) instead of a clean pass. Any other
    # non-zero = no PDF was (re)created -> FAIL LOUD.
    log_stage_start "PDF Generation"
    pdf_status=0
    ./scripts/shell/modules/compilation_compiled_tex_to_compiled_pdf.sh || pdf_status=$?
    if [ "$pdf_status" -eq 3 ]; then
        compile_warned=true
        echo_warning "PDF was produced and promoted, but the engine exited non-zero (above)."
    elif [ "$pdf_status" -ne 0 ]; then
        echo_error "PDF generation failed — revision.pdf was not (re)created. Aborting."
        exit 1
    fi
    log_stage_end "PDF Generation"

    # Post-compile verification: FAIL LOUD on a deficient PDF (off/warn never block).
    log_stage_start "Compile Verification"
    if ! ./scripts/shell/modules/run_compile_verification.sh; then
        echo_error "Compile verification failed — the PDF is deficient (see above). Aborting."
        exit 1
    fi
    log_stage_end "Compile Verification"

    # Post-compile overflow check: surface off-page content automatically from
    # the LaTeX .log (warn reports+continues, error blocks, off is a loud no-op;
    # a missing .log is reported, not fatal).
    log_stage_start "Overflow Check"
    if ! ./scripts/shell/modules/run_overflow_check.sh; then
        echo_error "Overflow check failed — content overflows the page (overflow.level=error). Aborting."
        exit 1
    fi
    log_stage_end "Overflow Check"

    # Skip diff generation for revision (revision document already shows changes inline)
    echo_info "Skipping diff generation (revision document shows changes inline)"

    # Archive (Python archive engine; a dirty tree is skipped, not archived)
    log_stage_start "Archive/Versioning"
    ./scripts/shell/modules/run_python_pipeline.sh archive
    log_stage_end "Archive/Versioning"

    # Cleanup
    log_stage_start "Cleanup"
    ./scripts/shell/modules/cleanup.sh
    log_stage_end "Cleanup"

    # Final steps
    log_stage_start "Directory Tree"
    ./scripts/shell/modules/custom_tree.sh
    log_stage_end "Directory Tree"

    # Logging
    echo

    final_time=$(date +%s)
    total_compilation_time=$((final_time - COMPILATION_START_TIME))
    echo_success "===================================================="
    echo_success "TOTAL COMPILATION TIME: ${total_compilation_time}s"
    echo_success "===================================================="
    echo_success "PDF: $SCITEX_WRITER_COMPILED_PDF"

    # A promoted-with-warnings run is not a clean pass — say so, and exit 3.
    if [ "$compile_warned" = true ]; then
        echo_warning "COMPLETED WITH WARNINGS — the PDF is usable but the engine"
        echo_warning "reported an error (usually a bibtex stub/duplicate entry)."
        exit 3
    fi
} 2>&1 | tee -a "$LOG_PATH" "$SCITEX_WRITER_GLOBAL_LOG_FILE"

# EOF
