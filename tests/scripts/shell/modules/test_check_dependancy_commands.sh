#!/bin/bash
# -*- coding: utf-8 -*-
# Test file for: check_dependancy_commands.sh

THIS_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT_DIR="$(realpath "$THIS_DIR/../..")"

# Test counter
TESTS_RUN=0
TESTS_PASSED=0
TESTS_FAILED=0

# Colors
GREEN='\033[0;32m'
RED='\033[0;31m'
NC='\033[0m'

assert_success() {
    local cmd="$1"
    local desc="${2:-$cmd}"
    ((TESTS_RUN++))
    if eval "$cmd" > /dev/null 2>&1; then
        echo -e "${GREEN}✓${NC} $desc"
        ((TESTS_PASSED++))
    else
        echo -e "${RED}✗${NC} $desc"
        ((TESTS_FAILED++))
    fi
}

assert_file_exists() {
    local file="$1"
    ((TESTS_RUN++))
    if [ -f "$file" ]; then
        echo -e "${GREEN}✓${NC} File exists: $file"
        ((TESTS_PASSED++))
    else
        echo -e "${RED}✗${NC} File missing: $file"
        ((TESTS_FAILED++))
    fi
}

# Assert the command FAILS (returns non-zero) — the complement of
# assert_success, needed for "still required when unavailable" cases.
assert_failure() {
    local cmd="$1"
    local desc="${2:-$cmd}"
    ((TESTS_RUN++))
    if eval "$cmd" > /dev/null 2>&1; then
        echo -e "${RED}✗ (expected failure but passed) $desc"
        ((TESTS_FAILED++))
    else
        echo -e "${GREEN}✓${NC} $desc"
        ((TESTS_PASSED++))
    fi
}

# ---------------------------------------------------------------------------
# Deterministic contracts for the table-tool dependency guard (2.43.1).
#
# The real functions are EXTRACTED from the committed module at test time (not
# re-typed), so these regression-test the actual guard logic. Tool *absence* is
# made deterministic with a restricted PATH that has find/grep but no
# xlsx2csv/csv2latex and a python3 stub that always exits 1 (so
# `python3 -c "import xlsx2csv"` fails regardless of what the host python has).
# ---------------------------------------------------------------------------
MODULE="scripts/shell/modules/check_dependancy_commands.sh"
REPO_ROOT="$(realpath "$THIS_DIR/../../../..")"

# Extract one function body (single-line or multi-line) from the real module.
extract_fn() {
    local fn="$1"
    awk -v fn="$fn" '
        $0 ~ "^" fn "\\(\\) \\{" {
            print
            if ($0 ~ /\}$/) exit
            p=1; next
        }
        p && /^\}$/ { print; exit }
        p { print }
    ' "$REPO_ROOT/$MODULE"
}

# A PATH that has find/grep (needed by the guard) but NO table tools, plus a
# python3 stub whose import of xlsx2csv/csv2latex always fails.
restricted_path() {
    local bin
    bin=$(mktemp -d)
    ln -s "$(command -v find)" "$bin/find"
    ln -s "$(command -v grep)" "$bin/grep"
    printf '#!/bin/sh\nexit 1\n' > "$bin/python3"
    chmod +x "$bin/python3"
    echo "$bin"
}

# Load the real guard functions + color vars into this shell (run once in main).
load_module_functions() {
    RED='\033[0;31m'
    NC='\033[0m'
    PKG_MANAGER="apt"
    SUDO_PREFIX=""
    eval "$(extract_fn check_xlsx2csv)"
    eval "$(extract_fn check_csv2latex)"
    eval "$(extract_fn echo_error)"
}

# Contract 1: a table-less manuscript does NOT require xlsx2csv/csv2latex.
test_table_less_workspace_does_not_require_table_tools() {
    # Arrange
    local d rb
    d=$(mktemp -d); mkdir -p "$d/01_manuscript/contents"
    rb=$(restricted_path)
    # Act + Assert: with no table sources, the guard returns 0 (not required),
    # even though the tools are guaranteed absent under the restricted PATH.
    assert_success "( cd '$d' && PATH='$rb' && check_xlsx2csv >/dev/null 2>&1 )" \
        "table-less: check_xlsx2csv is NOT required"
    assert_success "( cd '$d' && PATH='$rb' && check_csv2latex >/dev/null 2>&1 )" \
        "table-less: check_csv2latex is NOT required"
    rm -rf "$d" "$rb"
}

