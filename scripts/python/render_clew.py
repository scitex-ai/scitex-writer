#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# ROLE: engine-vendored — DO NOT edit here. `scitex-writer update-project`
# overwrites this file on every re-vendor; fix it upstream in the
# scitex-writer package instead (local edits are lost, and update-project
# may set it read-only in the consumer workspace after vendoring).
# File: scripts/python/render_clew.py
# Purpose: Pre-compile generation step -- emit 00_shared/clew_rendered.tex from
#          scitex-clew's runtime export (.scitex/clew/runtime/claims.json,
#          schema v1.3) before the manuscript is flattened. scitex-clew stays
#          RENDERER-AGNOSTIC (it exports JSON, not TeX by design), so turning
#          that JSON into the LaTeX the clew presentation layer consumes is
#          WRITER's job. packages.tex already \input{00_shared/clew_rendered.tex}
#          (skipped if absent), so once this writes the file it is picked up.
#
#          Output contract (see 00_shared/latex_styles/clew_presentation.tex +
#          demo/clew_rendered.sample.tex):
#            \makeatletter
#            \definecolor{clewVerified|Suspect|Unverified|Exception}{HTML}{hex}
#            \def\clew@total{N} \def\clew@verified{M} \def\clew@allverified{0|1}
#            \@namedef{clew@val@<id>}{value}      (id sanitized to [a-zA-Z0-9])
#            \@namedef{clew@hex@<id>}{6hex}
#            \@namedef{clew@status@<id>}{status}
#            \@namedef{clew@link@<id>}{link}      (source path/URL, LaTeX-escaped;
#                                                  emitted only when non-empty)
#            \makeatother
#
#          Claim VALUES are emitted VERBATIM -- clew provides display-ready
#          strings (the sample carries intentional math like $\times$ and
#          pre-escaped \_), so we do NOT re-escape (that would double-escape).
#
#          FAIL LOUD: if claims.json exists but is malformed / unreadable, exit
#          non-zero so the compile aborts rather than shipping a stale or empty
#          clew_rendered.tex. No-op (exit 0) when claims.json is absent -- the
#          clew layer is optional.
#
# Usage:
#   python render_clew.py [project_dir]

import json
import os
import re
import sys
from pathlib import Path

CLAIMS_JSON = ".scitex/clew/runtime/claims.json"
OUTPUT_TEX = "00_shared/clew_rendered.tex"

# status -> the \definecolor name the presentation layer expects.
_STATUS_COLOR = {
    "verified": "clewVerified",
    "suspect": "clewSuspect",
    "unverified": "clewUnverified",
    "exception": "clewException",
}
# Schema-version tolerance: clew's unified feed 1.5 RENAMED the red state
# "unverified" -> "failed" (and 1.3 claims.json "partial" -> "suspect").
# Normalize incoming status/palette keys to the internal 4 buckets above, so
# every feed version renders correctly with no version gate.
# NB: clew 1.6's `unsourced` (unproven-source) state is folded onto the amber
# `suspect` bucket in _verdict() ONLY -- NOT here -- because this map is also
# applied to palette keys, and clew emits BOTH `suspect` and `unsourced` hexes;
# a synonym here would let unsourced clobber the suspect palette color.
_STATUS_SYNONYMS = {
    "failed": "unverified",
    "partial": "suspect",
}
# Fallback palette -- clew's canonical CUD-safe (colorblind-safe) reader-bucket
# hexes, matching clew's emitted display_palette (all clear the CIE76 dE>=12
# floor across CVD types). Only used when claims.json carries no palette hex for
# a state; clew's emitted palette + per-claim display_color still override.
# Operator ruled (Q1=b): provenance marks use clew's CUD-safe palette, NOT the
# raw figrecipe SciTeX hexes (verified-green #14B414 vs suspect-yellow #E6A014
# collapse to indistinguishable under protanopia) -- so even the clew-absent
# fallback stays accessible.
_DEFAULT_PALETTE = {
    "verified": "2DA44E",
    "suspect": "D29922",
    "unverified": "CF222E",
    "exception": "8250DF",
}


def sanitize_id(claim_id):
    """[a-zA-Z0-9]-only key -- the SAME transform clew_presentation.tex applies
    to \\clewval{id}, so the emitted macro name matches the call site."""
    return re.sub(r"[^a-zA-Z0-9]", "", str(claim_id))


def _hex(value):
    """Normalize a color to bare 6-hex uppercase, or None."""
    if not value:
        return None
    h = str(value).lstrip("#").strip().upper()
    return h if re.fullmatch(r"[0-9A-F]{6}", h) else None


