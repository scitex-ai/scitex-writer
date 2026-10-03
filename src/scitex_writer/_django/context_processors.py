"""Writer template context observes the page's authorized project selection."""

from __future__ import annotations

from typing import Any


def project_context(request: Any) -> dict:
    """Render genuine SDK project context without persisting navigation again."""
    from scitex_sdk.app.project_context import project_context as sdk_project_context

    return sdk_project_context(request, remember=False)
