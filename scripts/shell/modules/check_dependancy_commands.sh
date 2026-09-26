#!/bin/bash
# -*- coding: utf-8 -*-
# ROLE: engine-vendored — DO NOT edit here. `scitex-writer update-project`
# overwrites this file on every re-vendor; fix it upstream in the
# scitex-writer package instead (local edits are lost, and update-project
# may set it read-only in the consumer workspace after vendoring).
# Timestamp: "2025-11-11 07:23:33 (ywatanabe)"
# File: ./scripts/shell/modules/check_dependancy_commands.sh

ORIG_DIR="$(pwd)"
THIS_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
LOG_PATH="$THIS_DIR/.$(basename "$0").log"
echo >"$LOG_PATH"

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
echo_error() { echo -e "${RED}ERRO: $1${NC}" >&2; }
echo_header() { echo_info "=== $1 ==="; }
# ---------------------------------------

# Don't clear log at start - timing info will be appended

# Configurations
# shellcheck source=/dev/null
source ./config/load_config.sh "$SCITEX_WRITER_DOC_TYPE"

# Source the 00_shared LaTeX commands module
# shellcheck source=/dev/null
source "$(dirname "${BASH_SOURCE[0]}")/command_switching.src"
log_info "Running ${BASH_SOURCE[0]}..."

# Verify a RESOLVED command actually executes -- not merely that get_cmd_*
# returned a non-empty string. Probes through the full command incl. any
# container-exec prefix, so a present-but-unmountable .sif (squashfuse
# 'fuse: device not found') fails here instead of being greenlit as a working
# engine. Returns 0 only when the probe runs to a 0 exit within the timeout.
_probe_runs() {
    local cmd="$1"
    [ -z "$cmd" ] && return 1
    # shellcheck disable=SC2086  # $cmd is a multi-word resolved command line.
    if command -v timeout &>/dev/null; then
        timeout 20 $cmd --version &>/dev/null
    else
        $cmd --version &>/dev/null
    fi
}

# Detect package manager
detect_package_manager() {
    if command -v apt &>/dev/null; then
        echo "apt"
    elif command -v yum &>/dev/null; then
        echo "yum"
    else
        echo "unknown"
    fi
}

# Check if sudo is available
has_sudo() {
    if command -v sudo &>/dev/null; then
        return 0
    else
        return 1
    fi
}

PKG_MANAGER=$(detect_package_manager)
SUDO_PREFIX=""
if has_sudo; then
    SUDO_PREFIX="sudo "
fi

# Standalone checker for each tool
check_pdflatex() {
    local cmd
    cmd=$(get_cmd_pdflatex "$ORIG_DIR")
    if [ -z "$cmd" ] || ! _probe_runs "$cmd"; then
        echo "- pdflatex"
        if [ "$PKG_MANAGER" = "apt" ]; then
            echo "    - ${SUDO_PREFIX}apt install texlive-latex-base"
        elif [ "$PKG_MANAGER" = "yum" ]; then
            echo "    - ${SUDO_PREFIX}yum install texlive-latex"
        fi
        echo "    - Or use: module load texlive"
        echo "    - Or use: scitex-writer containers install texlive -y"
        return 1
    fi
    return 0
}

check_bibtex() {
    local cmd
    cmd=$(get_cmd_bibtex "$ORIG_DIR")
    if [ -z "$cmd" ] || ! _probe_runs "$cmd"; then
        echo "- bibtex"
        if [ "$PKG_MANAGER" = "apt" ]; then
            echo "    - ${SUDO_PREFIX}apt install texlive-bibtex-extra"
        elif [ "$PKG_MANAGER" = "yum" ]; then
            echo "    - ${SUDO_PREFIX}yum install texlive-bibtex"
        fi
        echo "    - Or use: module load texlive"
        echo "    - Or use: scitex-writer containers install texlive -y"
        return 1
    fi
    return 0
}

check_latexdiff() {
    local cmd
    cmd=$(get_cmd_latexdiff "$ORIG_DIR")
    if [ -z "$cmd" ] || ! _probe_runs "$cmd"; then
        echo "- latexdiff"
        if [ "$PKG_MANAGER" = "apt" ]; then
            echo "    - ${SUDO_PREFIX}apt install latexdiff"
        elif [ "$PKG_MANAGER" = "yum" ]; then
            echo "    - ${SUDO_PREFIX}yum install texlive-latexdiff"
        fi
        echo "    - Or use: module load texlive"
        echo "    - Or use: scitex-writer containers install texlive -y"
        return 1
    fi
    return 0
}

