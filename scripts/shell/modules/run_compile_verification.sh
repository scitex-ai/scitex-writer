#!/bin/bash
# -*- coding: utf-8 -*-
# ROLE: engine-vendored — DO NOT edit here. `scitex-writer update-project`
# overwrites this file on every re-vendor; fix it upstream in the
# scitex-writer package instead (local edits are lost, and update-project
# may set it read-only in the consumer workspace after vendoring).
# File: scripts/shell/modules/run_compile_verification.sh
#
# POST-compile verification gate. Runs scripts/python/check_compile_artifacts.py
# at its RESOLVED severity (off|warn|error via CLI/env/config). It catches a
# FALSE-SUCCESS compile (exit 0 but DEFICIENT PDF): the compiled .tex emits N
# \includegraphics but the PDF embeds 0 images (silent figure miss -- the
# 2026-06-30 incident), plus secondary log deficiency signals.
#   off   -> no-op (exit 0)
#   warn  -> reports, exit 0 (does NOT block)
#   error -> exit 1 (blocks, fail-loud) when the PDF is deficient
# Default error. The PDF embedding check needs poppler (pdfimages); when absent
# it warns and does not block (the compile host has poppler).

THIS_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="${PROJECT_ROOT:-$(cd "$THIS_DIR/../../.." && pwd)}"
PY="${SCITEX_WRITER_PYTHON:-python3}"

script="$THIS_DIR/../../python/check_compile_artifacts.py"
[ -f "$script" ] || exit 0

tex_name=$(basename "${SCITEX_WRITER_COMPILED_TEX%.tex}")
"$PY" "$script" "$PROJECT_ROOT" \
    --tex-log "${LOG_DIR}/${tex_name}.log" \
    --compiled-tex "${SCITEX_WRITER_COMPILED_TEX}" \
    --pdf "${SCITEX_WRITER_COMPILED_PDF}" \
    --log "${SCITEX_WRITER_GLOBAL_LOG_FILE}"
