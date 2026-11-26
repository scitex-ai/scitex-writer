#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# ROLE: engine-vendored — DO NOT edit here. `scitex-writer update-project`
# overwrites this file on every re-vendor; fix it upstream in the
# scitex-writer package instead (local edits are lost, and update-project
# may set it read-only in the consumer workspace after vendoring).
# File: scripts/python/check_citation_trust.py
# Purpose: CITATION-TRUSTWORTHINESS check -- beyond "does the \cite key exist in
#          the .bib" (check_ref_integrity) and beyond "is the entry a scholar
#          stub" (check_citations): actually RESOLVE every cited entry against
#          the real bibliographic record (CrossRef / OpenAlex / arXiv / Semantic
#          Scholar) and flag the ones that cannot be shown to be a real,
#          trustworthy source.
#
#          Verification is DELEGATED to scitex-scholar (>= 1.2.1, the `scholar`
#          extra): `from scitex_scholar.verify_cites import verify_cites`.
#          "Trustworthy" in scholar's terms = the entry resolves to a real
#          source AND its claimed title fuzzy-matches what that source says
#          (>= min_confidence).
#          KNOWN GAP (not covered): scholar does NOT check retraction status or
#          predatory venues -- a resolvable, title-matching citation to a
#          RETRACTED paper still classifies as `verified` here.
#
#          Status -> severity mapping (agreed on card
#          writer-dynamic-paper-findings-feed):
#            verified                     -> info (suppressed; counted as pass)
#            unverified / stub / unlinked -> warning
#            lookup_failed                -> warning (NOT a verdict: the
#                                            metadata service rate-limited or
#                                            failed the lookup; never cached)
#            hallucinated                 -> error
#          A finding's severity is then CLAMPED by the resolved level: at
#          level=warn an error-mapped finding is still reported LOUDLY but does
#          not block (exit 0); at level=error it blocks (exit 1).
#
#          FAIL-LOUD, NEVER SILENTLY PASS. When verification is UN-RUNNABLE
#          (scitex-scholar not installed, bib unresolvable, network down,
#          resolver crash), the check reports the un-runnable condition at the
#          resolved level -- WARN by default, FAIL at level=error -- and emits
#          NO pass. No code path reports a citation as trustworthy without an
#          actual verdict for it.
#
#          CACHING is mandatory (scholar has none in this path); see
#          _citation_trust_cache.py. Verdicts are keyed by cite key + bib-entry
#          content hash in .scitex/writer/runtime/citation_trust.json; a cache
#          miss forces real verification; OFFLINE verdicts are never cached.
#
#          DEFAULT = warn: a network-dependent check must never block a compile
#          by default. Set citation_trust.level: error to gate.
#
#          Severity precedence: --level > env SCITEX_WRITER_CITATION_TRUST >
#          project ./config.yaml citation_trust.level > user
#          ~/.scitex/writer/config.yaml citation_trust.level > warn.
#
# Usage:
#   python check_citation_trust.py [project_dir] [--level off|warn|error]
#                                  [--bib PATH] [--offline]
#                                  [--min-confidence 0.8] [--no-cache]
#
# Self-contained: stdlib + optional PyYAML (config) + optional scitex-scholar
# (the verifier itself; its absence is reported LOUDLY, never as a pass).

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from _citation_trust_cache import (  # noqa: E402
    cache_lookup,
    cache_path,
    cache_store,
    entry_fingerprint,
    load_cache,
    save_cache,
)
from _severity import env_truthy, resolve_level  # noqa: E402
from check_citations import (  # noqa: E402
    _load_text,
    _resolve_tex_paths,
    extract_cited_keys,
    iter_bib_entries,
    resolve_bib_paths,
)

GREEN = "\033[0;32m"
YELLOW = "\033[1;33m"
RED = "\033[0;31m"
DIM = "\033[0;90m"
BOLD = "\033[1m"
NC = "\033[0m"

_LEVELS = ("off", "warn", "error")

# scitex-scholar verify_cites statuses (scitex_scholar.verify_cites._model).
VERIFIED = "verified"
UNVERIFIED = "unverified"
STUB = "stub"
HALLUCINATED = "hallucinated"
UNLINKED = "unlinked"
# The metadata service could not be ASKED (HTTP 429 rate limit, 5xx, network):
# a transient service condition, not a content verdict (scitex-scholar
# reports it since verify_cites grew LOOKUP_FAILED).
LOOKUP_FAILED = "lookup_failed"