def _first(d, *keys):
    """First present, non-empty value among ``keys`` in dict ``d``."""
    for k in keys:
        v = d.get(k)
        if v not in (None, ""):
            return v
    return None


# scitex-writer registers its \vclaim values IN clew (one claim store); the
# writer-only fields ride in claim_value as a JSON envelope whose `display`
# member is the display-ready string. Show that, never the raw JSON.
_WRITER_ENVELOPE = "scitex-writer-claim/1"


def _unwrap_writer_envelope(value):
    if isinstance(value, str) and value.lstrip().startswith("{"):
        try:
            payload = json.loads(value)
        except ValueError:
            return value
        if isinstance(payload, dict) and payload.get("schema") == _WRITER_ENVELOPE:
            return payload.get("display") or ""
    return value


def _claim_value(claim):
    """The display string for a claim. clew stores it display-ready; try the
    known field names in order (`claim_value` is the clew 0.2.19 key)."""
    v = _first(
        claim,
        "claim_value",
        "value",
        "display_value",
        "latex",
        "rendered_value",
        "text",
    )
    v = _unwrap_writer_envelope(v)
    return "" if v is None else str(v)


# LaTeX special characters -> their escaped, display-safe forms. Unlike claim
# VALUES (which clew emits display-ready and we pass verbatim), the link is a
# RAW filesystem path / URL (contains _ # % ~ & $ { } etc.), so it MUST be made
# LaTeX-safe before emission -- a bare `%` would comment out the line, a bare
# `_` errors outside math, etc. This is the "escape consistent with how the file
# handles other non-verbatim text" the contract calls for.
_LATEX_ESCAPES = {
    "\\": r"\textbackslash{}",
    "&": r"\&",
    "%": r"\%",
    "$": r"\$",
    "#": r"\#",
    "_": r"\_",
    "{": r"\{",
    "}": r"\}",
    "~": r"\textasciitilde{}",
    "^": r"\textasciicircum{}",
}


def _latex_escape(text):
    """Escape LaTeX-special characters in ``text`` (char-by-char, no re-scan of
    the replacements) so an arbitrary path/URL is safe to emit into a TeX macro
    body and to feed hyperref's \\pdfstringdef for the PDF tooltip string."""
    return "".join(_LATEX_ESCAPES.get(ch, ch) for ch in text)


def _claim_link(claim):
    """The resolvable source pointer for a claim: ``link`` (clew's per-entry
    source pointer -- a source_file path for value/figure claims, a scholar/doi
    URL for citation claims), falling back to ``source_file``. Mirrors the
    _first(...) accessor pattern. Empty string when the claim has no link."""
    v = _first(claim, "link", "source_file")
    return "" if v is None else str(v)


#: Prefix of a link whose file lies outside the project root. Only the file
#: name follows it: the directory is the build host's, not the paper's.
EXTERNAL_LINK_PREFIX = "external: "

_URL_RE = re.compile(r"^[A-Za-z][A-Za-z0-9+.\-]*:(//|[^/\\])")


def _portable_link(link, root):
    r"""The link as the rendered .tex may carry it: never a build-host path.

    clew >= 0.37.2 already names in-project files relative to the project root;
    an older feed (or one exported from another checkout) carries the absolute
    path recorded on whichever machine and checkout registered the claim, and
    that path would be baked into the tracked, flattened manuscript.tex and the
    PDF tooltip. So, resolved against ``root`` (the project the feed belongs
    to) at render time:

    * URLs (``https://doi.org/...``, ``doi:...``) and relative paths: unchanged;
    * an absolute path inside ``root``: the POSIX path relative to ``root``;
    * an absolute path outside ``root``: ``external: <file name>`` -- the
      directory says where the authors' files were, nothing about the paper.
    """
    if not link or root is None or _URL_RE.match(link):
        return link
    path = Path(link)
    if not path.is_absolute():
        return link
    root = Path(root)
    for base in dict.fromkeys((root, root.resolve())):
        for candidate in dict.fromkeys((path, path.resolve())):
            try:
                return candidate.relative_to(base).as_posix()
            except ValueError:
                continue
    return f"{EXTERNAL_LINK_PREFIX}{path.name}"


