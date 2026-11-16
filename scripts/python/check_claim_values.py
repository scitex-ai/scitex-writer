#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# ROLE: engine-vendored — DO NOT edit here. `scitex-writer update-project`
# overwrites this file on every re-vendor; fix it upstream in the
# scitex-writer package instead (local edits are lost, and update-project
# may set it read-only in the consumer workspace after vendoring).
# File: scripts/python/check_claim_values.py
# Purpose: VALUE-VS-SOURCE gate. For every \vclaim registered with source
#          locators (source_keys: a JSON Pointer into a .json/.yaml source, or
#          a row/column cell of a .csv/.tsv), re-read the value from the
#          claim's source file NOW and compare it with the claim value that
#          will be rendered, within the declared tolerance (or the tolerance
#          implied by the precision the value is written with).
#
#          Why: clew's hash check proves the source FILE is unchanged since
#          registration; it cannot prove the number in the manuscript is the
#          number IN that file. A claim typed as 0.91 against a JSON saying
#          0.81 hashes perfectly. This check catches exactly that.
#
#          Claims are read from the scitex-clew store (the single claim store;
#          00_shared/claims.json is only its derived export). If clew or its
#          store is unavailable the check FAILS LOUDLY -- it never falls back
#          to the JSON file and never reports an unchecked claim as passing.
#
#          Severity off|warn|error (default error -- a mismatched number is a
#          wrong result in the paper):
#            off   -- skip (prints a loud "disabled (level=off)" note)
#            warn  -- report, exit 0
#            error -- report, exit 1 (blocks the compile)
#          Precedence: --level, env SCITEX_WRITER_CLAIM_VALUES, ./config.yaml
#          claim_values.level, ~/.scitex/writer/config.yaml, default error.
#
#          No-op (exit 0) when 00_shared/claims.json is absent: no claims.
#
# Usage:
#   python check_claim_values.py [project_dir] [--level off|warn|error]

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from _severity import resolve_level  # noqa: E402

GREEN = "\033[0;32m"
YELLOW = "\033[1;33m"
RED = "\033[0;31m"
DIM = "\033[0;90m"
BOLD = "\033[1m"
NC = "\033[0m"

_ENV = "SCITEX_WRITER_CLAIM_VALUES"


def _report(level, message):
    tag, color = ("FAIL", RED) if level == "error" else ("WARN", YELLOW)
    print(f"  {color}[{tag}]{NC} {message}")


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("project_dir", nargs="?", default=".")
    parser.add_argument("--level", choices=("off", "warn", "error"), default=None)
    args = parser.parse_args(argv)
    project_dir = Path(args.project_dir).resolve()

    level = resolve_level(
        "claim_values", args.level, project_dir, default="error", env_var=_ENV
    )
    print(f"\n{BOLD}=== Claim Value-vs-Source Check (level={level}) ==={NC}\n")
    if level == "off":
        print(f"  {YELLOW}[WARN]{NC} claim value-vs-source check disabled (level=off)")
        return 0
    if not (project_dir / "00_shared" / "claims.json").exists():
        print(
            f"  {GREEN}[PASS]{NC} no claims registered (00_shared/claims.json absent)"
        )
        return 0

    blocking = 1 if level == "error" else 0
    try:
        from scitex_writer._mcp.handlers._claim import check_claim_values
    except Exception as exc:  # broken install -- surface it, never skip silently
        _report(level, f"cannot import scitex_writer to check claim values: {exc}")
        return blocking

    result = check_claim_values(str(project_dir))
    if not result.get("success"):
        _report(
            level,
            "claim values could NOT be checked (this is not a pass): "
            f"{result.get('error')}",
        )
        return blocking

    for row in result["checked"]:
        print(f"  {GREEN}[PASS]{NC} {row['claim_id']}.{row['field']}: {row['detail']}")
    for row in result["mismatches"]:
        _report(level, f"{row['claim_id']}.{row['field']}: {row['detail']}")
    if result["unlocated"]:
        print(
            f"    {DIM}{len(result['unlocated'])} claim(s) carry no source_keys, so "
            f"their values were NOT compared: {', '.join(result['unlocated'])}{NC}"
        )
    if result["mismatches"]:
        print(
            f"\n  {len(result['mismatches'])} claim value(s) disagree with their "
            "source. Re-register the claim with the current value "
            "(writer_claim_add) or fix the pipeline output."
        )
        return blocking
    return 0


if __name__ == "__main__":
    sys.exit(main())

# EOF