# The agreed status -> canonical severity mapping. An UNKNOWN status is treated
# as an error, never as a pass -- fail-loud on anything unrecognised.
STATUS_SEVERITY = {
    VERIFIED: "info",
    UNVERIFIED: "warning",
    STUB: "warning",
    UNLINKED: "warning",
    HALLUCINATED: "error",
    LOOKUP_FAILED: "warning",
}

# Statuses whose verdict is a property of the bib entry and may be reused until
# the entry changes. LOOKUP_FAILED is a property of the service at that moment,
# so it is never cached -- the next compile asks again.
CACHEABLE_STATUSES = {s: v for s, v in STATUS_SEVERITY.items() if s != LOOKUP_FAILED}

_STATUS_EXPLAIN = {
    UNVERIFIED: "has an identifier but did NOT resolve (or its title matched "
    "below the confidence threshold)",
    STUB: "is an auto-generated placeholder -- no real metadata to verify",
    UNLINKED: "is cited but has no entry in the compiled bibliography",
    HALLUCINATED: "was not found in ANY source index -- it looks fabricated",
    LOOKUP_FAILED: "could NOT be checked -- the metadata service rate-limited or "
    "failed the lookup (a service condition, NOT a verdict on the citation; it "
    "is re-checked on the next run)",
}

# Force offline verification (no network) without touching the CLI.
OFFLINE_ENV = "SCITEX_WRITER_CITATION_TRUST_OFFLINE"


class VerificationUnavailable(RuntimeError):
    """Verification could not be RUN (missing scholar, bad bib, network, crash).

    Distinct from "verification ran and found problems". This is the fail-loud
    signal: the check reports it at the resolved level and never emits a PASS.
    """


class Reporter:
    """PASS/WARN/FAIL reporter with per-run counters (no module globals).

    ``exit_code()`` is 1 iff a real FAIL was reported, so an in-process caller
    (and a test) gets an exit code that depends only on THIS run.
    """

    def __init__(self):
        self.passed = 0
        self.warnings = 0
        self.errors = 0

    def log_pass(self, msg):
        print(f"  {GREEN}[PASS]{NC} {msg}")
        self.passed += 1

    def log_warn(self, msg):
        print(f"  {YELLOW}[WARN]{NC} {msg}")
        self.warnings += 1

    def log_fail(self, msg):
        print(f"  {RED}[FAIL]{NC} {msg}")
        self.errors += 1

    def log_detail(self, msg):
        print(f"    {DIM}{msg}{NC}")

    def at(self, severity):
        """The logger for ``severity`` ("error" -> FAIL, else WARN)."""
        return self.log_fail if severity == "error" else self.log_warn

    def summary(self):
        print()
        print(
            f"{BOLD}Summary:{NC} {GREEN}{self.passed} passed{NC}, "
            f"{YELLOW}{self.warnings} warnings{NC}, {RED}{self.errors} errors{NC}"
        )

    def exit_code(self):
        return 1 if self.errors > 0 else 0


def default_verifier(
    project_dir, bib=None, offline=False, min_confidence=0.8, cited_keys=None
):
    """Verify cited keys via scitex-scholar; return a list of verdict dicts.

    ``cited_keys`` is the set to verify (the gate's own cited set, so scholar
    does not re-scan the project's .tex on its own); ``None`` lets scholar
    discover them.

    Each verdict is ``{"key", "status", "detail", "confidence"}``. Raises
    :class:`VerificationUnavailable` when verification cannot be run at all
    (scitex-scholar absent, bib unresolvable, resolver/network failure) -- the
    caller turns that into a loud warning/error, never a pass.

    This is the DEFAULT injection seam: callers (and tests) pass a callable with
    the same signature to exercise the check without a network.
    """
    try:
        from scitex_scholar.verify_cites import verify_cites
    except Exception as exc:  # not installed, too old, or a broken install
        raise VerificationUnavailable(
            "scitex_scholar.verify_cites is unavailable "
            f"({type(exc).__name__}: {exc}), so citations could NOT be verified "
            "-- install the extra: uv pip install 'scitex-writer[all]'"
        ) from exc
    try:
        report = verify_cites(
            str(project_dir),
            bib=Path(bib) if bib else None,
            min_confidence=min_confidence,
            offline=offline,
            cited_keys=None if cited_keys is None else sorted(cited_keys),
            write=False,
        )
    except Exception as exc:  # resolver / network / bib failure -- never swallow
        raise VerificationUnavailable(
            f"scitex-scholar verify_cites() failed: {type(exc).__name__}: {exc}"
        ) from exc
    return [
        {
            "key": status.key,
            "status": (status.status or "").strip().lower(),
            "detail": getattr(status, "provenance", "") or "",
            "confidence": getattr(status, "match_confidence", None),
        }
        for status in report.statuses
    ]


