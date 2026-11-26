#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# File: src/scitex_writer/_mcp/handlers/_claim_render.py

r"""``00_shared/claims_rendered.tex``: the ``\vclaim`` macros, generated.

How the file is loaded decides how it must be written. ``packages.tex`` loads
it with a plain top-level ``\input`` (the 2026-08-18 catcode fix), and the
flattener inlines it at top level too. So macro parameters are single ``#``.
A doubled ``##``, written for the older ``\IfFileExists{..}{BODY}`` wrapper,
reaches the stored macro body as a literal parameter token: every
``\vclaim`` then failed with "You can't use `macro parameter character #'".

Claim ids are free text (``acc_mean``, ``group-comparison``), but per-claim
macro names use the sanitised id (letters and digits). ``\vclaim{<id>}``
resolves the id it was given through an alias, ``v@claim@id@<id>`` ->
``<sanitised id>``. Before this, ``\vclaim`` looked up the RAW id and every id
with punctuation rendered as ``[claim:<id>]``.
"""

from typing import Dict, List

from ._claim_format import FORMAT_STYLES, _render_claim, _sanitize_id

#: The macro preamble (single ``#``: the file is loaded at top level).
PREAMBLE = r"""\makeatletter

%% \vclaim[style]{id} -- render a registered claim inline.
%% The id is resolved through v@claim@id@<id> -> its sanitised macro key, so
%% any id that can be typed in the braces works. Robust, so it is safe in
%% moving arguments (captions, section titles).
\DeclareRobustCommand{\vclaim}[2][nature]{%
  \@ifundefined{v@claim@id@#2}%
    {[\texttt{claim:\detokenize{#2}}]}%
    {\edef\v@claim@safe{\csname v@claim@id@#2\endcsname}%
     \ifvmode\leavevmode\fi
     \global\advance\v@claim@seq\@ne
     \edef\v@claim@n{\the\v@claim@seq}%
     \v@claim@mark{\detokenize{#2}}{\v@claim@n s}%
     \v@claim@maybecolor{\v@claim@safe}%
       {\csname v@claim@\v@claim@safe @#1\endcsname}%
     \v@claim@mark{\detokenize{#2}}{\v@claim@n e}}}

%% Claim positions for PDF readers (scripts/python/emit_claim_anchors.py
%% turns them into <pdf stem>.pdf-anchors.json after the compile). Every
%% printed \vclaim writes to the .aux, when its page is shipped out, where its
%% text starts and ends (\pdfsavepos). In a paragraph it also records the
%% left edge of the line in a \vadjust, so a claim that wraps across lines can
%% be boxed line by line. Record:
%%   \v@claimpos{id}{<n><s|e|sl|el>}{page}{x sp}{y sp}{indent}{width}{ht}{dp}
%% Engines without a savepos primitive, and \nofiles runs, record nothing.
\providecommand{\v@claimpos}[9]{}
\ifdefined\v@claim@seq\else\newcount\v@claim@seq\fi
\ifdefined\pdfsavepos
  \let\v@claim@savepos\pdfsavepos
  \def\v@claim@lastx{\the\pdflastxpos}%
  \def\v@claim@lasty{\the\pdflastypos}%
\else\ifdefined\savepos
  \let\v@claim@savepos\savepos
  \def\v@claim@lastx{\the\lastxpos}%
  \def\v@claim@lasty{\the\lastypos}%
\fi\fi
%% The physical page being shipped out (LaTeX 2020-10 and later); older
%% kernels fall back to the page counter.
\ifdefined\ReadonlyShipoutCounter
  \def\v@claim@page{\the\ReadonlyShipoutCounter}%
\else
  \def\v@claim@page{\the\c@page}%
\fi
%% \v@claim@record{id}{tag}{indent}{width}{ht}{dp}: savepos + deferred write.
\def\v@claim@record#1#2#3#4#5#6{%
  \edef\v@claim@rec{\write\@auxout{\string\v@claimpos{#1}{#2}%
    {\noexpand\v@claim@page}{\noexpand\v@claim@lastx}{\noexpand\v@claim@lasty}%
    {#3}{#4}{#5}{#6}}}%
  \v@claim@savepos\v@claim@rec}
%% \v@claim@mark{id}{<n>s|<n>e}: the claim's start or end mark.
\def\v@claim@mark#1#2{%
  \ifdefined\v@claim@savepos\if@filesw
    \v@claim@record{#1}{#2}{\the\dimexpr\@totalleftmargin\relax}%
      {\the\linewidth}{\the\ht\strutbox}{\the\dp\strutbox}%
    \ifhmode\ifinner\else
      \vadjust{\v@claim@record{#1}{#2l}{0pt}{0pt}{0pt}{0pt}}%
    \fi\fi
  \fi\fi}

%% \v@claim@maybecolor{key}{rendered} -- clew provenance overlay.
%% When the clew presentation markers layer is ACTIVE (\ifclewpresmarkers,
%% set by --clew-overlay / the master switch) AND this claim has a clew colour
%% registered (clew@hex@<key>, emitted into clew_rendered.tex by render_clew
%% with the SAME sanitised key), the value gets the verdict-coloured
%% decoration of the clew layer (\clewDecorate, the ulem \uwave span). The
%% value is \mbox-wrapped first: it carries a \hypertarget, and \uwave chokes
%% ("Bad space factor (0)") on that box unless it is a single \hbox. In every
%% other case (no clew_rendered.tex, markers off, claim not in the clew feed)
%% it is the PLAIN value, guarded by \@ifundefined so a normal compile never
%% touches an undefined colour or toggle macro.
\providecommand{\v@claim@maybecolor}[2]{%
  \@ifundefined{clew@hex@#1}{#2}{%
    \@ifundefined{ifclewpresmarkers}{#2}{%
      \ifclewpresmarkers
        \begingroup
        \edef\v@claim@clewhex{\csname clew@hex@#1\endcsname}%
        \definecolor{clewVerdict}{HTML}{\v@claim@clewhex}%
        \clewDecorate{\mbox{#2}}%
        \endgroup
      \else #2\fi}}%
}
"""