# Contract 2: a workspace containing xlsx/xls/csv table sources STILL requires
# them when unavailable.
test_with_table_source_still_requires_tools_when_unavailable() {
    # Arrange
    local d rb
    d=$(mktemp -d); mkdir -p "$d/01_manuscript/contents/tables/caption_and_media"
    echo "1,2" > "$d/01_manuscript/contents/tables/caption_and_media/1_tab.csv"
    rb=$(restricted_path)
    # Act + Assert: a table source is present AND the tools are unavailable,
    # so the guard returns 1 (required) — it must not silently drop them.
    assert_failure "( cd '$d' && PATH='$rb' && check_xlsx2csv >/dev/null 2>&1 )" \
        "with-table: check_xlsx2csv IS required when absent"
    assert_failure "( cd '$d' && PATH='$rb' && check_csv2latex >/dev/null 2>&1 )" \
        "with-table: check_csv2latex IS required when absent"
    rm -rf "$d" "$rb"
}

# Contract 3: the missing-required-tools diagnostic reaches STDERR (so the
# Hub's stderr_tail can surface it) — not stdout.
test_missing_required_report_reaches_stderr_not_stdout() {
    # Arrange
    local out err
    # Act: capture stdout-only and stderr-only from the real echo_error.
    out=$(echo_error "Missing required tools:" 2>/dev/null)
    err=$(echo_error "Missing required tools:" 2>&1 1>/dev/null)
    # Assert: the message is on stderr and NOT on stdout.
    assert_success "[ -n '$err' ]" "echo_error writes to stderr"
    assert_success "[ -z '$out' ]" "echo_error writes nothing to stdout"
}

# Run tests
main() {
    echo "Testing: check_dependancy_commands.sh"
    echo "========================================"

    load_module_functions

    test_table_less_workspace_does_not_require_table_tools
    test_with_table_source_still_requires_tools_when_unavailable
    test_missing_required_report_reaches_stderr_not_stdout

    echo "========================================"
    echo "Results: $TESTS_PASSED/$TESTS_RUN passed"
    [ $TESTS_FAILED -gt 0 ] && exit 1
    exit 0
}

main "$@"

