"""Report an unavailable workspace shell through its single SDK owner."""

import importlib.metadata
import importlib.util
from typing import Optional

MIN_SCITEX_SDK = "0.3.0"
REMEDY = "uv pip install 'scitex-writer[all]'"


def describe_missing_shell(spec_found: bool, installed_version: Optional[str]) -> str:
    """Distinguish an absent SDK from an installed SDK with an unavailable shell."""
    if not spec_found:
        return "scitex-sdk is not installed"
    shown = installed_version or "an unknown version"
    return (
        f"scitex-sdk {shown} is installed but its workspace shell "
        f"scitex_sdk.app.embed is unavailable; check scitex-sdk>={MIN_SCITEX_SDK}"
    )


def probe_missing_shell() -> str:
    """Read only SDK presence/version; no legacy distribution is required."""
    try:
        spec_found = importlib.util.find_spec("scitex_sdk") is not None
    except (ImportError, ValueError):
        spec_found = False
    installed_version = None
    if spec_found:
        try:
            installed_version = importlib.metadata.version("scitex-sdk")
        except importlib.metadata.PackageNotFoundError:
            pass
    return describe_missing_shell(spec_found, installed_version)
