#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# ROLE: engine-vendored — DO NOT edit here. `scitex-writer update-project`
# overwrites this file on every re-vendor; fix it upstream in the
# scitex-writer package instead (local edits are lost, and update-project
# may set it read-only in the consumer workspace after vendoring).
# File: scripts/python/check_clew_verify.py
# Purpose: Pre-compile provenance GATE -- before a research manuscript is
#          compiled, re-verify every clew-registered claim against its bound
#          source (re-hash source files + walk the claim DAG; no analysis is
#          re-run). A failed verification ABORTS the compile, so a manuscript
#          can never ship a value whose source has drifted, gone missing, or
#          was never lineage-bound. Implements neurovista's ADR-0021 ("every
#          manuscript value must be clew-registered + source-verified").
#
#          Delegates the actual verification to the `clew` CLI
#          (scitex-clew >= 0.2.19, `clew verify`). This check is a thin,
#          severity-aware ADAPTER: it resolves a level, runs `clew verify`,
#          maps clew's exit codes to pass/warn/fail, and exits non-zero ONLY
#          at error-level with a real verification failure.
#
#          clew verify exit codes (from scitex-clew):
#            0   OK             -- all claims verified
#            10  UNVERIFIED     -- a claim is not verified
#            11  SOURCE_MISSING -- a bound source file is gone
#            12  HASH_MISMATCH  -- a bound source changed since binding
#            13  NO_LINEAGE     -- a claim has no lineage (only with --strict)
#            14-19, 21-24       -- citation, lineage, value and environment
#                                  failures; labels in _CLEW_CODES below,
#                                  contract in scitex_clew._cli._exit_codes
#            20  NO_CLAIMS      -- the project has no registered claims
#
#          NO_CLAIMS (20) is treated as a WARN regardless of level: a project
#          that has not yet adopted clew should not be hard-blocked from
#          compiling. A genuinely-empty claim set is "nothing to verify", not
#          "verification failed". Real failures (10/11/12/13) gate at the
#          resolved level.
#
#          DEFAULT depends on project type: a *research* project (marked by
#          .scitex/dev/config.yaml `project-type: research`) defaults to
#          `error` (gate ON); any other project defaults to `off`. CLI/env/
#          config always override the computed default.
#
#          If the `clew` CLI is not installed, the check WARNS (provenance
#          unverified) but never blocks -- the public template ships to many
#          projects that do not use clew, and a missing tool is an environment
#          gap, not a verification failure. Install scitex-clew to enable, or
#          set clew_verify.level: off to silence. The `require_claims` knob
#          (below) flips both NO_CLAIMS and a missing clew CLI into real
#          failures (ADR-0021: a research manuscript MUST have registered
#          claims AND clew present).
#
#          Severity precedence (highest -> lowest), mirroring the package's
#          documented config precedence:
#            1. --level {off,warn,error} CLI flag
#            2. env SCITEX_WRITER_CLEW_VERIFY
#            3. project ./config.yaml key clew_verify.level
#            4. user-wide ~/.scitex/writer/config.yaml key clew_verify.level
#            5. default: error for research projects, else off
#          strict / require_claims precedence (CLI only ever tightens):
#            1. --strict / --require-claims CLI flag (presence => true)
#            2. project ./config.yaml key clew_verify.{strict,require_claims}
#            3. user ~/.scitex/writer/config.yaml clew_verify.{strict,require_claims}
#            4. default false
#
# Usage:
#   python check_clew_verify.py [project_dir]
#                               [--level off|warn|error]
#                               [--strict] [--require-claims]
#
# Self-contained: stdlib + optional PyYAML (only needed to read config files).

import argparse
import os
import shutil
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from _severity import resolve_level  # noqa: E402

# ANSI colors (match check_media_provenance.py / check_paper_symlink.py)
GREEN = "\033[0;32m"
YELLOW = "\033[1;33m"
RED = "\033[0;31m"
DIM = "\033[0;90m"
BOLD = "\033[1m"
NC = "\033[0m"

PASS_COUNT = 0
WARN_COUNT = 0
FAIL_COUNT = 0

_LEVELS = ("off", "warn", "error")

