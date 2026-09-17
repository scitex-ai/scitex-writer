#!/usr/bin/env python3
"""Establish the engine's own version truthfully, or refuse to state one.

A package's version lives in metadata *adjacent* to its code, not in the code.
When an environment holds more than one scitex-writer distribution,
``importlib.metadata.version()`` resolves one of them by scan order and returns
it with no indication that the question was ambiguous -- a confident answer to
an unanswerable question.

That matters here more than it would elsewhere: the compile stamps this version
into the manuscript's PDF provenance metadata. A guessed version becomes a
durable falsehood in a published scientific artifact -- one that survives in the
file long after the environment is repaired, and which no later reader can
detect from the PDF alone.

So when the version cannot be established, we refuse to stamp rather than stamp
a guess. The decision logic is pure: callers pass in the facts, so it can be
tested against real inputs instead of a patched interpreter.
"""

from __future__ import annotations

from typing import Optional

REMEDY = (
    "Remove the stale distribution so the version is unambiguous:\n"
    "    pip uninstall -y scitex-writer && pip install 'scitex-writer[all]'"
)


def describe_ambiguous_metadata(versions: list[str]) -> str:
    """Explain why no version can be stated, naming every candidate."""
    shown = ", ".join(sorted(versions))
    return (
        f"scitex-writer cannot determine its own version: {len(versions)} "
        f"installed distributions claim the name scitex-writer ({shown}). "
        f"importlib.metadata resolves one of them by directory scan order, so "
        f"any version reported now is a coin-flip.\n\n"
        f"Refusing to stamp a guessed engine version into the PDF's provenance "
        f"metadata: the manuscript would assert it was built by a version that "
        f"did not build it, and would keep asserting it after this environment "
        f"is fixed.\n\n" + REMEDY
    )


def resolve_stamp_version(installed: list[str], declared: str) -> str:
    """Return the version safe to stamp, or raise naming the ambiguity.

    ``installed`` are the versions of every installed distribution claiming the
    scitex-writer name; ``declared`` is what the package reports as its own
    version. This function's job is to *veto* ``declared`` when the metadata it
    came from was ambiguous -- not to re-derive it. An empty ``installed`` is
    not ambiguous: running from a source tree with nothing installed is a
    legitimate state, and ``declared`` falls back to pyproject.toml there.
    """
    distinct = sorted(set(installed))
    if len(distinct) > 1:
        raise RuntimeError(describe_ambiguous_metadata(distinct))
    return declared


def version_stamp_tex(version: str) -> str:
    """Render the LaTeX provenance stamp for a version known to be truthful."""
    return (
        f"\\def\\ScitexWriterVersion{{{version}}}\n"
        f"\\hypersetup{{pdfcreator={{Compiled by SciTeX Writer v{version}}}}}\n"
    )


def installed_versions(name: str = "scitex-writer") -> list[str]:
    """Every version claimed by an installed distribution with this name."""
    import importlib.metadata as md

    want = name.lower().replace("_", "-")
    return [
        d.version
        for d in md.distributions()
        if (d.metadata["Name"] or "").lower().replace("_", "-") == want
    ]


def _source_tree_version(package_file: str, name: str = "scitex-writer") -> Optional[str]:
    """The version declared by the source tree the RUNNING CODE sits in.

    THE CASE THIS EXISTS FOR, measured 2026-09-17 on this container's dev
    checkout: ``importlib.metadata.version("scitex-writer")`` said **2.42.0**
    while the code being executed was 2.43.5's. An editable install's metadata
    is written once and never updated by later commits, so the compile stamped a
    PDF with a version that DID NOT COMPILE IT — the durable falsehood this
    module's docstring is about, arriving from the direction the ambiguity veto
    cannot see (one distribution, wrong version, so nothing looks ambiguous).

    A checkout's own ``pyproject.toml`` cannot lag its code: it IS the code's
    declaration. So when it sits where the running package expects it — two
    levels above the package directory, ``<repo>/src/scitex_writer/`` — and names
    this project, it wins.

    IN A WHEEL INSTALL NOTHING CHANGES: ``site-packages`` has no ``pyproject.toml``
    two levels up (and if some unrelated project's did sit there, the name check
    refuses it), so this returns ``None`` and metadata supplies the version.
    """
    from pathlib import Path

    candidate = Path(package_file).resolve().parents[2] / "pyproject.toml"
    if not candidate.is_file():
        return None
    try:
        for line in candidate.read_text(encoding="utf-8").splitlines():
            if line.startswith("name") and "=" in line:
                declared_name = line.split("=", 1)[1].strip().strip('"').strip("'")
                if declared_name.lower().replace("_", "-") != name.lower().replace("_", "-"):
                    return None  # someone else's pyproject.toml, not ours
            if line.startswith("version") and "=" in line:
                return line.split("=", 1)[1].strip().strip('"').strip("'")
    except OSError:
        return None
    return None


def stamp_version(name: str = "scitex-writer") -> str:
    """THE version to stamp: one resolver for every writer of the stamp.

    Two writers put a version into a compiled manuscript's provenance metadata —
    the compile path (``_mcp/handlers/_compile.py``) and the re-vendor path
    (``_mcp/handlers/_update/_handler.py``) — and before this they resolved it two
    different ways (``importlib.metadata`` vs a hand-rolled pyproject read), which
    is how one PDF came to carry claims that disagreed with each other and with
    the code that produced it.

    Order, and why: the SOURCE TREE the running code lives in (it describes what
    is executing, and cannot lag it), then the installed distribution's version.
    Ambiguity — more than one distribution claiming the name — still raises
    rather than picking one by scan order, because a guessed version in a
    published artifact outlives the environment that guessed it.
    """
    import scitex_writer

    installed = installed_versions(name)
    distinct = sorted(set(installed))
    if len(distinct) > 1:
        raise RuntimeError(describe_ambiguous_metadata(distinct))
    return _source_tree_version(scitex_writer.__file__, name) or scitex_writer.__version__
