#!/bin/bash
# -*- coding: utf-8 -*-
# ROLE: engine-vendored — DO NOT edit here. `scitex-writer update-project`
# overwrites this file on every re-vendor; fix it upstream in the
# scitex-writer package instead (local edits are lost, and update-project
# may set it read-only in the consumer workspace after vendoring).
# Timestamp: "2025-10-29 12:59:32 (ywatanabe)"
# File: ./compile.sh

ORIG_DIR="$(pwd)"
export ORIG_DIR
THIS_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

# Early parsing for --project-root (must be done before PROJECT_ROOT is set)
for arg in "$@"; do
    case $arg in
    -p=* | --project-root=* | --project_root=*)
        PROJECT_ROOT="${arg#*=}"
        ;;
    esac
done

# Resolve project root from script location (safe for nested repos)
# Priority: 1. -p/--project-root arg, 2. env var, 3. auto-detect from script location
PROJECT_ROOT="${PROJECT_ROOT:-$(cd "$THIS_DIR" && pwd)}"
export PROJECT_ROOT


GRAY='\033[0;90m'
GREEN='\033[0;32m'
YELLOW='\033[0;33m'
RED='\033[0;31m'
CYAN='\033[0;36m'
BOLD_CYAN='\033[1;36m'
NC='\033[0m' # No Color

echo_info() { echo -e "${GRAY}INFO: $1${NC}"; }
echo_success() { echo -e "${GREEN}SUCC: $1${NC}"; }
echo_warning() { echo -e "${YELLOW}WARN: $1${NC}"; }
echo_error() { echo -e "${RED}ERRO: $1${NC}"; }
echo_header() { echo_info "=== $1 ==="; }
# ---------------------------------------
# Time-stamp: "2025-09-27 15:00:00 (ywatanabe)"

################################################################################
# Unified compilation interface
# Delegates to specific compilation scripts based on document type
################################################################################

# Default values
DOC_TYPE=""
WATCH_MODE=false

# Function to display usage
show_usage() {
    cat <<EOF
Usage: ./compile.sh [TYPE] [OPTIONS]

Unified compilation interface for scientific documents.

DOCUMENT TYPES:
    manuscript, -m        Compile manuscript (= ./scripts/shell/compile_manuscript.sh)
    supplementary, -s     Compile supplementary (= ./scripts/shell/compile_supplementary.sh)
    revision, -r          Compile revision (= ./scripts/shell/compile_revision.sh)
    all, -a               Compile supplement THEN manuscript in dependency order
                          so main->supplement cross-refs (xr-hyper) resolve in a
                          single invocation (supplement .aux is produced first).

BUILD INSPECTION:
    builds [-n N]         List recent build IDs embedded in PDFs
    show <BUILD_ID>       Show metadata for a specific build ID (or prefix)

GLOBAL OPTIONS:
    -h, --help           Show this help message
    --help-recursive     Show help for all commands recursively
    -p, --project-root   Override project root directory
                         (useful when project is moved)
    -w, --watch          Enable watch mode for hot-recompiling
                         (Only works with manuscript type)

COMMON SPEED OPTIONS (available for all document types):
    -nf, --no_figs       Skip figure processing (~4s faster)
    -nt, --no_tables     Skip table processing (~4s faster)
    -nd, --no_diff       Skip diff generation (~17s faster)
                         (revision skips diff by default)
    -d,  --draft         Single-pass PDF compilation (~5s faster)
    -dm, --dark_mode     Dark mode: black background, white text
                         (figures keep original colors)
    -q,  --quiet         Minimal logs
    -v,  --verbose       Detailed logs

    Note: All options accept both hyphens and underscores
          (e.g., --no-figs or --no_figs, --dark-mode or --dark_mode)

EXAMPLES:
    Basic compilation:
    ./compile.sh                           # Compile manuscript (default)
    ./compile.sh manuscript                # Explicitly compile manuscript
    ./compile.sh supplementary             # Compile supplementary materials
    ./compile.sh revision                  # Compile revision responses
    ./compile.sh all                       # Supplement then manuscript (xr-hyper)

    Short forms:
    ./compile.sh -m                        # Compile manuscript
    ./compile.sh -s                        # Compile supplementary
    ./compile.sh -r                        # Compile revision
    ./compile.sh -a                        # Supplement then manuscript

    Cross-references (main <-> supplement):
    ./compile.sh all                       # One-shot: resolves \ref into the
                                           # supplement without a manual -s then -m.
                                           # Speed flags pass through to both, e.g.:
    ./compile.sh all --no-diff             # Combined build, skip diff on both

    Speed options:
    ./compile.sh -m --no-figs --no-diff    # Fast manuscript (~12s)
    ./compile.sh -s --no_figs --no_tables --draft  # Ultra-fast supplementary
    ./compile.sh -r --no-figs --draft      # Fast revision

    Ultra-fast mode (all speed flags):
    ./compile.sh -m --no-figs --no-tables --no-diff --draft  # ~8s

    Dark mode:
    ./compile.sh -m --dark-mode            # Black background, white text
    ./compile.sh -s --dark_mode            # Works with all doc types

    Watch mode:
    ./compile.sh -m -w                     # Watch and recompile manuscript
    ./compile.sh -m --watch --no-figs      # Watch mode with speed options

    Custom project root (for moved projects):
    ./compile.sh -m -p=/new/path/to/project
    ./compile.sh -m --project-root=/path/to/project

EOF
}

