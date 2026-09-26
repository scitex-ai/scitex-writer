#!/usr/bin/env python3
"""Validate that no workflow pins a RETIRED runner pool into its ``runs-on``.

Why this exists (the incident, stated once)
==========================================
``sdist-wheel-import`` (and the release workflow) routed through
``vars.CI_RUNS_ON`` with a literal fallback of
``["self-hosted","Linux","X64","scitex-ci"]``. The repo Actions variable
``CI_RUNS_ON`` was set to that same dead pool, and every ``scitex-ci`` /
``spartan-cpu`` runner is OFFLINE while four ``scitex-org-cpu`` runners are
online and idle. A job whose labels name a pool with zero online runners does
NOT fail — it queues forever, and a check that never starts is indistinguishable
from one that has not run yet. There is no red; 15 PRs sat stuck.

What this checks (the statically-decidable core)
================================================
For every job in ``.github/workflows/``, parse ``runs-on``. Two spellings are
possible:

* a VARIABLE seam  — ``runs-on: ${{ fromJSON(vars.CI_RUNS_ON || '<fallback>') }}``
* a FROZEN literal — ``runs-on: ["self-hosted", ..., "scitex-ci"]``

In BOTH cases the *statically readable* pool label(s) are what this guard
sees: the fallback string (the variable seam) or the literal list (frozen).
If any of those readable labels is in ``RETIRED_POOLS``, the job is armed to
queue forever on a dead pool, so it is a violation. The live value of the
variable is a repository-settings value no static reader can see — that part
is enforced by re-pointing the variable (see the runbook); this guard enforces
the part that IS visible in the repo, which is exactly the class that bit us.

This is the same seam the fleet guard (scitex_agent_container._runner_pool_guard)
enforces, narrowed to "the readable pool must be a SUPPORTED one, not a retired
one", so a stale fallback cannot hide behind a variable seam.

NOT a live-runner check: it validates the label against the supported/retired
convention (a pure function of the repo tree), not against the current online
runner census — the latter needs the fleet API and would make the guard
network-dependent.

Usage
=====
    python scripts/ci/validate_runner_pools.py [REPO_ROOT]   # exit 0 clean, 1 on violation
"""
from __future__ import annotations

import re
import sys
from dataclasses import dataclass
from pathlib import Path

try:
    import yaml
except ImportError:  # pragma: no cover - yaml is a project dep
    yaml = None

# GitHub's automatic labels: they narrow by capability, never by machine group.
_GENERIC = frozenset({"self-hosted", "linux", "windows", "macos", "x64", "x86", "arm", "arm64"})

# The org's SUPPORTED self-hosted pool (CI_RUNS_ON_DEFAULT in scitex_dev).
SUPPORTED_POOL = "scitex-org-cpu"

# Pools that are RETIRED — every runner in them is offline. A job readable to
# target any of these will queue forever. This is the violation set.
RETIRED_POOLS = frozenset({"scitex-ci", "spartan-cpu", "spartan-pooled-cpu"})

# Workflows that are PINNED to an explicit version-controlled pool and must NOT
# route through the hidden `vars.CI_RUNS_ON` seam. A set repository variable
# silently overrides any `|| '<fallback>'`, is not visible in a diff, and is not
# writable by the agent token — so for these gates the pool must be an explicit
# literal in the YAML (mirrored in .github/runner-pools.yaml), never a variable
# reference. The validator rejects any `vars.*` seam here.
#
# The pypi release workflow's filename contains non-ASCII characters (it displays
# with an elided "..."), so it is matched by prefix, not by a literal name.
def _is_pinned_workflow(wf_name: str) -> bool:
    return wf_name.startswith("sdist-wheel-import") or wf_name.startswith("pypi")


@dataclass(frozen=True)
class Violation:
    path: str
    job_id: str
    pool: str
    kind: str  # "frozen" | "fallback" | "hidden-seam"


def _pool_labels(text: str) -> list[str]:
    """Extract the pool-selecting labels from a runs-on text fragment.

    The readable pool appears as a JSON/YAML array; its items are double-quoted
    in the variable-seam spelling and (after YAML parses a frozen flow list into
    a Python list and we ``str()`` it) single-quoted. Both spellings must parse::

      * variable seam  — fromJSON(vars.CI_RUNS_ON || '["self-hosted",...,"scitex-ci"]')
      * frozen literal — ["self-hosted", ..., "scitex-ci"]  (-> str(): single-quoted)

    We isolate every ``[...]`` span and read its quoted items (either quote
    type), returning only the labels that select a machine group — the
    GitHub-automatic capability labels (matched case-insensitively, since the
    workflows spell them ``Linux``/``X64``) and ``vars.`` references are dropped.
    """
    labels: list[str] = []
    for span in re.findall(r"\[[^\]]*\]", text):
        for tok in re.findall(r"['\"]([^'\"]+)['\"]", span):
            if tok.lower() in _GENERIC or tok.startswith("vars."):
                continue
            labels.append(tok)
    return labels