# clew verify exit codes -> (short label, is_real_failure). NO_CLAIMS is NOT a
# real failure (nothing registered yet); it always degrades to a warning.
_CLEW_CODES = {
    0: ("OK", False),
    10: ("UNVERIFIED -- a claim is not source-verified", True),
    11: ("SOURCE_MISSING -- a bound source file is gone", True),
    12: ("HASH_MISMATCH -- a bound source changed since it was registered", True),
    13: ("NO_LINEAGE -- a claim has no lineage (strict)", True),
    14: ("CITATION_STUB -- a \\cite key resolves to a placeholder stub", True),
    15: ("CITATION_UNRESOLVED -- a cited key has no confirmed source", True),
    16: ("CITATION_UNLINKED -- a cited key has no clew citation node", True),
    17: ("UNSOURCED -- a claim's chain reaches no registered source", True),
    18: ("STALE_LINEAGE -- an input, script or run changed since recording", True),
    19: ("VERIFY_ERROR -- a claim could not be verified", True),
    20: ("NO_CLAIMS -- no clew claims registered in this project", False),
    21: ("VALUE_MISMATCH -- a stated value disagrees with its source", True),
    22: ("EXTERNAL_MISSING -- an input outside the project is absent here", True),
    23: ("ENV_NOT_REPRODUCIBLE -- a package used is not reproducible", True),
    24: ("VALUE_UNCHECKED -- a stated value could not be checked (strict)", True),
}

# Env override for the clew executable (else found on PATH).
_CLEW_BIN_ENV = "SCITEX_WRITER_CLEW_BIN"


def log_pass(msg):
    global PASS_COUNT
    print(f"  {GREEN}[PASS]{NC} {msg}")
    PASS_COUNT += 1


def log_warn(msg):
    global WARN_COUNT
    print(f"  {YELLOW}[WARN]{NC} {msg}")
    WARN_COUNT += 1


def log_fail(msg):
    global FAIL_COUNT
    print(f"  {RED}[FAIL]{NC} {msg}")
    FAIL_COUNT += 1


def log_detail(msg):
    print(f"    {DIM}{msg}{NC}")


def _read_block(config_path, key):
    """Read mapping ``key`` from a YAML config, or ``{}`` (PyYAML optional)."""
    if not config_path.exists():
        return {}
    try:
        import yaml
    except ImportError:
        return {}
    try:
        data = yaml.safe_load(config_path.read_text(encoding="utf-8")) or {}
    except Exception:
        return {}
    if not isinstance(data, dict):
        return {}
    block = data.get(key)
    return block if isinstance(block, dict) else {}


def _is_research_project(project_dir):
    """True iff .scitex/dev/config.yaml marks this a ``project-type: research``.

    This mirrors the marker scitex-dev enforces research-mode rules on. PyYAML
    is optional; absent it we read the file as text and look for the marker so
    the default still flips ON for research projects without yaml installed.
    """
    cfg = project_dir / ".scitex" / "dev" / "config.yaml"
    if not cfg.is_file():
        return False
    try:
        text = cfg.read_text(encoding="utf-8")
    except OSError:
        return False
    try:
        import yaml

        data = yaml.safe_load(text) or {}
        if isinstance(data, dict):
            return str(data.get("project-type", "")).strip().lower() == "research"
    except Exception:
        pass
    # Fallback: textual marker (tolerant of quoting / spacing).
    for line in text.splitlines():
        stripped = line.strip()
        if stripped.startswith("project-type:"):
            return stripped.split(":", 1)[1].strip().strip("\"'").lower() == "research"
    return False


def _resolve_clew_bool(key, cli_flag, project_dir):
    """Resolve a clew_verify boolean knob. The CLI flag only ever tightens (true)."""
    if cli_flag:
        return True
    for cfg in (
        Path(project_dir) / "config.yaml",
        Path.home() / ".scitex" / "writer" / "config.yaml",
    ):
        val = _read_block(cfg, "clew_verify").get(key)
        if isinstance(val, bool):
            return val
    return False


def resolve_strict(cli_flag, project_dir):
    """Resolve strict mode. The CLI flag only ever tightens (true)."""
    return _resolve_clew_bool("strict", cli_flag, project_dir)


def resolve_require_claims(cli_flag, project_dir):
    """Resolve require_claims. The CLI flag only ever tightens (true).

    When true, the two normally-soft conditions -- NO_CLAIMS (clew has zero
    registered claims) and a missing clew CLI -- are reclassified as real
    verification failures, so they gate at the resolved level (block at error).
    This enforces ADR-0021 for research projects: a manuscript MUST have
    registered claims AND clew present. Default false (the public template
    keeps both soft).
    """
    return _resolve_clew_bool("require_claims", cli_flag, project_dir)


def _find_clew():
    """Locate the clew executable (env override first), or None."""
    override = os.environ.get(_CLEW_BIN_ENV, "").strip()
    if override:
        return (
            override if (Path(override).is_file() or shutil.which(override)) else None
        )
    return shutil.which("clew")


