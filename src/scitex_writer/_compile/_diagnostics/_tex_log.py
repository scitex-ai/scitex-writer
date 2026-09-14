#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# File: src/scitex_writer/_compile/_diagnostics/_tex_log.py

"""Read errors and warnings out of a pdfTeX/XeTeX/LuaTeX ``.log``.

Handles both error styles the engines write: ``! Message`` (classic) and
``./file.tex:12: Message`` (``-file-line-error``, which writer's engines use).
"""

from __future__ import annotations

import re
from typing import Optional

from ._model import (
    EMERGENCY_STOP,
    OVERFULL_ONLY_WARNING,
    SEVERITY_ERROR,
    SEVERITY_WARNING,
    UNKNOWN,
    LatexDiagnostic,
)
from ._rules import ERROR_RULES, FULL_LOG_HINT, WARNING_RULES, classify

UNKNOWN_CONTEXT_LINES = 30
# pdfTeX hard-wraps its log at max_print_line, counted in bytes.
TEX_LOG_WRAP_WIDTH = 79
INPUT_LINE_LOOKAHEAD = 12

FILE_LINE_ERROR = re.compile(
    r"^(?P<file>[^\s:()!][^:()]*?\.\w+):(?P<line>\d+): (?P<message>.+)$"
)
BANG_ERROR = re.compile(r"^! (?P<message>.+)$")
INPUT_LINE = re.compile(r"^l\.(?P<line>\d+) ?(?P<before>.*)$")
CONTROL_SEQUENCE = re.compile(r"\\[A-Za-z@]+\*?|\\.")
FILE_OPEN = re.compile(
    r"\((?P<path>\.{0,2}/[^\s()]+|[\w.-]+\.(?:tex|sty|cls|clo|def|cfg|aux|bbl|fd))"
)
TEX_CARET_BYTES = re.compile(r"(?:\^\^[0-9a-f]{2})+")
SECONDARY_ERROR = re.compile(r"==> Fatal error occurred|job aborted")

NOISE_LINE = re.compile(
    r"^\s*$"
    r"|^\s*\*+\s*$"
    r"|^\\[\w@]+=\\\w+"
    r"|^(?:File|Package|Document Class|LaTeX Font Info|Language|For additional)\b"
    r"|^ \d+[\w,]* .*out of"
    r"|^Here is how much of TeX's memory"
    r"|^PDF statistics:"
    r"|^</usr/|^r/share/"
)


def unwrap_tex_log(text: str) -> list[str]:
    """Rejoin lines pdfTeX hard-wrapped at the print width."""
    joined: list[str] = []
    pending = ""
    for raw in text.splitlines():
        pending += raw
        # Error excerpts ("l.12 ..." and its indented remainder) are padded, not wrapped.
        is_excerpt = raw.startswith((" ", "l."))
        if len(raw.encode("utf-8", "replace")) == TEX_LOG_WRAP_WIDTH and not is_excerpt:
            continue
        joined.append(pending)
        pending = ""
    if pending:
        joined.append(pending)
    return joined


def decode_caret_bytes(text: str) -> str:
    """Turn pdfTeX's ``^^e3^^80^^8d`` escapes back into the character."""

    def decode(match: re.Match) -> str:
        pairs = [pair for pair in match.group(0).split("^^") if pair]
        return bytes(int(pair, 16) for pair in pairs).decode("utf-8", "replace")

    return TEX_CARET_BYTES.sub(decode, text)


def meaningful_tail(text: str, count: int = UNKNOWN_CONTEXT_LINES) -> str:
    """The last ``count`` log lines that are not engine bookkeeping."""
    lines = [line.rstrip() for line in text.splitlines() if not NOISE_LINE.search(line)]
    return "\n".join(lines[-count:])


def clean_path(path: Optional[str]) -> Optional[str]:
    if not path:
        return None
    return path[2:] if path.startswith("./") else path


class FileStack:
    """Which input file TeX is reading, from the '(' / ')' marks it logs."""

    def __init__(self) -> None:
        self._entries: list[Optional[str]] = []

    def feed(self, line: str) -> None:
        position = 0
        while position < len(line):
            if line[position] == "(":
                opened = FILE_OPEN.match(line, position)
                self._entries.append(opened.group("path") if opened else None)
                position = opened.end() if opened else position + 1
                continue
            if line[position] == ")" and self._entries:
                self._entries.pop()
            position += 1

    @property
    def current_tex_file(self) -> Optional[str]:
        for entry in reversed(self._entries):
            if entry and entry.endswith(".tex"):
                return clean_path(entry)
        return None