def effective_severity(status, level):
    """Clamp a finding's mapped severity by the check's resolved ``level``.

    ``error`` findings only FAIL at level=error; at level=warn they are still
    reported loudly, but never block the compile.
    """
    mapped = STATUS_SEVERITY.get(status, "error")
    if mapped == "error" and level != "error":
        return "warning"
    return mapped


def _report_findings(reporter, verdicts, level):
    """Print one line per verdict group at its effective severity."""
    buckets = {}
    for verdict in verdicts:
        buckets.setdefault(verdict["status"], []).append(verdict)

    verified = buckets.pop(VERIFIED, [])
    if verified:
        reporter.log_pass(
            f"{len(verified)} citation(s) resolve to a real source with a "
            f"matching title (trustworthy)"
        )

    for status in (HALLUCINATED, UNVERIFIED, STUB, UNLINKED, LOOKUP_FAILED):
        found = buckets.pop(status, [])
        if not found:
            continue
        reporter.at(effective_severity(status, level))(
            f"{len(found)} citation(s) classified {status.upper()} -- "
            f"{_STATUS_EXPLAIN[status]}:"
        )
        for verdict in found:
            suffix = " (cached)" if verdict.get("cached") else ""
            detail = verdict.get("detail") or ""
            reporter.log_detail(f"\\cite{{{verdict['key']}}}{suffix} {detail}".rstrip())

    # Anything scholar reports that we do not recognise is an ERROR, not a pass.
    for status, found in sorted(buckets.items()):
        reporter.at("error" if level == "error" else "warning")(
            f"{len(found)} citation(s) have an UNRECOGNISED status {status!r} -- "
            f"treating as untrusted (writer/scholar version skew?):"
        )
        for verdict in found:
            reporter.log_detail(f"\\cite{{{verdict['key']}}}")


def _read_entries(reporter, bib_paths):
    """Merge bib entries across the resolved bibs (first occurrence wins)."""
    entries = {}
    for bib_path in bib_paths:
        reporter.log_detail(f"reading bib: {bib_path}")
        for key, fields in iter_bib_entries(
            bib_path.read_text(encoding="utf-8", errors="replace")
        ):
            entries.setdefault(key, fields)
    return entries