def _verdict(claim):
    """Map a claim to one of the 4 presentation states (verified / suspect /
    unverified / exception).

    clew v1.3 emits a 4-state ``status`` directly (pass through). clew 0.2.19
    emits ``status: registered`` + a ``verified_at`` (or null) and NO
    verdict/color -- so a claim is ``verified`` only once chain-verified
    (``verified_at`` set), else ``unverified`` (red). A registered-but-unverified
    claim renders RED, honestly (never green until verified).

    clew 1.6's ``unsourced`` (unproven-source) state folds onto the amber
    ``suspect`` bucket -- the writer keeps a single amber "questionable" state
    rather than a separate unsourced bucket (operator decision)."""
    status = str(claim.get("status", "")).strip().lower()
    status = _STATUS_SYNONYMS.get(status, status)  # 1.5 "failed" -> red bucket
    if status == "unsourced":
        return "suspect"  # clew 1.6 unproven-source -> amber suspect (one amber state)
    if status in _STATUS_COLOR:
        return status
    return "verified" if claim.get("verified_at") else "unverified"


def _resolve_palette(data):
    """status -> hex, from the top-level palette (dict or list of entries),
    falling back to the default palette for any missing state. Palette keys
    are normalized through the status synonyms (1.5 keys the red state
    "failed"), so the feed's hex lands on the right internal bucket."""
    palette = dict(_DEFAULT_PALETTE)
    raw = data.get("palette") or data.get("display_palette") or {}
    if isinstance(raw, dict):
        for status, color in raw.items():
            h = _hex(
                color if not isinstance(color, dict) else _first(color, "hex", "color")
            )
            key = _STATUS_SYNONYMS.get(str(status).lower(), str(status).lower())
            if h:
                palette[key] = h
    return palette


def _aggregate(data, claims):
    """(total, verified, allverified) from the attestation block, else counted
    from the claims themselves. Accepts both attestation shapes: the flat
    {verified_count, unverified_count} (<=1.4) and the 1.5 nested
    {counts: {total, verified, ...}, badge_state}."""
    att = data.get("attestation") or {}
    counts = att.get("counts") if isinstance(att.get("counts"), dict) else {}
    verified = counts.get("verified", att.get("verified_count"))
    total = counts.get("total")
    if not isinstance(total, int):
        unverified = att.get("unverified_count")
        if isinstance(verified, int) and isinstance(unverified, int):
            total = verified + unverified
    if not (isinstance(total, int) and isinstance(verified, int)):
        # No usable attestation -- count via the resolved verdict.
        total = len(claims)
        verified = sum(1 for c in claims if _verdict(c) == "verified")
    allverified = 1 if (total > 0 and verified == total) else 0
    return total, verified, allverified


def _clew_version(data):
    """The scitex-clew TOOL version that produced this export, for the rendered
    provenance attestation. Prefer the export's own stamp (authoritative for
    THIS file -- the version that produced it, not whatever CLI is installed);
    fall back to the CLI version render_clew.sh captured into
    SCITEX_WRITER_CLEW_VERSION. clew stamps it at ``attestation.version``
    (= importlib.metadata.version("scitex-clew") at export time). A bare
    TOP-LEVEL ``version`` is deliberately NOT read -- that is the SCHEMA
    version, not the tool version. Sanitized to a LaTeX-safe [0-9A-Za-z.-]
    token (never trust the string blindly)."""
    v = _first(data, "clew_version", "tool_version", "generator_version")
    if not v:
        att = data.get("attestation")
        if isinstance(att, dict):
            # attestation.version = the producing scitex-clew tool version.
            v = att.get("version") or att.get("clew_version") or att.get("tool_version")
    if not v:
        v = os.environ.get("SCITEX_WRITER_CLEW_VERSION")
    v = "" if v is None else str(v).strip()
    return re.sub(r"[^0-9A-Za-z.\-]", "", v)


def _iter_claims(data):
    """The claim records, whether claims.json stores them as a list or a dict
    keyed by claim_id."""
    claims = data.get("claims", data)
    if isinstance(claims, dict):
        out = []
        for cid, rec in claims.items():
            rec = dict(rec)
            rec.setdefault("claim_id", cid)
            out.append(rec)
        return out
    return list(claims) if isinstance(claims, list) else []


