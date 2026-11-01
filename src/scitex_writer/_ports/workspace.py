"""Per-project writer workspace setup.

Ensures ``<project_dir>/00_shared/scholar/library →
~/.scitex/scholar/library/`` exists as a symlink (one-hop; see
SCHOLAR_WRITER_INTEGRATION doc).

The target may not exist yet if scitex-scholar has never run on this
machine — that's fine; consumers handle dangling symlinks.
"""

from __future__ import annotations

from pathlib import Path

from scitex_logging import getLogger

logger = getLogger(__name__)


def ensure_scholar_library_link(project_dir: Path) -> Path | None:
    """Create or refresh the 00_shared/scholar/library symlink.

    Idempotent. Does nothing if the link already points at the home
    library. Returns the link path on success, None if it couldn't be
    created (e.g. read-only filesystem).
    """
    project_dir = Path(project_dir)
    target = Path("~/.scitex/scholar/library").expanduser()

    link_parent = project_dir / "00_shared" / "scholar"
    try:
        link_parent.mkdir(parents=True, exist_ok=True)
    except OSError as exc:
        logger.warning("Could not create %s: %s", link_parent, exc)
        return None

    link = link_parent / "library"
    try:
        if link.is_symlink():
            if link.readlink() == target:
                return link
            link.unlink()
        elif link.exists():
            logger.warning(
                "Refusing to replace existing non-symlink at %s (delete manually to re-link)",
                link,
            )
            return None
        link.symlink_to(target)
        logger.info("Linked %s → %s", link, target)
        return link
    except OSError as exc:
        logger.warning("Could not create %s: %s", link, exc)
        return None