def run_check(
    project_dir,
    level=None,
    bib=None,
    offline=False,
    min_confidence=0.8,
    use_cache=True,
    tex=None,
    verifier=default_verifier,
):
    """Run the citation-trustworthiness check; return a process exit code.

    ``verifier`` is the injection seam (default :func:`default_verifier`, which
    calls scitex-scholar). Returns 1 iff a real FAIL was reported.
    """
    project_dir = Path(project_dir).resolve()
    reporter = Reporter()
    level = resolve_level(
        "citation_trust",
        level,
        project_dir,
        default="warn",
        env_var="SCITEX_WRITER_CITATION_TRUST",
    )
    offline = bool(offline) or env_truthy(OFFLINE_ENV)
    mode = "offline" if offline else "online"
    print(f"\n{BOLD}=== Citation Trustworthiness (level={level}, {mode}) ==={NC}\n")

    if level == "off":
        print(
            f"  {DIM}[INFO]{NC} citation-trust check is disabled (level=off). "
            f"Set citation_trust.level or --level to enable."
        )
        reporter.summary()
        return 0

    # A check that cannot RUN is reported AT the resolved level -- never a pass.
    unrunnable = reporter.at("error" if level == "error" else "warning")

    tex_paths = _resolve_tex_paths(project_dir, tex)
    cited_keys = extract_cited_keys(_load_text(tex_paths))
    if not cited_keys:
        reporter.log_warn(
            "no \\cite keys found in the scanned tex -- nothing to verify."
        )
        reporter.log_detail(f"scanned: {len(tex_paths)} tex file(s)")
        reporter.summary()
        return reporter.exit_code()

    bib_paths = resolve_bib_paths(project_dir, tex_paths, bib)
    if not bib_paths:
        unrunnable(
            "no bibliography resolved -- citations could NOT be verified for this "
            "build (they are NOT known to be trustworthy)."
        )
        reporter.log_detail(
            "fix: pass --bib, or add a \\bibliography{}/\\addbibresource{}."
        )
        reporter.summary()
        return reporter.exit_code()

    entries = _read_entries(reporter, bib_paths)
    fingerprints = {
        key: entry_fingerprint(entries[key]) for key in cited_keys if key in entries
    }

    cached = load_cache(cache_path(project_dir)) if use_cache else {}
    hits = {}
    if use_cache:
        for key in sorted(cited_keys):
            hit = cache_lookup(cached, key, fingerprints.get(key), CACHEABLE_STATUSES)
            if hit is not None:
                hits[key] = hit

    misses = sorted(set(cited_keys) - set(hits))
    if not misses:
        reporter.log_detail(
            f"all {len(hits)} cited key(s) served from the verdict cache "
            f"({cache_path(project_dir)})"
        )
        _report_findings(reporter, [hits[key] for key in sorted(hits)], level)
        reporter.summary()
        return reporter.exit_code()

    reporter.log_detail(
        f"verifying via scitex-scholar: {len(misses)} uncached cite key(s), "
        f"{len(hits)} cache hit(s)"
    )
    try:
        fresh = verifier(
            project_dir,
            bib=bib_paths[0],
            offline=offline,
            min_confidence=min_confidence,
            cited_keys=misses,
        )
    except VerificationUnavailable as exc:
        unrunnable(f"citations could NOT be verified for this build: {exc}")
        reporter.log_detail(
            f"{len(cited_keys)} cited reference(s) are therefore UNVERIFIED (NOT "
            f"proven trustworthy) -- this is NOT a pass."
        )
        reporter.log_detail(
            "fix: install the scholar extra / restore network access, or set "
            "citation_trust.level: off to silence this check deliberately."
        )
        reporter.summary()
        return reporter.exit_code()

    fresh = [v for v in fresh if v.get("key") in cited_keys]
    fresh_keys = {v["key"] for v in fresh}
    verdicts = list(fresh)
    # Keep cache hits for any key the verifier returned no verdict for.
    verdicts += [hits[key] for key in sorted(hits) if key not in fresh_keys]

    missing = sorted(set(cited_keys) - {v["key"] for v in verdicts})
    if missing:
        unrunnable(
            f"{len(missing)} cited key(s) got NO verdict from scitex-scholar -- "
            f"they are NOT verified:"
        )
        for key in missing:
            reporter.log_detail(f"\\cite{{{key}}}")

    # OFFLINE verdicts are never cached: an offline "unverified" must not poison
    # a later online run.
    if use_cache and not offline and fresh:
        save_cache(
            cache_path(project_dir),
            cache_store(cached, fresh, fingerprints, CACHEABLE_STATUSES),
        )

    _report_findings(reporter, verdicts, level)
    reporter.summary()
    return reporter.exit_code()


def main(argv=None, verifier=default_verifier):
    parser = argparse.ArgumentParser(
        description="Citation-trustworthiness check: resolve every cited entry "
        "against the real bibliographic record (via scitex-scholar) and flag the "
        "ones that cannot be shown to be real, trustworthy sources. Defaults to "
        "warn (a network-dependent check never blocks a compile by default) and "
        "fails LOUDLY -- never silently passes -- when it cannot run."
    )
    parser.add_argument("project_dir", nargs="?", default=".")
    parser.add_argument(
        "--level",
        choices=list(_LEVELS),
        default=None,
        help="Severity: off, warn (default), or error. Overrides env and config.",
    )
    parser.add_argument(
        "--tex",
        action="append",
        default=None,
        help="Tex file(s)/glob(s) to scan for \\cite keys (repeatable).",
    )
    parser.add_argument(
        "--bib",
        default=None,
        help="Bibliography .bib to verify against (default: the \\bibliography{} "
        "target resolved from the tex).",
    )
    parser.add_argument(
        "--offline",
        action="store_true",
        help="Never touch the network (deterministic; unresolvable entries are "
        "reported UNVERIFIED / HALLUCINATED, never as trustworthy).",
    )
    parser.add_argument(
        "--min-confidence",
        type=float,
        default=0.8,
        help="Minimum title-match confidence for a VERIFIED verdict (default 0.8).",
    )
    parser.add_argument(
        "--no-cache",
        action="store_true",
        help="Ignore (and do not write) the verdict cache; re-verify everything.",
    )
    args = parser.parse_args(argv)

    return run_check(
        args.project_dir,
        level=args.level,
        bib=args.bib,
        offline=args.offline,
        min_confidence=args.min_confidence,
        use_cache=not args.no_cache,
        tex=args.tex,
        verifier=verifier,
    )


if __name__ == "__main__":
    sys.exit(main())

# EOF
