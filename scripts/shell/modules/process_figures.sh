#!/bin/bash
# -*- coding: utf-8 -*-
# ROLE: engine-vendored — DO NOT edit here. `scitex-writer update-project`
# overwrites this file on every re-vendor; fix it upstream in the
# scitex-writer package instead (local edits are lost, and update-project
# may set it read-only in the consumer workspace after vendoring).
# Timestamp: "$(date +"%Y-%m-%d %H:%M:%S") ($(whoami))"
# File: process_figures.sh
#
# SUPERSEDED (2.29.0) — NOTHING ON THE COMPILE PATH CALLS THIS ANY MORE.
# The compile scripts now delegate the figure stage to the installed Python
# engine via `modules/run_python_pipeline.sh figures` (-> `scitex-writer figures
# render`), which fixes bugs this module still has: multi-panel figures shipped
# as panel-a while logging success, and a no-op crop when magick/mogrify is
# absent. Kept for one release cycle only; do not wire it back in.

# shellcheck disable=SC1091  # Don't follow sourced files

# Get script directory and resolve project root (Issue #13)
export ORIG_DIR
ORIG_DIR="$(pwd)"
THIS_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
MODULES_DIR="$THIS_DIR/process_figures_modules"

# Resolve project root from script location (safe for nested repos)
PROJECT_ROOT="$(cd "$THIS_DIR/../../.." && pwd)"
export PROJECT_ROOT
# Both names go out: the refreshed vendored helpers read the prefixed name, and
# a workspace whose helpers have not been refreshed yet still reads this one.
export SCITEX_WRITER_PROJECT_ROOT="$PROJECT_ROOT"
cd "$PROJECT_ROOT" || exit 1

# Source configuration
source ./config/load_config.sh manuscript >/dev/null 2>&1

# Source all modules
source "$MODULES_DIR/00_common.src"
source "$MODULES_DIR/01_caption_management.src"
source "$MODULES_DIR/02_format_conversion.src"
source "$MODULES_DIR/03_panel_tiling.src"
source "$MODULES_DIR/04_compilation.src"

# Additional utility functions not yet modularized
ensure_lower_letter_id() {
    # Convert uppercase panel IDs to lowercase (01A_ -> 01a_)
    for file in "$SCITEX_WRITER_FIGURE_CAPTION_MEDIA_DIR"/[0-9]*[A-Z]_*; do
        [ -e "$file" ] || continue
        local dir
        dir=$(dirname "$file")
        local bname
        bname=$(basename "$file")
        local new_basename
        # shellcheck disable=SC2001  # sed needed for \L case conversion
        new_basename=$(echo "$bname" | sed 's/\([0-9]*\)\([A-Z]\)_/\1\L\2_/')

        if [ "$bname" != "$new_basename" ]; then
            echo_info "Renaming: $bname -> $new_basename"
            mv "$file" "$dir/$new_basename"
        fi
    done
}

crop_image() {
    local input_file="$1"
    local output_file="${2:-$input_file}"

    if command -v mogrify >/dev/null 2>&1; then
        mogrify -trim +repage "$input_file"
    elif command -v convert >/dev/null 2>&1; then
        convert "$input_file" -trim +repage "$output_file"
    fi
}

crop_all_images() {
    echo_info "Cropping all images..."
    for jpg_file in "$SCITEX_WRITER_FIGURE_JPG_DIR"/*.jpg; do
        [ -e "$jpg_file" ] || continue
        crop_image "$jpg_file"
    done
}

# Main function
main() {
    local no_figs="${1:-false}"
    local p2t="${2:-false}" # Convert PPTX to TIF
    local verbose="${3:-false}"
    local do_crop="${4:-false}" # Crop images

    if [ "$verbose" = true ]; then
        echo_info "Figure processing: Starting with parameters: "
        echo_info "no_figs=$no_figs, p2t=$p2t, crop=$do_crop"
    fi

    # Initialize environment
    init_figures
    ensure_lower_letter_id

    # Clean up panel captions that shouldn't exist
    cleanup_panel_captions

    # Ensure captions for main figures only
    ensure_caption

    if [ "$no_figs" = false ]; then
        # Run the figure conversion cascade
        convert_figure_formats_in_cascade "$p2t" "$do_crop"

        # Post-processing
        check_and_create_placeholders
        auto_tile_panels "$no_figs"
    fi

    # Final compilation steps
    compile_legends
    handle_figure_visibility "$no_figs"
    compile_figure_tex_files

    # Report results
    local compiled_count
    compiled_count=$(find "$SCITEX_WRITER_FIGURE_COMPILED_DIR" -maxdepth 1 -name "[0-9]*.tex" 2>/dev/null | wc -l)
    if [ "$no_figs" = false ] && [ "$compiled_count" -gt 0 ]; then
        echo_success "$compiled_count figures compiled"
    fi
}

# Run if executed directly
if [ "${BASH_SOURCE[0]}" == "${0}" ]; then
    main "$@"
fi

# EOF