def claim_lines(claim_id: str, claim: Dict) -> List[str]:
    r"""The alias and the per-style value macros of one claim.

    The first rendering in the document creates a named PDF destination,
    ``\hypertarget{vclaim-<key>}{...}``, which Living Paper uses so PDF.js can
    find the claim text. Later renderings do not emit it again (hyperref warns
    on duplicates): a one-shot flag per claim decides.
    """
    safe_id = _sanitize_id(claim_id)
    context = claim.get("context", "")
    claim_type = claim.get("type", "unknown")
    lines = [
        f"%% {claim_id} ({claim_type}){': ' + context if context else ''}",
        f"\\@namedef{{v@claim@id@{claim_id}}}{{{safe_id}}}",
    ]
    flag = f"v@claim@{safe_id}@anchored"
    for style in FORMAT_STYLES:
        rendered = _render_claim(claim, style)
        wrapped = (
            f"\\expandafter\\ifx\\csname {flag}\\endcsname\\relax"
            f"\\global\\@namedef{{{flag}}}{{}}"
            f"\\hypertarget{{vclaim-{safe_id}}}{{{rendered}}}"
            f"\\else {rendered}\\fi"
        )
        lines.append(f"\\@namedef{{v@claim@{safe_id}@{style}}}{{{wrapped}}}")
    lines.append("")
    return lines


def claims_rendered_tex(claims: Dict[str, Dict], source_note: str) -> str:
    """The whole ``claims_rendered.tex`` for ``claims`` (id -> claim entry)."""
    lines = [
        "%% Auto-generated by scitex-writer — do not edit manually.",
        f"%% Source: {source_note}",
        "%% To update: run writer_claim_render or recompile the project.",
        "",
        PREAMBLE,
        "%% Rendered claims" if claims else "%% No claims defined yet.",
    ]
    for claim_id, claim in claims.items():
        lines.extend(claim_lines(claim_id, claim))
    lines.append("\\makeatother")
    return "\n".join(lines) + "\n"


__all__ = ["PREAMBLE", "claim_lines", "claims_rendered_tex"]

# EOF