def render_clew_tex(data, root=None):
    r"""Render the clew_rendered.tex body from a parsed claims.json (v1.3).

    ``root`` is the project root the feed belongs to; links are made portable
    against it (:func:`_portable_link`). ``None`` emits links as given."""
    claims = _iter_claims(data)
    palette = _resolve_palette(data)
    total, verified, allverified = _aggregate(data, claims)

    lines = ["\\makeatletter", ""]
    lines.append(
        "%% --- palette (from clew claims.json; writer has \\providecolor fallbacks) ---"
    )
    for status, name in _STATUS_COLOR.items():
        lines.append(f"\\definecolor{{{name}}}{{HTML}}{{{palette[status]}}}")
    lines += ["", "%% --- aggregate ---"]
    lines.append(f"\\def\\clew@total{{{total}}}")
    lines.append(f"\\def\\clew@verified{{{verified}}}")
    lines.append(f"\\def\\clew@allverified{{{allverified}}}")
    version = _clew_version(data)
    if version:
        lines.append(f"\\def\\clew@version{{{version}}}")
    lines += ["", "%% --- per-claim data (id sanitized to [a-zA-Z0-9]) ---"]

    for claim in claims:
        cid = sanitize_id(_first(claim, "claim_id", "id") or "")
        if not cid:
            continue
        # Resolve the 4-state verdict (v1.3 status pass-through, or 0.2.19
        # registered->verified/unverified), then the color: a per-claim color
        # field if clew emitted one (v1.3), else the palette entry for the
        # verdict (0.2.19 has no color, so derive it).
        verdict = _verdict(claim)
        # `display_color` is the frozen contract name (clew 0.4.0 emits it);
        # color/hex are accepted aliases. Fall back to the verdict palette.
        color = _hex(_first(claim, "display_color", "color", "hex")) or palette.get(
            verdict
        )
        value = _claim_value(claim)
        lines.append(f"%% {claim.get('claim_id', cid)} [{verdict}]")
        lines.append(f"\\@namedef{{clew@val@{cid}}}{{{value}}}")
        if color:
            lines.append(f"\\@namedef{{clew@hex@{cid}}}{{{color}}}")
        lines.append(f"\\@namedef{{clew@status@{cid}}}{{{verdict}}}")
        # Source pointer (LaTeX-escaped): emitted only when the claim carries a
        # non-empty link, so a link-less claim's tooltip degrades to status-only.
        link = _portable_link(_claim_link(claim), root)
        if link:
            lines.append(f"\\@namedef{{clew@link@{cid}}}{{{_latex_escape(link)}}}")
        lines.append("")

    lines.append("\\makeatother")
    return "\n".join(lines) + "\n"


def _find_git_root(start):
    """Nearest ancestor of ``start`` containing ``.git`` (a git root), or None.
    Bounded walk so a pathological tree can't spin."""
    cur = start
    for _ in range(64):
        if (cur / ".git").exists():
            return cur
        if cur.parent == cur:
            return None
        cur = cur.parent
    return None


def _resolve_claims_json(project_path):
    r"""Locate .scitex/clew/runtime/claims.json the way clew resolves its OWN db:
    at the GIT ROOT. This makes NESTED-writer projects work -- when scitex-writer
    is vendored UNDER an outer repo (e.g. at ``.scitex/writer/``) whose
    ``.scitex/clew`` at the git root is the real feed, clew writes the export at
    the git root, so render_clew must READ it there too (not under the writer
    subdir). Preference: git-root/.scitex/clew when that dir exists; else fall
    back to project_path/.scitex/clew -- the flat/common case (project IS its own
    git root) is unchanged, and a stray empty .scitex/clew under the writer
    subdir is ignored in favor of the real git-root feed. (nested-writer bug
    surfaced by paper-neurovista, 2026-07-04.)"""
    root = _find_git_root(project_path)
    if root is not None and (root / ".scitex" / "clew").is_dir():
        return root / ".scitex" / "clew" / "runtime" / "claims.json"
    return project_path / CLAIMS_JSON


def main(argv):
    project_dir = argv[1] if len(argv) > 1 else "."
    project_path = Path(project_dir).resolve()
    claims_json = _resolve_claims_json(project_path)

    if not claims_json.exists():
        return 0  # clew layer optional -- no-op

    try:
        data = json.loads(claims_json.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        print(
            f"ERRO:     Cannot read clew claims.json ({claims_json}): {exc}. "
            f"Fix it or remove it; compiling now would ship a stale/empty "
            f"clew_rendered.tex.",
            file=sys.stderr,
        )
        return 1

    try:
        # <root>/.scitex/clew/runtime/claims.json -> <root>: the project the
        # feed's paths belong to (the git root for a nested writer).
        tex = render_clew_tex(data, root=claims_json.parents[3])
    except Exception as exc:  # malformed schema -- surface, don't ship stale
        print(
            f"ERRO:     Failed to render clew_rendered.tex from {claims_json}: {exc}.",
            file=sys.stderr,
        )
        return 1

    out = project_path / OUTPUT_TEX
    try:
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(tex, encoding="utf-8")
    except OSError as exc:
        print(f"ERRO:     Cannot write {out}: {exc}", file=sys.stderr)
        return 1

    n = len(_iter_claims(data))
    print(f"INFO:     Rendered clew_rendered.tex ({n} claims) from clew claims.json")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))

# EOF