check_texcount() {
    local cmd
    cmd=$(get_cmd_texcount "$ORIG_DIR")
    if [ -z "$cmd" ] || ! _probe_runs "$cmd"; then
        echo "- texcount"
        if [ "$PKG_MANAGER" = "apt" ]; then
            echo "    - ${SUDO_PREFIX}apt install texlive-extra-utils"
        elif [ "$PKG_MANAGER" = "yum" ]; then
            echo "    - ${SUDO_PREFIX}yum install texlive-texcount"
        fi
        echo "    - Or use: module load texlive"
        echo "    - Or use: scitex-writer containers install texlive -y"
        return 1
    fi
    return 0
}

check_yq() {
    # yq is invoked directly by config/load_config.sh to read every YAML path.
    # Probe EXECUTION (not mere presence): a present-but-broken yq (e.g. a
    # .venv/bin/yq whose Python shebang no longer resolves -> "bad interpreter")
    # must FAIL here, otherwise it passes the gate green and then silently
    # yields empty paths during config load.
    if ! command -v yq &>/dev/null || ! yq --version &>/dev/null 2>&1; then
        echo "- yq"
        echo "    - Go (recommended): https://github.com/mikefarah/yq"
        echo "    - If present but failing: a broken venv interpreter -- repair the venv or put a working yq first on PATH"
        return 1
    fi
    return 0
}

check_xlsx2csv() {
    # Table conversion is only exercised when the manuscript actually contains
    # xlsx/csv table sources (process_tables reads
    # 01_manuscript/contents/tables/...). A default manuscript has none, so a
    # fresh env missing xlsx2csv must not hard-fail every compile (2026-09-14
    # repro: "Missing required tools: xlsx2csv, csv2latex" on a table-less doc).
    # Only require the tool when a table source is present.
    local _has_table_src=false
    if [ -d 01_manuscript ]; then
        # shellcheck disable=SC2012
        if find 01_manuscript -type f \( -name '*.xlsx' -o -name '*.xls' -o -name '*.csv' \) -print -quit 2>/dev/null | grep -q .; then
            _has_table_src=true
        fi
    fi
    if [ "$_has_table_src" = true ] && ! command -v xlsx2csv &>/dev/null && ! python3 -c "import xlsx2csv" &>/dev/null 2>&1; then
        echo "- xlsx2csv"
        echo "    - pip install xlsx2csv"
        if [ "$PKG_MANAGER" = "apt" ]; then
            echo "    - Or: ${SUDO_PREFIX}apt install xlsx2csv"
        fi
        return 1
    fi
    return 0
}

check_csv2latex() {
    # See check_xlsx2csv: only required when the manuscript has table sources.
    local _has_table_src=false
    if [ -d 01_manuscript ]; then
        # shellcheck disable=SC2012
        if find 01_manuscript -type f \( -name '*.xlsx' -o -name '*.xls' -o -name '*.csv' \) -print -quit 2>/dev/null | grep -q .; then
            _has_table_src=true
        fi
    fi
    if [ "$_has_table_src" = true ] && ! command -v csv2latex &>/dev/null && ! python3 -c "import csv2latex" &>/dev/null 2>&1; then
        echo "- csv2latex"
        echo "    - pip install csv2latex"
        return 1
    fi
    return 0
}

check_parallel() {
    if ! command -v parallel &>/dev/null; then
        echo "- parallel"
        if [ "$PKG_MANAGER" = "apt" ]; then
            echo "    - ${SUDO_PREFIX}apt install parallel"
        elif [ "$PKG_MANAGER" = "yum" ]; then
            echo "    - ${SUDO_PREFIX}yum install parallel"
        fi
        return 1
    fi
    return 0
}

check_opencv() {
    if command -v python3 &>/dev/null; then
        if ! python3 -c "import cv2" &>/dev/null 2>&1; then
            echo "- opencv-python (optional, for --crop_tif)"
            echo "    - pip install opencv-python"
            return 1
        fi
    fi
    return 0
}