# Function to display help for all commands recursively
show_help_recursive() {
    echo ""
    echo -e "${BOLD_CYAN}━━━ compile.sh (main) ━━━${NC}"
    show_usage
    echo ""
    echo -e "${CYAN}────────────────────────────────────────────────────────────────────${NC}"
    echo ""
    echo -e "${BOLD_CYAN}━━━ compile.sh manuscript ━━━${NC}"
    echo -e "${GRAY}./scripts/shell/compile_manuscript.sh${NC}"
    echo ""
    bash "$THIS_DIR/scripts/shell/compile_manuscript.sh" --help 2>/dev/null || echo "(No help available)"
    echo ""
    echo -e "${CYAN}────────────────────────────────────────────────────────────────────${NC}"
    echo ""
    echo -e "${BOLD_CYAN}━━━ compile.sh supplementary ━━━${NC}"
    echo -e "${GRAY}./scripts/shell/compile_supplementary.sh${NC}"
    echo ""
    bash "$THIS_DIR/scripts/shell/compile_supplementary.sh" --help 2>/dev/null || echo "(No help available)"
    echo ""
    echo -e "${CYAN}────────────────────────────────────────────────────────────────────${NC}"
    echo ""
    echo -e "${BOLD_CYAN}━━━ compile.sh revision ━━━${NC}"
    echo -e "${GRAY}./scripts/shell/compile_revision.sh${NC}"
    echo ""
    bash "$THIS_DIR/scripts/shell/compile_revision.sh" --help 2>/dev/null || echo "(No help available)"
    echo ""
}

# Parse arguments
REMAINING_ARGS=""

while [ $# -gt 0 ]; do
    case $1 in
    manuscript | -m)
        DOC_TYPE="manuscript"
        shift
        ;;
    supplementary | -s)
        DOC_TYPE="supplementary"
        shift
        ;;
    revision | -r)
        DOC_TYPE="revision"
        shift
        ;;
    all | -a)
        # Combined target: compile supplement then manuscript in dependency
        # order so main->supplement cross-refs (xr-hyper) resolve in one call.
        DOC_TYPE="all"
        shift
        ;;
    builds)
        # Inspect the build registry (#77). Delegates to manage_builds.py.
        shift
        exec python3 "$PROJECT_ROOT/scripts/python/manage_builds.py" \
            --project-root "$PROJECT_ROOT" list "$@"
        ;;
    show)
        # Show one build by ID or prefix (#77).
        shift
        exec python3 "$PROJECT_ROOT/scripts/python/manage_builds.py" \
            --project-root "$PROJECT_ROOT" show "$@"
        ;;
    -w | --watch)
        WATCH_MODE=true
        shift
        ;;
    -p=* | --project-root=* | --project_root=*)
        # Already parsed early, just consume the argument
        shift
        ;;
    --help-recursive)
        show_help_recursive
        exit 0
        ;;
    -h | --help)
        # If document type already specified, pass --help to that script
        # Otherwise, show wrapper's help
        if [ -z "$DOC_TYPE" ]; then
            show_usage
            exit 0
        elif [ "$DOC_TYPE" = "all" ]; then
            show_help_recursive
            exit 0
        else
            bash "$THIS_DIR/scripts/shell/compile_${DOC_TYPE}.sh" --help
            exit $?
        fi
        ;;
    *)
        # Collect remaining arguments
        if [ -z "$DOC_TYPE" ]; then
            echo "ERROR: Unknown document type '$1'"
            echo "Valid types: manuscript, supplementary, revision, all"
            echo "Use './compile --help' for usage information"
            exit 1
        else
            REMAINING_ARGS="$REMAINING_ARGS $1"
            shift
        fi
        ;;
    esac