def _iter_runs_on(workflows_dir: Path):
    """Yield (relpath, job_id, runs_on_text) for every job in every workflow."""
    for wf in sorted(workflows_dir.glob("*.y*ml")):
        if yaml is None:
            # Degrade to a raw text scan so the guard still runs without yaml.
            for m in re.finditer(r"runs-on:\s*(.+)", wf.read_text(encoding="utf-8")):
                yield wf.name, "<job>", m.group(1).strip()
            continue
        try:
            doc = yaml.safe_load(wf.read_text(encoding="utf-8"))
        except yaml.YAMLError:
            continue
        if not isinstance(doc, dict) or "jobs" not in doc:
            continue
        for job_id, job in (doc.get("jobs") or {}).items():
            if not isinstance(job, dict):
                continue
            # A composite/reusable workflow (uses:) has no runs-on of its own.
            if "runs-on" in job:
                ro = job["runs-on"]
                yield wf.name, str(job_id), ro if isinstance(ro, str) else str(ro)


def check_repo(root: Path) -> list[Violation]:
    """Return violations for the pinned workflows.

    Two independent rules (both statically decidable, so both fail loudly):

    1. **retired pool** — any readable pool label (frozen literal OR variable
       fallback) that names a RETIRED_POOL queues forever;
    2. **hidden seam** — a PINNED workflow must name its pool as an EXPLICIT
       literal in version control. Routing through `vars.CI_RUNS_ON` is
       rejected because a set repository variable silently overrides the
       fallback, is not visible in a diff, and is not writable by the agent
       token — exactly the failure that stalled sdist on `scitex-ci`.
    """
    workflows = root / ".github" / "workflows"
    if not workflows.is_dir():
        return []
    out: list[Violation] = []
    for path, job_id, ro_text in _iter_runs_on(workflows):
        for label in _pool_labels(ro_text):
            if label in RETIRED_POOLS:
                kind = "fallback" if "vars." in ro_text else "frozen"
                out.append(Violation(path, job_id, label, kind))
        if _is_pinned_workflow(path) and "vars." in ro_text:
            # Name the offending label for triage (the readable pool), or mark
            # it as the raw seam if no concrete label is readable.
            labels = [l for l in _pool_labels(ro_text) if l not in _GENERIC]
            out.append(Violation(path, job_id, labels[0] if labels else "(variable)", "hidden-seam"))
    return out


def format_report(root: Path, violations: list[Violation]) -> str:
    if not violations:
        return (
            f"runner-pool validator: OK — no workflow in {root / '.github' / 'workflows'} "
            f"reads a retired pool ({', '.join(sorted(RETIRED_POOLS))}), and the pinned "
            f"workflows name their pool explicitly (no hidden vars.CI_RUNS_ON seam)."
        )
    lines = ["runner-pool validator: VIOLATIONS:", ""]
    for v in violations:
        if v.kind == "hidden-seam":
            lines.append(
                f"  {v.path} :: {v.job_id}: routes through a hidden `vars.*` seam. "
                f"Pinned workflows must use an EXPLICIT label list in YAML "
                f"([\"self-hosted\", \"Linux\", \"X64\", \"{SUPPORTED_POOL}\"]) — a set "
                f"repo variable silently overrides the fallback and cannot be "
                f"written by the agent token."
            )
        else:
            lines.append(
                f"  {v.path} :: {v.job_id}: readable pool '{v.pool}' ({v.kind}) "
                f"is retired; use '{SUPPORTED_POOL}'."
            )
    lines.append("")
    lines.append("  Re-point the pool by editing the workflow's runs-on literal AND")
    lines.append(f"  .github/runner-pools.yaml (the version-controlled SSOT), not a hidden variable.")
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    root = Path(argv[0]) if argv else Path.cwd()
    violations = check_repo(root)
    print(format_report(root, violations))
    return 1 if violations else 0


if __name__ == "__main__":
    raise SystemExit(main())