check_numpy() {
    if command -v python3 &>/dev/null; then
        if ! python3 -c "import numpy" &>/dev/null 2>&1; then
            echo "- numpy (optional, for --crop_tif)"
            echo "    - pip install numpy"
            return 1
        fi
    fi
    return 0
}

check_mmdc() {
    local cmd
    cmd=$(get_cmd_mmdc "$ORIG_DIR")
    if [ -z "$cmd" ] || ! _probe_runs "$cmd"; then
        echo "- mmdc (optional, for Mermaid diagrams)"
        if ! command -v npm &>/dev/null; then
            echo "    - First install npm/nodejs"
        fi
        echo "    - npm install -g @mermaid-js/mermaid-cli"
        echo "    - Or use: apptainer/singularity with mermaid container"
        return 1
    fi
    return 0
}

check_bibtexparser() {
    if command -v python3 &>/dev/null; then
        if ! python3 -c "import bibtexparser" &>/dev/null 2>&1; then
            echo "- bibtexparser (for bibliography analysis tools)"
            echo "    - pip install bibtexparser"
            return 1
        fi
    fi
    return 0
}

# Check all required commands (parallelized for speed)
check_all_dependencies() {
    local has_missing_required=false
    local has_missing_optional=false
    local required_output=""
    local optional_output=""

    # Log run timestamp
    echo "=== $(date '+%Y-%m-%d %H:%M:%S') ===" >>"$LOG_PATH"

    # Quick native-only check to avoid expensive container warmup
    local all_native_available=true
    local start_native_check
    start_native_check=$(date +%s%N)

    # Check if all required native commands exist (fast check only)
    if ! command -v pdflatex &>/dev/null || ! pdflatex --version &>/dev/null 2>&1; then
        all_native_available=false
    elif ! command -v bibtex &>/dev/null || ! bibtex --version &>/dev/null 2>&1; then
        all_native_available=false
    elif ! command -v latexdiff &>/dev/null; then
        all_native_available=false
    elif ! command -v texcount &>/dev/null || ! texcount --version &>/dev/null 2>&1; then
        all_native_available=false
    fi

    local end_native_check
    end_native_check=$(date +%s%N)
    local native_check_ms
    native_check_ms=$(((end_native_check - start_native_check) / 1000000))
    echo "Native check: ${native_check_ms}ms" >>"$LOG_PATH"
    echo_info "    Native check: ${native_check_ms}ms"

    # Only do expensive warmup if native commands are missing
    if [ "$all_native_available" = false ]; then
        echo_info "    Native commands incomplete, checking alternatives..."
        # Pre-warmup: do expensive shared setup once before parallelizing
        # This prevents each parallel job from doing redundant work
        local start_warmup
        start_warmup=$(date +%s%N)
        get_container_runtime &>/dev/null
        load_texlive_module &>/dev/null
        setup_latex_container &>/dev/null
        setup_mermaid_container &>/dev/null
        local end_warmup
        end_warmup=$(date +%s%N)
        local warmup_ms
        warmup_ms=$(((end_warmup - start_warmup) / 1000000))
        echo "Warmup: ${warmup_ms}ms" >>"$LOG_PATH"
        echo_info "    Warmup: ${warmup_ms}ms"
    else
        echo_info "    All native LaTeX commands available (skipping container warmup)"
    fi

    # Temp directory for parallel results
    local temp_dir
    temp_dir=$(mktemp -d)

    # Run all required checks in parallel, capturing exit codes
    local start_checks
    start_checks=$(date +%s%N)
    (
        check_pdflatex >"$temp_dir/req_pdflatex" 2>&1
        echo $? >"$temp_dir/req_pdflatex.exit"
    ) &
    (
        check_bibtex >"$temp_dir/req_bibtex" 2>&1
        echo $? >"$temp_dir/req_bibtex.exit"
    ) &
    (
        check_latexdiff >"$temp_dir/req_latexdiff" 2>&1
        echo $? >"$temp_dir/req_latexdiff.exit"
    ) &
    (
        check_texcount >"$temp_dir/req_texcount" 2>&1
        echo $? >"$temp_dir/req_texcount.exit"
    ) &
    (
        check_xlsx2csv >"$temp_dir/req_xlsx2csv" 2>&1
        echo $? >"$temp_dir/req_xlsx2csv.exit"
    ) &
    (
        check_csv2latex >"$temp_dir/req_csv2latex" 2>&1
        echo $? >"$temp_dir/req_csv2latex.exit"
    ) &
    (
        check_parallel >"$temp_dir/req_parallel" 2>&1
        echo $? >"$temp_dir/req_parallel.exit"
    ) &
    (
        check_bibtexparser >"$temp_dir/req_bibtexparser" 2>&1
        echo $? >"$temp_dir/req_bibtexparser.exit"
    ) &
    (
        check_yq >"$temp_dir/req_yq" 2>&1
        echo $? >"$temp_dir/req_yq.exit"
    ) &

    # Run all optional checks in parallel
    (
        check_opencv >"$temp_dir/opt_opencv" 2>&1
        echo $? >"$temp_dir/opt_opencv.exit"
    ) &
    (
        check_numpy >"$temp_dir/opt_numpy" 2>&1
        echo $? >"$temp_dir/opt_numpy.exit"
    ) &
    (
        check_mmdc >"$temp_dir/opt_mmdc" 2>&1
        echo $? >"$temp_dir/opt_mmdc.exit"
    ) &

    # Wait for all background jobs
    wait
    local end_checks
    end_checks=$(date +%s%N)
    local checks_ms
    checks_ms=$(((end_checks - start_checks) / 1000000))
    echo "Parallel checks: ${checks_ms}ms" >>"$LOG_PATH"
    echo_info "    Parallel checks: ${checks_ms}ms"

    # Collect required results with exit codes
    declare -A tool_status
    local exit_code
    for tool in pdflatex bibtex latexdiff texcount yq xlsx2csv csv2latex parallel bibtexparser; do
        exit_code=$(cat "$temp_dir/req_${tool}.exit" 2>/dev/null || echo 1)
        if [ "$exit_code" -eq 0 ]; then
            tool_status[$tool]="✓"
        else
            has_missing_required=true
            tool_status[$tool]="✗"
            if [ -s "$temp_dir/req_${tool}" ]; then
                required_output="${required_output}$(cat "$temp_dir/req_${tool}")\n"
            fi
        fi
    done

    # Collect optional results
    local tool
    for result_file in "$temp_dir"/opt_*.exit; do
        tool=$(basename "$result_file" .exit | sed 's/opt_//')
        exit_code=$(cat "$result_file" 2>/dev/null || echo 1)
        if [ "$exit_code" -ne 0 ]; then
            has_missing_optional=true
            if [ -s "${result_file%.exit}" ]; then
                optional_output="${optional_output}$(cat "${result_file%.exit}")\n"
            fi
        fi
    done

    # Cleanup
    rm -rf "$temp_dir"

    # Display results
    if [ "$has_missing_required" = true ]; then
        # Send the full required-tools report to STDERR so it lands in the
        # compile result's stderr_tail (run_compile_script captures stderr, not
        # stdout, into result.error / the UI). A stdout-only message reads as
        # "exit 1" with no cause (the 2026-09-14 repro saw stderr_tail: null).
        echo_error "    Missing required tools:"
        echo -e "$required_output" >&2
        return 1
    else
        # Show summary table using cached results (no additional checks!)
        echo_success "    Required tools:"
        printf "      %-20s %s\n" "pdflatex" "${tool_status[pdflatex]}"
        printf "      %-20s %s\n" "bibtex" "${tool_status[bibtex]}"
        printf "      %-20s %s\n" "latexdiff" "${tool_status[latexdiff]}"
        printf "      %-20s %s\n" "texcount" "${tool_status[texcount]}"
        printf "      %-20s %s\n" "yq" "${tool_status[yq]}"
        printf "      %-20s %s\n" "xlsx2csv" "${tool_status[xlsx2csv]}"
        printf "      %-20s %s\n" "csv2latex" "${tool_status[csv2latex]}"
        printf "      %-20s %s\n" "parallel" "${tool_status[parallel]}"
        printf "      %-20s %s\n" "bibtexparser" "${tool_status[bibtexparser]}"
    fi

    if [ "$has_missing_optional" = true ]; then
        echo_warning "    Missing optional tools:"
        echo -e "$optional_output"
    fi

    return 0
}

# Run checks
check_all_dependencies
exit_code=$?

exit $exit_code

# EOF