done

# Help is handled before project writes, initialization or dependency checks.
LOG_PATH="$THIS_DIR/.$(basename "$0").log"
echo >"$LOG_PATH"

# Change to project root to ensure all relative paths work (Issue #13)
cd "$PROJECT_ROOT" || exit 1

# Auto-initialize project if preprocessing artifacts are missing (Issue #12)
if [ ! -f "01_manuscript/contents/wordcounts/figure_count.txt" ]; then
    if [ -x "$PROJECT_ROOT/scripts/installation/init_project.sh" ]; then
        echo "Initializing project (missing preprocessing artifacts)..."
        "$PROJECT_ROOT/scripts/installation/init_project.sh" >/dev/null 2>&1 || true
    fi
fi


# Default to manuscript if no type specified
if [ -z "$DOC_TYPE" ]; then
    DOC_TYPE="manuscript"
fi

# Check if watch mode is supported for this document type
if [ "$WATCH_MODE" = true ] && [ "$DOC_TYPE" != "manuscript" ]; then
    echo "ERROR: Watch mode is only supported for manuscript compilation"
    echo "Use: ./compile -m -w"
    exit 1
fi

# Display what we're doing (compact format)
echo ""
echo -e "\033[1;36m━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\033[0m"
echo -e "\033[1;36m  SciTeX Writer Compilation\033[0m"
echo -e "\033[0;36m  Type: $DOC_TYPE\033[0m"
if [ "$WATCH_MODE" = true ]; then
    echo -e "\033[0;36m  Mode: WATCH\033[0m"
fi
if [ -n "$REMAINING_ARGS" ]; then
    echo -e "\033[0;90m  Options:$REMAINING_ARGS\033[0m"
fi
echo -e "\033[1;36m━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\033[0m"
echo ""

# Handle watch mode
if [ "$WATCH_MODE" = true ]; then
    # Run watch script for manuscript
    "$PROJECT_ROOT/scripts/shell/watch_compile.sh" "$REMAINING_ARGS"
    exit $?
fi

# Delegate to the appropriate compilation script
# Note: Use ${VAR:+$VAR} to only pass args when non-empty (avoid passing "" as an argument)
case $DOC_TYPE in
manuscript)
    "$PROJECT_ROOT/scripts/shell/compile_manuscript.sh" ${REMAINING_ARGS:+$REMAINING_ARGS}
    ;;
supplementary)
    "$PROJECT_ROOT/scripts/shell/compile_supplementary.sh" ${REMAINING_ARGS:+$REMAINING_ARGS}
    ;;
revision)
    "$PROJECT_ROOT/scripts/shell/compile_revision.sh" ${REMAINING_ARGS:+$REMAINING_ARGS}
    ;;
all)
    # Dependency-ordered combined build for cross-references.
    #
    # 1. Supplement FIRST: its compile ends by exposing supplementary.aux at
    #    doc-root (./02_supplementary/supplementary.aux) — the target that the
    #    manuscript's xr-hyper \externaldocument/\link reads.
    # 2. Manuscript SECOND: with the supplement .aux now present, main->supplement
    #    \ref/\pageref resolve instead of printing "??".
    #
    # This replaces the manual "compile.sh -s && compile.sh -m" dance. Reverse
    # refs (supplement->main) additionally require the manuscript to expose its
    # own .aux at doc-root; that is a separate follow-up (pairs with
    # writer-supp-aux-docroot) and would add a third supplement pass here.
    echo -e "${CYAN}[all] Step 1/2: supplement (produces supplementary.aux)${NC}"
    "$PROJECT_ROOT/scripts/shell/compile_supplementary.sh" ${REMAINING_ARGS:+$REMAINING_ARGS} || exit $?
    echo -e "${CYAN}[all] Step 2/2: manuscript (resolves cross-refs into supplement)${NC}"
    "$PROJECT_ROOT/scripts/shell/compile_manuscript.sh" ${REMAINING_ARGS:+$REMAINING_ARGS}
    ;;
*)
    echo "Error: Unknown document type: $DOC_TYPE"
    exit 1
    ;;
esac

# Exit with the same status as the delegated script
exit $?

# EOF
