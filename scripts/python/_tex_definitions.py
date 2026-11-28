#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# ROLE: engine-vendored — DO NOT edit here. `scitex-writer update-project`
# overwrites this file on every re-vendor; fix it upstream in the
# scitex-writer package instead (local edits are lost, and update-project
# may set it read-only in the consumer workspace after vendoring).
# File: scripts/python/_tex_definitions.py
# Purpose: Remove the replacement text of LaTeX macro/environment definitions.
#
#          A DEFINITION is not a USE: \includegraphics inside the body of
#          \newcommand / \def / \newenvironment embeds nothing until the macro
#          is invoked, and a style may define one it never calls (or calls only
#          when an optional file exists). A static count over the compiled .tex
#          must therefore ignore those bodies, or a figure-free document whose
#          preamble defines such a macro "references" a figure that can never be
#          embedded. Self-contained: stdlib only.

import re

_DEF_COMMAND_RE = re.compile(
    r"\\(?:(?:re)?newcommand|providecommand|DeclareRobustCommand)\*?"
    r"|\\(?:re)?newenvironment\*?"
    r"|\\(?:(?:long|protected|global|outer)\s*\\)*[gex]?def(?![A-Za-z])"
)


def _skip_ws(text, i):
    while i < len(text) and text[i].isspace():
        i += 1
    return i


def _skip_group(text, i, open_ch, close_ch):
    """Index just past the balanced group that opens at text[i]."""
    depth = 0
    while i < len(text):
        ch = text[i]
        if ch == "\\":
            i += 2
            continue
        if ch == open_ch:
            depth += 1
        elif ch == close_ch:
            depth -= 1
            if depth == 0:
                return i + 1
        i += 1
    return len(text)


def _skip_name(text, i):
    """Index just past a definition's name ({\\name}, {env}, \\name, \\@),
    or None when no name follows."""
    if i < len(text) and text[i] == "{":
        return _skip_group(text, i, "{", "}")
    if i < len(text) and text[i] == "\\":
        j = i + 1
        while j < len(text) and (text[j].isalpha() or text[j] == "@"):
            j += 1
        return j if j > i + 1 else min(j + 1, len(text))
    return None


def strip_macro_definitions(text):
    """``text`` with the body of every macro/environment definition removed.

    Comments must already be stripped (an unbalanced brace in a comment would
    otherwise swallow the rest of the document)."""
    out = []
    pos = 0
    for m in _DEF_COMMAND_RE.finditer(text):
        if m.start() < pos:
            continue  # nested inside a definition already removed
        token = m.group(0)
        i = _skip_name(text, _skip_ws(text, m.end()))
        if i is None:
            continue
        if token.endswith("def"):
            # Parameter text (#1, delimiters) runs up to the body's brace.
            while i < len(text) and text[i] != "{":
                i += 1
        else:
            i = _skip_ws(text, i)
            while i < len(text) and text[i] == "[":
                i = _skip_ws(text, _skip_group(text, i, "[", "]"))
        for _ in range(2 if "environment" in token else 1):
            i = _skip_ws(text, i)
            if i >= len(text) or text[i] != "{":
                break
            i = _skip_group(text, i, "{", "}")
        out.append(text[pos : m.start()])
        pos = i
    out.append(text[pos:])
    return "".join(out)


# EOF
