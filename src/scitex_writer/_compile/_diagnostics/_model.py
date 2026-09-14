#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# File: src/scitex_writer/_compile/_diagnostics/_model.py

"""The closed set of compile-problem causes and the diagnostic record."""

from __future__ import annotations

import re
from dataclasses import asdict, dataclass
from typing import Optional

UNDEFINED_CONTROL_SEQUENCE = "undefined-control-sequence"
MISSING_PACKAGE = "missing-package"
UNICODE_CHAR_NOT_SET_UP = "unicode-char-not-set-up"
MISSING_FILE = "missing-file"
BIBTEX_ERROR = "bibtex-error"
BIBER_ERROR = "biber-error"
CITATION_UNDEFINED = "citation-undefined"
REFERENCE_UNDEFINED = "reference-undefined"
RUNAWAY_ARGUMENT = "runaway-argument"
EMERGENCY_STOP = "emergency-stop"
OVERFULL_ONLY_WARNING = "overfull-only-warning"
TIMEOUT = "timeout"
ENGINE_NOT_FOUND = "engine-not-found"
UNKNOWN = "unknown"

CAUSE_CLASSES = (
    UNDEFINED_CONTROL_SEQUENCE,
    MISSING_PACKAGE,
    UNICODE_CHAR_NOT_SET_UP,
    MISSING_FILE,
    BIBTEX_ERROR,
    BIBER_ERROR,
    CITATION_UNDEFINED,
    REFERENCE_UNDEFINED,
    RUNAWAY_ARGUMENT,
    EMERGENCY_STOP,
    OVERFULL_ONLY_WARNING,
    TIMEOUT,
    ENGINE_NOT_FOUND,
    UNKNOWN,
)

SEVERITY_ERROR = "error"
SEVERITY_WARNING = "warning"


@dataclass(frozen=True)
class LatexDiagnostic:
    """One problem found in a compile, located and explained."""

    cause: str
    severity: str
    message: str
    hint: str
    context: str = ""
    file: Optional[str] = None
    line: Optional[int] = None

    @property
    def location(self) -> str:
        if self.file and self.line:
            return f"{self.file}:{self.line}"
        return self.file or ""

    @property
    def is_error(self) -> bool:
        return self.severity == SEVERITY_ERROR

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass(frozen=True)
class Rule:
    """A message pattern and the hint template its named groups fill in."""

    cause: str
    pattern: re.Pattern
    hint: str

    def fill_hint(self, fields: dict) -> str:
        return fill_hint(self.hint, fields)


def fill_hint(template: str, fields: dict) -> str:
    values = {key: value for key, value in fields.items() if value is not None}
    values.setdefault("command", "This command")
    try:
        return template.format(**values)
    except (KeyError, IndexError):
        return template


__all__ = [
    "CAUSE_CLASSES",
    "LatexDiagnostic",
    "Rule",
    "SEVERITY_ERROR",
    "SEVERITY_WARNING",
    "fill_hint",
]

# EOF
