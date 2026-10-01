#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Why the scitex-app workspace shell is unavailable, stated precisely.

An ``except ImportError`` around ``scitex_app.embed`` catches two different
failures and cannot tell them apart:

- scitex-app is ABSENT, or
- scitex-app is PRESENT but predates ``.embed`` (added in 0.4.0).

Reporting the first when the second is true sends the reader to
``pip show scitex-app``, where the package is sitting right there — so the
message reads as a lie and they go debug something else. The remedy is the
same for both, but the diagnosis is not, and a wrong diagnosis costs more
than a missing one.

The decision is a pure function of two facts so it can be tested against real
values; only ``probe_missing_shell`` touches the interpreter.
"""

import importlib.metadata
import importlib.util
from typing import Optional

# First scitex-app release exposing the public ``scitex_app.embed`` module.
MIN_SCITEX_APP = "0.4.0"
MIN_SCITEX_SDK = "0.3.0"

REMEDY = "uv pip install 'scitex-writer[all]'"


def describe_missing_shell(spec_found: bool, installed_version: Optional[str]) -> str:
    """Name which of the two failures actually happened."""
    if not spec_found:
        return "scitex-app is not installed"
    shown = installed_version or "an unknown version"
    return (
        f"scitex-app {shown} is installed but does not expose "
        f"scitex_app.embed, which arrived in {MIN_SCITEX_APP}"
    )


def probe_missing_shell() -> str:
    """Read the two facts off the live interpreter, then describe them."""
    try:
        sdk_found = importlib.util.find_spec("scitex_sdk") is not None
    except (ImportError, ValueError):
        sdk_found = False
    if not sdk_found:
        return "scitex-sdk is not installed"
    try:
        spec_found = importlib.util.find_spec("scitex_app") is not None
    except (ImportError, ValueError):
        # A half-installed package can raise rather than return None.
        spec_found = False

    installed_version = None
    if spec_found:
        try:
            installed_version = importlib.metadata.version("scitex-app")
        except importlib.metadata.PackageNotFoundError:
            installed_version = None

    if not spec_found:
        return describe_missing_shell(spec_found, installed_version)
    return (
        f"scitex-sdk is installed but its workspace shell is unavailable; "
        f"check scitex-sdk>={MIN_SCITEX_SDK} and its app/UI dependencies "
        f"(scitex-app {installed_version or 'version unknown'})"
    )
