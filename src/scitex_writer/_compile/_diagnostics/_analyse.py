#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# File: src/scitex_writer/_compile/_diagnostics/_analyse.py

"""Combine every log a compile leaves into one located, de-duplicated list."""

from __future__ import annotations

import re
from pathlib import Path
from typing import Iterable, Optional

from ._model import (
    CITATION_UNDEFINED,
    ENGINE_NOT_FOUND,
    OVERFULL_ONLY_WARNING,
    SEVERITY_ERROR,
    SEVERITY_WARNING,
    TIMEOUT,
    UNKNOWN,
    LatexDiagnostic,
    fill_hint,
)
from ._rules import (
    BIBLIOGRAPHY_RULES,
    ENGINE_NOT_FOUND_HINT,
    ENGINE_NOT_FOUND_PATTERN,
    FULL_LOG_HINT,
    TIMEOUT_HINT,
    classify,
)
from ._tex_log import (
    clean_path,
    meaningful_tail,
    parse_tex_errors,
    parse_tex_warnings,
    unwrap_tex_log,
)

MAX_WARNINGS_PER_CAUSE = 20
FLATTENED_FILE_BANNER = re.compile(r"^% File: (?P<path>\S+)\s*$")
BANNER_RULE = re.compile(r"^% =+\s*$")
BIBTEX_LOCATION = re.compile(r"^---line (?P<line>\d+) of file (?P<file>\S+)")


def parse_bibliography_log(text: str) -> list[LatexDiagnostic]:
    """Errors and missing entries from a BibTeX ``.blg`` or Biber output."""
    diagnostics: list[LatexDiagnostic] = []
    lines = text.splitlines()
    for index, line in enumerate(lines):
        classified = classify(line, BIBLIOGRAPHY_RULES)
        if not classified:
            continue
        rule, fields = classified
        following = (
            BIBTEX_LOCATION.match(lines[index + 1]) if index + 1 < len(lines) else None
        )
        file = fields.get("file") or (following.group("file") if following else None)
        line_number = fields.get("line") or (
            following.group("line") if following else None
        )
        is_missing_entry = rule.cause == CITATION_UNDEFINED
        diagnostics.append(
            LatexDiagnostic(
                cause=rule.cause,
                severity=SEVERITY_WARNING if is_missing_entry else SEVERITY_ERROR,
                message=line.strip(),
                hint=rule.fill_hint({**fields, "file": file, "line": line_number}),
                context=""
                if is_missing_entry
                else "\n".join(lines[index + 1 : index + 3]).strip(),
                file=file,
                line=int(line_number) if line_number else None,
            )
        )
    return diagnostics


def parse_engine_not_found(console_text: str) -> list[LatexDiagnostic]:
    for line in console_text.splitlines():
        match = ENGINE_NOT_FOUND_PATTERN.search(line)
        if match:
            return [
                LatexDiagnostic(
                    cause=ENGINE_NOT_FOUND,
                    severity=SEVERITY_ERROR,
                    message=line.strip(),
                    hint=fill_hint(ENGINE_NOT_FOUND_HINT, match.groupdict()),
                    context=line.strip(),
                )
            ]
    return []


def map_flattened_location(
    diagnostic: LatexDiagnostic, project_dir: Optional[Path]
) -> LatexDiagnostic:
    """Point a line in the flattened manuscript.tex back at the file the user edits.

    The compile concatenates contents/*.tex behind '% File: <path>' banners.
    The mapping is kept only when the source line's text is identical.
    """
    if project_dir is None or not diagnostic.file or not diagnostic.line:
        return diagnostic
    try:
        flattened = (
            (project_dir / diagnostic.file)
            .read_text(encoding="utf-8", errors="replace")
            .splitlines()
        )
    except OSError:
        return diagnostic
    target = diagnostic.line - 1
    if target >= len(flattened):
        return diagnostic
    for banner_index in range(target, -1, -1):
        banner = FLATTENED_FILE_BANNER.match(flattened[banner_index])
        if not banner:
            continue
        body_start = banner_index + 1
        if body_start < len(flattened) and BANNER_RULE.match(flattened[body_start]):
            body_start += 1
        source_path = clean_path(banner.group("path"))
        source_line = target - body_start + 1
        try:
            source = (
                (project_dir / source_path)
                .read_text(encoding="utf-8", errors="replace")
                .splitlines()
            )
        except OSError:
            return diagnostic
        if (
            1 <= source_line <= len(source)
            and source[source_line - 1] == flattened[target]
        ):
            return LatexDiagnostic(
                **{**diagnostic.to_dict(), "file": source_path, "line": source_line}
            )
        return diagnostic
    return diagnostic


def _dedupe(diagnostics: Iterable[LatexDiagnostic]) -> list[LatexDiagnostic]:
    seen: set[tuple] = set()
    warnings_per_cause: dict[str, int] = {}
    unique: list[LatexDiagnostic] = []
    for diagnostic in diagnostics:
        key = (diagnostic.cause, diagnostic.file, diagnostic.line, diagnostic.message)
        if key in seen:
            continue
        seen.add(key)
        if not diagnostic.is_error:
            count = warnings_per_cause.get(diagnostic.cause, 0) + 1
            warnings_per_cause[diagnostic.cause] = count
            if count > MAX_WARNINGS_PER_CAUSE:
                continue
        unique.append(diagnostic)
    return unique


def analyse_latex_output(
    *,
    compile_failed: bool,
    log_text: str = "",
    console_text: str = "",
    bibliography_log_text: str = "",
    timed_out_after_seconds: Optional[float] = None,
    project_dir: Optional[Path] = None,
) -> list[LatexDiagnostic]:
    """Every error and warning in a compile's logs, errors first.

    A failed compile always yields at least one error diagnostic: when no rule
    matches, an ``unknown`` one carrying the last meaningful log lines.
    """
    tex_text = log_text or console_text
    tex_lines = unwrap_tex_log(tex_text)
    diagnostics: list[LatexDiagnostic] = []
    if timed_out_after_seconds is not None:
        seconds = f"{timed_out_after_seconds:g}"
        diagnostics.append(
            LatexDiagnostic(
                cause=TIMEOUT,
                severity=SEVERITY_ERROR,
                message=f"Compilation timed out after {seconds} seconds",
                hint=fill_hint(TIMEOUT_HINT, {"seconds": f"{seconds} s"}),
                context=meaningful_tail(tex_text),
            )
        )
    diagnostics += parse_engine_not_found(console_text)
    diagnostics += parse_tex_errors(tex_lines)
    diagnostics += parse_bibliography_log(bibliography_log_text)

    has_errors = any(d.is_error for d in diagnostics)
    diagnostics += [
        warning
        for warning in parse_tex_warnings(tex_lines)
        if not (has_errors and warning.cause == OVERFULL_ONLY_WARNING)
    ]
    if compile_failed and not has_errors:
        everything = "\n".join(filter(None, [log_text, console_text]))
        diagnostics.append(
            LatexDiagnostic(
                cause=UNKNOWN,
                severity=SEVERITY_ERROR,
                message="The compile failed without a recognisable LaTeX error",
                hint=FULL_LOG_HINT,
                context=meaningful_tail(everything),
            )
        )
    located = [map_flattened_location(d, project_dir) for d in diagnostics]
    return _dedupe(located)


__all__ = [
    "analyse_latex_output",
    "map_flattened_location",
    "parse_bibliography_log",
    "parse_engine_not_found",
]

# EOF