def _run_clew_verify(clew_bin, project_dir, strict):
    """Run ``clew verify`` in ``project_dir``; return (exit_code, output)."""
    cmd = [clew_bin, "verify"]
    if strict:
        cmd.append("--strict")
    try:
        proc = subprocess.run(
            cmd,
            cwd=str(project_dir),
            capture_output=True,
            text=True,
            timeout=120,
        )
    except subprocess.TimeoutExpired:
        return 124, "clew verify timed out after 120s"
    except OSError as exc:
        return 125, f"could not execute clew: {exc}"
    output = (proc.stdout or "") + (proc.stderr or "")
    return proc.returncode, output.strip()


def main():
    parser = argparse.ArgumentParser(
        description="Pre-compile clew provenance gate: re-verify every "
        "registered claim against its bound source before compiling. "
        "Defaults ON (error) for research projects, off otherwise."
    )
    parser.add_argument("project_dir", nargs="?", default=".")
    parser.add_argument(
        "--level",
        choices=list(_LEVELS),
        default=None,
        help="Severity: off, warn, or error. Overrides env and config.",
    )
    parser.add_argument(
        "--strict",
        action="store_true",
        help="Pass --strict to clew (a claim with no lineage becomes a failure).",
    )
    parser.add_argument(
        "--require-claims",
        action="store_true",
        help="Reclassify NO_CLAIMS and a missing clew CLI as real failures "
        "(so they gate at the resolved level). Enforces ADR-0021.",
    )
    args = parser.parse_args()

    project_dir = Path(args.project_dir).resolve()
    research = _is_research_project(project_dir)
    default = "error" if research else "off"
    level = resolve_level(
        "clew_verify",
        args.level,
        project_dir,
        default=default,
        env_var="SCITEX_WRITER_CLEW_VERIFY",
    )
    strict = resolve_strict(args.strict, project_dir)
    require_claims = resolve_require_claims(args.require_claims, project_dir)

    # When require_claims is set, the two normally-soft conditions become real
    # failures and gate at the resolved level; otherwise they stay warnings.
    soft_report = (
        (log_fail if level == "error" else log_warn) if require_claims else log_warn
    )

    mode = "strict" if strict else "basic"
    if require_claims:
        mode += "+require-claims"
    kind = "research" if research else "non-research"
    print(f"\n{BOLD}=== Clew Provenance Gate (level={level}, {mode}, {kind}) ==={NC}\n")

    if level == "off":
        print(
            f"  {DIM}[INFO]{NC} clew provenance gate is disabled (level=off). "
            f"Set clew_verify.level or --level to enable."
        )
        print(
            f"\n{BOLD}Summary:{NC} {GREEN}0 passed{NC}, "
            f"{YELLOW}0 warnings{NC}, {RED}0 errors{NC}"
        )
        return 0

    clew_bin = _find_clew()
    if clew_bin is None:
        # Missing tool is normally an environment gap (warn). With
        # require_claims it is a real failure: a research build cannot certify
        # provenance without clew present.
        soft_report(
            "clew CLI not found -- manuscript provenance is UNVERIFIED for this build."
        )
        log_detail(
            "install scitex-clew (>=0.2.19) to enable verification, set "
            f"{_CLEW_BIN_ENV}, or set clew_verify.level: off to silence."
        )
        print()
        print(
            f"{BOLD}Summary:{NC} {GREEN}{PASS_COUNT} passed{NC}, "
            f"{YELLOW}{WARN_COUNT} warnings{NC}, {RED}{FAIL_COUNT} errors{NC}"
        )
        return 1 if FAIL_COUNT > 0 else 0

    code, output = _run_clew_verify(clew_bin, project_dir, strict)
    label, is_failure = _CLEW_CODES.get(code, (f"clew exited {code}", True))

    if code == 0:
        log_pass("all registered claims verified against their bound sources")
    elif not is_failure:
        # NO_CLAIMS (20): nothing registered yet. Soft (warn) by default; a real
        # failure when require_claims is set (ADR-0021 needs registered claims).
        soft_report(label)
        log_detail(
            "no manuscript values are clew-verified yet; register claims with "
            "scitex-clew to enable the provenance gate."
        )
    else:
        report = log_fail if level == "error" else log_warn
        report(f"clew verify failed: {label}")
        if output:
            for line in output.splitlines()[: _max_detail_lines()]:
                log_detail(line)
        log_detail(
            "fix: re-run the analysis to rebind drifted sources, or update the "
            "claim, then `clew verify`. Override with clew_verify.level if intended."
        )

    print()
    print(
        f"{BOLD}Summary:{NC} {GREEN}{PASS_COUNT} passed{NC}, "
        f"{YELLOW}{WARN_COUNT} warnings{NC}, {RED}{FAIL_COUNT} errors{NC}"
    )
    return 1 if FAIL_COUNT > 0 else 0


def _max_detail_lines():
    return 40


if __name__ == "__main__":
    sys.exit(main())