# --------------------------------------------------------------------------------
# Start of Source Code from: /home/ywatanabe/proj/scitex-writer/scripts/shell/modules/check_dependancy_commands.sh
# --------------------------------------------------------------------------------
# #!/bin/bash
# # -*- coding: utf-8 -*-
# # Timestamp: "2025-11-11 07:23:33 (ywatanabe)"
# # File: ./scripts/shell/modules/check_dependancy_commands.sh
# 
# ORIG_DIR="$(pwd)"
# THIS_DIR="$(cd $(dirname ${BASH_SOURCE[0]}) && pwd)"
# LOG_PATH="$THIS_DIR/.$(basename $0).log"
# echo > "$LOG_PATH"
# 
# GIT_ROOT="$(git rev-parse --show-toplevel 2>/dev/null)"
# 
# GRAY='\033[0;90m'
# GREEN='\033[0;32m'
# YELLOW='\033[0;33m'
# RED='\033[0;31m'
# NC='\033[0m' # No Color
# 
# echo_info() { echo -e "${GRAY}INFO: $1${NC}"; }
# log_info() {
#     if [ "${SCITEX_LOG_LEVEL:-1}" -ge 2 ]; then
#         echo -e "  \033[0;90m→ $1\033[0m"
#     fi
# }
# echo_success() { echo -e "${GREEN}SUCC: $1${NC}"; }
# echo_warning() { echo -e "${YELLOW}WARN: $1${NC}"; }
# echo_error() { echo -e "${RED}ERRO: $1${NC}"; }
# echo_header() { echo_info "=== $1 ==="; }
# # ---------------------------------------
# 
# # Don't clear log at start - timing info will be appended
# 
# # Configurations
# source ./config/load_config.sh $SCITEX_WRITER_DOC_TYPE
# 
# # Source the 00_shared LaTeX commands module
# source "$(dirname ${BASH_SOURCE[0]})/command_switching.src"
# log_info "Running ${BASH_SOURCE[0]}..."
# 
# 
# # Detect package manager
# detect_package_manager() {
#     if command -v apt &> /dev/null; then
#         echo "apt"
#     elif command -v yum &> /dev/null; then
#         echo "yum"
#     else
#         echo "unknown"
#     fi
# }
# 
# # Check if sudo is available
# has_sudo() {
#     if command -v sudo &> /dev/null; then
#         return 0
#     else
#         return 1
#     fi
# }
# 
# PKG_MANAGER=$(detect_package_manager)
# SUDO_PREFIX=""
# if has_sudo; then
#     SUDO_PREFIX="sudo "
# fi
# 
# # Standalone checker for each tool
# check_pdflatex() {
#     local cmd=$(get_cmd_pdflatex "$ORIG_DIR")
#     if [ -z "$cmd" ]; then
#         echo "- pdflatex"
#         if [ "$PKG_MANAGER" = "apt" ]; then
#             echo "    - ${SUDO_PREFIX}apt install texlive-latex-base"
#         elif [ "$PKG_MANAGER" = "yum" ]; then
#             echo "    - ${SUDO_PREFIX}yum install texlive-latex"
#         fi
#         echo "    - Or use: module load texlive"
#         echo "    - Or use: apptainer/singularity with texlive container"
#         return 1
#     fi
#     return 0
# }
# 
# check_bibtex() {
#     local cmd=$(get_cmd_bibtex "$ORIG_DIR")
#     if [ -z "$cmd" ]; then
#         echo "- bibtex"
#         if [ "$PKG_MANAGER" = "apt" ]; then
#             echo "    - ${SUDO_PREFIX}apt install texlive-bibtex-extra"
#         elif [ "$PKG_MANAGER" = "yum" ]; then
#             echo "    - ${SUDO_PREFIX}yum install texlive-bibtex"
#         fi
#         echo "    - Or use: module load texlive"
#         echo "    - Or use: apptainer/singularity with texlive container"
#         return 1
#     fi
#     return 0
# }
# 
# check_latexdiff() {
#     local cmd=$(get_cmd_latexdiff "$ORIG_DIR")
#     if [ -z "$cmd" ]; then
#         echo "- latexdiff"
#         if [ "$PKG_MANAGER" = "apt" ]; then
#             echo "    - ${SUDO_PREFIX}apt install latexdiff"
#         elif [ "$PKG_MANAGER" = "yum" ]; then
#             echo "    - ${SUDO_PREFIX}yum install texlive-latexdiff"
#         fi
#         echo "    - Or use: module load texlive"
#         echo "    - Or use: apptainer/singularity with texlive container"
#         return 1
#     fi
#     return 0
# }
# 
# check_texcount() {
#     local cmd=$(get_cmd_texcount "$ORIG_DIR")
#     if [ -z "$cmd" ]; then
#         echo "- texcount"
#         if [ "$PKG_MANAGER" = "apt" ]; then
#             echo "    - ${SUDO_PREFIX}apt install texlive-extra-utils"
#         elif [ "$PKG_MANAGER" = "yum" ]; then
#             echo "    - ${SUDO_PREFIX}yum install texlive-texcount"
#         fi
#         echo "    - Or use: module load texlive"
#         echo "    - Or use: apptainer/singularity with texlive container"
#         return 1
#     fi
#     return 0
# }
# 
# check_xlsx2csv() {
#     if ! command -v xlsx2csv &> /dev/null && ! python3 -c "import xlsx2csv" &> /dev/null 2>&1; then
#         echo "- xlsx2csv"
#         echo "    - pip install xlsx2csv"
#         if [ "$PKG_MANAGER" = "apt" ]; then
#             echo "    - Or: ${SUDO_PREFIX}apt install xlsx2csv"
#         fi
#         return 1
#     fi
#     return 0
# }
# 
# check_csv2latex() {
#     if ! command -v csv2latex &> /dev/null && ! python3 -c "import csv2latex" &> /dev/null 2>&1; then
#         echo "- csv2latex"
#         echo "    - pip install csv2latex"
#         return 1
#     fi
#     return 0
# }
# 
# check_parallel() {
#     if ! command -v parallel &> /dev/null; then
#         echo "- parallel"
#         if [ "$PKG_MANAGER" = "apt" ]; then
#             echo "    - ${SUDO_PREFIX}apt install parallel"
#         elif [ "$PKG_MANAGER" = "yum" ]; then
#             echo "    - ${SUDO_PREFIX}yum install parallel"
#         fi
#         return 1
#     fi
#     return 0
# }
# 
# check_opencv() {
#     if command -v python3 &> /dev/null; then
#         if ! python3 -c "import cv2" &> /dev/null 2>&1; then
#             echo "- opencv-python (optional, for --crop_tif)"
#             echo "    - pip install opencv-python"
#             return 1
#         fi
#     fi
#     return 0
# }
# 
# check_numpy() {
#     if command -v python3 &> /dev/null; then
#         if ! python3 -c "import numpy" &> /dev/null 2>&1; then
#             echo "- numpy (optional, for --crop_tif)"
#             echo "    - pip install numpy"
#             return 1
#         fi
#     fi
#     return 0
# }
# 
# check_mmdc() {
#     local cmd=$(get_cmd_mmdc "$ORIG_DIR")
#     if [ -z "$cmd" ]; then
#         echo "- mmdc (optional, for Mermaid diagrams)"
#         if ! command -v npm &> /dev/null; then
#             echo "    - First install npm/nodejs"
#         fi
#         echo "    - npm install -g @mermaid-js/mermaid-cli"
#         echo "    - Or use: apptainer/singularity with mermaid container"
#         return 1
#     fi
#     return 0
# }
# 
# check_bibtexparser() {
#     if command -v python3 &> /dev/null; then
#         if ! python3 -c "import bibtexparser" &> /dev/null 2>&1; then
#             echo "- bibtexparser (for bibliography analysis tools)"
#             echo "    - pip install bibtexparser"
#             return 1
#         fi
#     fi
#     return 0
# }
# 
# # Check all required commands (parallelized for speed)
# check_all_dependencies() {
#     local has_missing_required=false
#     local has_missing_optional=false
#     local required_output=""
#     local optional_output=""
# 
#     # Log run timestamp
#     echo "=== $(date '+%Y-%m-%d %H:%M:%S') ===" >> "$LOG_PATH"
# 
#     # Quick native-only check to avoid expensive container warmup
#     local all_native_available=true
#     local start_native_check=$(date +%s%N)
# 
#     # Check if all required native commands exist (fast check only)
#     if ! command -v pdflatex &> /dev/null || ! pdflatex --version &> /dev/null 2>&1; then
#         all_native_available=false
#     elif ! command -v bibtex &> /dev/null || ! bibtex --version &> /dev/null 2>&1; then
#         all_native_available=false
#     elif ! command -v latexdiff &> /dev/null; then
#         all_native_available=false
#     elif ! command -v texcount &> /dev/null || ! texcount --version &> /dev/null 2>&1; then
#         all_native_available=false
#     fi
# 
#     local end_native_check=$(date +%s%N)
#     local native_check_ms=$(( (end_native_check - start_native_check) / 1000000 ))
#     echo "Native check: ${native_check_ms}ms" >> "$LOG_PATH"
#     echo_info "    Native check: ${native_check_ms}ms"
# 
#     # Only do expensive warmup if native commands are missing
#     if [ "$all_native_available" = false ]; then
#         echo_info "    Native commands incomplete, checking alternatives..."
#         # Pre-warmup: do expensive shared setup once before parallelizing
#         # This prevents each parallel job from doing redundant work
#         local start_warmup=$(date +%s%N)
#         get_container_runtime &> /dev/null
#         load_texlive_module &> /dev/null
#         setup_latex_container &> /dev/null
#         setup_mermaid_container &> /dev/null
#         local end_warmup=$(date +%s%N)
#         local warmup_ms=$(( (end_warmup - start_warmup) / 1000000 ))
#         echo "Warmup: ${warmup_ms}ms" >> "$LOG_PATH"
#         echo_info "    Warmup: ${warmup_ms}ms"
#     else
#         echo_info "    All native LaTeX commands available (skipping container warmup)"
#     fi
# 
#     # Temp directory for parallel results
#     local temp_dir=$(mktemp -d)
# 
#     # Run all required checks in parallel, capturing exit codes
#     local start_checks=$(date +%s%N)
#     (check_pdflatex > "$temp_dir/req_pdflatex" 2>&1; echo $? > "$temp_dir/req_pdflatex.exit") &
#     (check_bibtex > "$temp_dir/req_bibtex" 2>&1; echo $? > "$temp_dir/req_bibtex.exit") &
#     (check_latexdiff > "$temp_dir/req_latexdiff" 2>&1; echo $? > "$temp_dir/req_latexdiff.exit") &
#     (check_texcount > "$temp_dir/req_texcount" 2>&1; echo $? > "$temp_dir/req_texcount.exit") &
#     (check_xlsx2csv > "$temp_dir/req_xlsx2csv" 2>&1; echo $? > "$temp_dir/req_xlsx2csv.exit") &
#     (check_csv2latex > "$temp_dir/req_csv2latex" 2>&1; echo $? > "$temp_dir/req_csv2latex.exit") &
#     (check_parallel > "$temp_dir/req_parallel" 2>&1; echo $? > "$temp_dir/req_parallel.exit") &
# 
#     # Run all optional checks in parallel
#     (check_opencv > "$temp_dir/opt_opencv" 2>&1; echo $? > "$temp_dir/opt_opencv.exit") &
#     (check_numpy > "$temp_dir/opt_numpy" 2>&1; echo $? > "$temp_dir/opt_numpy.exit") &
#     (check_mmdc > "$temp_dir/opt_mmdc" 2>&1; echo $? > "$temp_dir/opt_mmdc.exit") &
#     (check_bibtexparser > "$temp_dir/opt_bibtexparser" 2>&1; echo $? > "$temp_dir/opt_bibtexparser.exit") &
# 
#     # Wait for all background jobs
#     wait
#     local end_checks=$(date +%s%N)
#     local checks_ms=$(( (end_checks - start_checks) / 1000000 ))
#     echo "Parallel checks: ${checks_ms}ms" >> "$LOG_PATH"
#     echo_info "    Parallel checks: ${checks_ms}ms"
# 
#     # Collect required results with exit codes
#     declare -A tool_status
#     for tool in pdflatex bibtex latexdiff texcount xlsx2csv csv2latex parallel; do
#         local exit_code=$(cat "$temp_dir/req_${tool}.exit" 2>/dev/null || echo 1)
#         if [ "$exit_code" -eq 0 ]; then
#             tool_status[$tool]="✓"
#         else
#             has_missing_required=true
#             tool_status[$tool]="✗"
#             if [ -s "$temp_dir/req_${tool}" ]; then
#                 required_output="${required_output}$(cat "$temp_dir/req_${tool}")\n"
#             fi
#         fi
#     done
# 
#     # Collect optional results
#     for result_file in "$temp_dir"/opt_*.exit; do
#         local tool=$(basename "$result_file" .exit | sed 's/opt_//')
#         local exit_code=$(cat "$result_file" 2>/dev/null || echo 1)
#         if [ "$exit_code" -ne 0 ]; then
#             has_missing_optional=true
#             if [ -s "${result_file%.exit}" ]; then
#                 optional_output="${optional_output}$(cat "${result_file%.exit}")\n"
#             fi
#         fi
#     done
# 
#     # Cleanup
#     rm -rf "$temp_dir"
# 
#     # Display results
#     if [ "$has_missing_required" = true ]; then
#         echo_error "    Missing required tools:"
#         echo -e "$required_output"
#         return 1
#     else
#         # Show summary table using cached results (no additional checks!)
#         echo_success "    Required tools:"
#         printf "      %-20s %s\n" "pdflatex" "${tool_status[pdflatex]}"
#         printf "      %-20s %s\n" "bibtex" "${tool_status[bibtex]}"
#         printf "      %-20s %s\n" "latexdiff" "${tool_status[latexdiff]}"
#         printf "      %-20s %s\n" "texcount" "${tool_status[texcount]}"
#         printf "      %-20s %s\n" "xlsx2csv" "${tool_status[xlsx2csv]}"
#         printf "      %-20s %s\n" "csv2latex" "${tool_status[csv2latex]}"
#         printf "      %-20s %s\n" "parallel" "${tool_status[parallel]}"
#     fi
# 
#     if [ "$has_missing_optional" = true ]; then
#         echo_warning "    Missing optional tools:"
#         echo -e "$optional_output"
#     fi
# 
#     return 0
# }
# 
# # Run checks
# check_all_dependencies
# exit_code=$?
# 
# exit $exit_code
# 
# # EOF
# --------------------------------------------------------------------------------
# End of Source Code from: /home/ywatanabe/proj/scitex-writer/scripts/shell/modules/check_dependancy_commands.sh
# --------------------------------------------------------------------------------
