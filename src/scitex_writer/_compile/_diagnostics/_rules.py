#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# File: src/scitex_writer/_compile/_diagnostics/_rules.py

"""The rule tables: which message means which cause, and what to do next.

Order matters inside a table: the first matching rule wins, so the more
specific pattern (a missing ``.sty``) sits above the general one (any file).
"""

from __future__ import annotations

import re

from ._model import (
    BIBER_ERROR,
    BIBTEX_ERROR,
    CITATION_UNDEFINED,
    EMERGENCY_STOP,
    MISSING_FILE,
    MISSING_PACKAGE,
    OVERFULL_ONLY_WARNING,
    REFERENCE_UNDEFINED,
    RUNAWAY_ARGUMENT,
    UNDEFINED_CONTROL_SEQUENCE,
    UNICODE_CHAR_NOT_SET_UP,
    Rule,
)

FULL_LOG_HINT = (
    'No known cause matched: open the full log ("Show full log") and read the '
    "lines just above the first error"
)

MISSING_CITATION_HINT = (
    "Citation key '{key}' is not in the bibliography: add the entry to the "
    ".bib file or fix the key"
)

ERROR_RULES: tuple[Rule, ...] = (
    Rule(
        UNICODE_CHAR_NOT_SET_UP,
        re.compile(
            r"Unicode character (?P<char>.+?) \((?P<codepoint>U\+[0-9A-Fa-f]+)\)"
        ),
        "{codepoint} {char} isn't supported by pdfLaTeX: remove it or compile "
        "with XeLaTeX",
    ),
    Rule(
        MISSING_PACKAGE,
        re.compile(r"File [`'](?P<name>[^`']+)\.(?P<ext>sty|cls)' not found"),
        "The package '{name}.{ext}' is not installed: remove "
        "\\usepackage{{{name}}} or install it (tlmgr install {name})",
    ),
    Rule(
        MISSING_FILE,
        re.compile(r"File [`'](?P<name>[^`']+)' not found"),
        "'{name}' was not found: check the path and file name (relative to the "
        "project root) or add the missing file",
    ),
    Rule(
        UNDEFINED_CONTROL_SEQUENCE,
        re.compile(r"Undefined control sequence"),
        "{command} is not defined: fix its spelling or load the package that "
        "provides it",
    ),
    Rule(
        RUNAWAY_ARGUMENT,
        re.compile(
            r"(?:File ended while scanning use of|Paragraph ended before)"
            r" (?P<command>\\[^\s.]+)"
        ),
        "An argument of {command} is never closed: add the missing '}}'",
    ),
    Rule(
        EMERGENCY_STOP,
        re.compile(r"Emergency stop"),
        "LaTeX stopped before the end of the document: check that "
        "\\end{{document}} is present and every brace and environment is closed",
    ),
)

WARNING_RULES: tuple[Rule, ...] = (
    Rule(
        CITATION_UNDEFINED,
        re.compile(
            r"Citation [`'](?P<key>[^']+)' on page \S+ undefined"
            r"(?: on input line (?P<line>\d+))?"
        ),
        MISSING_CITATION_HINT,
    ),
    Rule(
        REFERENCE_UNDEFINED,
        re.compile(
            r"Reference [`'](?P<key>[^']+)' on page \S+ undefined"
            r"(?: on input line (?P<line>\d+))?"
        ),
        "Label '{key}' is not defined: add \\label{{{key}}} or fix the \\ref",
    ),
    Rule(
        OVERFULL_ONLY_WARNING,
        re.compile(
            r"^Overfull \\[hv]box \((?P<amount>[\d.]+pt) too (?:wide|high)\)"
            r".*?lines? (?P<line>\d+)"
        ),
        "Content sticks out of the margin by {amount} (the PDF is still "
        "produced): rephrase, allow a line break, or shrink the figure/table",
    ),
)

BIBLIOGRAPHY_RULES: tuple[Rule, ...] = (
    Rule(
        BIBTEX_ERROR,
        re.compile(r"I couldn't open database file (?P<name>\S+)"),
        "The bibliography database '{name}' was not found: check "
        "\\bibliography{{...}} and that the .bib file exists",
    ),
    Rule(
        BIBTEX_ERROR,
        re.compile(r"I couldn't open style file (?P<name>\S+)"),
        "The bibliography style '{name}' was not found: check "
        "\\bibliographystyle{{...}}",
    ),
    Rule(
        BIBTEX_ERROR,
        re.compile(r"^(?P<text>.+?)---line (?P<line>\d+) of file (?P<file>\S+)"),
        "BibTeX could not parse {file} near line {line}: fix the entry syntax "
        "(a missing comma, brace or quote)",
    ),
    Rule(
        BIBER_ERROR,
        re.compile(r"\bERROR - (?P<text>.+)"),
        "Biber reported '{text}': fix the named .bib entry or biblatex option",
    ),
    Rule(
        CITATION_UNDEFINED,
        re.compile(r"Warning--I didn't find a database entry for \"(?P<key>[^\"]+)\""),
        MISSING_CITATION_HINT,
    ),
)

ENGINE_NOT_FOUND_PATTERN = re.compile(
    r"\b(?P<engine>pdflatex|xelatex|lualatex|latexmk|tectonic|bibtex|biber)"
    r":?(?: command)? not (?:found|available)"
)
ENGINE_NOT_FOUND_HINT = (
    "The LaTeX tool '{engine}' is not installed on the compile server: install "
    "it (TeX Live) or choose another engine"
)

TIMEOUT_HINT = (
    "The compile was stopped after {seconds}: look for a macro that loops "
    "forever, or compile in preview (draft) mode"
)

MISSING_COMPILE_SCRIPT_HINT = (
    "The project workspace has no compile.sh: re-create the workspace or run "
    "`scitex-writer update-project` on it"
)


def classify(text: str, rules: tuple[Rule, ...]) -> tuple[Rule, dict] | None:
    """Return the first rule whose pattern matches ``text``, with its groups."""
    for rule in rules:
        match = rule.pattern.search(text)
        if match:
            return rule, match.groupdict()
    return None


__all__ = [
    "BIBLIOGRAPHY_RULES",
    "ENGINE_NOT_FOUND_HINT",
    "ENGINE_NOT_FOUND_PATTERN",
    "ERROR_RULES",
    "FULL_LOG_HINT",
    "MISSING_COMPILE_SCRIPT_HINT",
    "TIMEOUT_HINT",
    "WARNING_RULES",
    "classify",
]

# EOF