def _is_error_line(line: str) -> bool:
    return bool(FILE_LINE_ERROR.match(line) or BANG_ERROR.match(line))


def _read_error_context(
    lines: list[str], start: int
) -> tuple[str, Optional[int], Optional[str], int]:
    """Find the ``l.<n>`` excerpt after an error: (context, line, command, next index).

    When the error happened inside a macro, TeX first prints the expansion
    (``\\macro ->\\undefined``); that line names the real culprit.
    """
    expansion = ""
    for index in range(start, min(start + INPUT_LINE_LOOKAHEAD, len(lines))):
        if _is_error_line(lines[index]):
            break
        if not expansion and "->" in lines[index]:
            expansion = lines[index].strip()
        input_line = INPUT_LINE.match(lines[index])
        if input_line:
            before = input_line.group("before")
            after = lines[index + 1].strip() if index + 1 < len(lines) else ""
            commands = CONTROL_SEQUENCE.findall(expansion or before)
            excerpt = f"{before} {after}".strip()
            context = "\n".join(part for part in (expansion, excerpt) if part)
            return (
                context,
                int(input_line.group("line")),
                commands[-1] if commands else None,
                index + 2,
            )
        if lines[index].startswith("*** ("):
            return lines[index].strip(), None, None, index + 1
    return "", None, None, start


def parse_tex_errors(lines: list[str]) -> list[LatexDiagnostic]:
    """Every error in the log, classified; a fatal stop alone stays visible."""
    diagnostics: list[LatexDiagnostic] = []
    files = FileStack()
    index = 0
    while index < len(lines):
        line = lines[index]
        located = FILE_LINE_ERROR.match(line)
        bare = None if located else BANG_ERROR.match(line)
        if not (located or bare):
            files.feed(line)
            index += 1
            continue

        message = (located or bare).group("message").strip()
        cursor = index + 1
        while (
            cursor < len(lines)
            and lines[cursor].startswith(" ")
            and lines[cursor].strip()
        ):
            message = f"{message} {lines[cursor].strip()}"
            cursor += 1
        context, input_line, command, cursor = _read_error_context(lines, cursor)
        if not context and index >= 2 and lines[index - 2] == "Runaway argument?":
            context = lines[index - 1].strip()

        classified = classify(message, ERROR_RULES)
        if not classified and SECONDARY_ERROR.search(message):
            index = cursor
            continue
        if classified:
            rule, fields = classified
            fields = {"command": command, **{k: v for k, v in fields.items() if v}}
            cause, hint = rule.cause, rule.fill_hint(_decoded(fields))
        else:
            cause, hint = UNKNOWN, FULL_LOG_HINT
            context = context or meaningful_tail("\n".join(lines[:index]))
        diagnostics.append(
            LatexDiagnostic(
                cause=cause,
                severity=SEVERITY_ERROR,
                message=decode_caret_bytes(message),
                hint=hint,
                context=decode_caret_bytes(context),
                file=clean_path(located.group("file"))
                if located
                else files.current_tex_file,
                line=int(located.group("line")) if located else input_line,
            )
        )
        index = max(cursor, index + 1)

    primary = [d for d in diagnostics if d.cause != EMERGENCY_STOP]
    return primary or diagnostics


def parse_tex_warnings(lines: list[str]) -> list[LatexDiagnostic]:
    """Undefined citations/references and overfull boxes, with their file."""
    diagnostics: list[LatexDiagnostic] = []
    files = FileStack()
    for index, line in enumerate(lines):
        maybe_warning = "Warning" in line or line.startswith("Overfull")
        classified = classify(line, WARNING_RULES) if maybe_warning else None
        if not classified:
            files.feed(line)
            continue
        rule, fields = classified
        is_overfull = rule.cause == OVERFULL_ONLY_WARNING
        diagnostics.append(
            LatexDiagnostic(
                cause=rule.cause,
                severity=SEVERITY_WARNING,
                message=line.strip(),
                hint=rule.fill_hint(fields),
                context=lines[index + 1].strip()
                if is_overfull and index + 1 < len(lines)
                else "",
                file=files.current_tex_file,
                line=int(fields["line"]) if fields.get("line") else None,
            )
        )
    return diagnostics


def _decoded(fields: dict) -> dict:
    return {
        key: decode_caret_bytes(value) if isinstance(value, str) else value
        for key, value in fields.items()
    }


__all__ = [
    "FileStack",
    "clean_path",
    "decode_caret_bytes",
    "meaningful_tail",
    "parse_tex_errors",
    "parse_tex_warnings",
    "unwrap_tex_log",
]

# EOF
