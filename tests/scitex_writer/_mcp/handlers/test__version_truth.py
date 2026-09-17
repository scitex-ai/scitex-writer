#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""The compile must never stamp a version it cannot establish.

THE BUG. `_inject_version_stamp` wrote `scitex_writer.__version__` into the
manuscript's PDF provenance metadata (\\ScitexWriterVersion + pdfcreator), and
`__version__` comes from `importlib.metadata.version()`. When an environment
holds more than one scitex-writer distribution, that call resolves one by
directory scan order and returns it with no sign the question was ambiguous.
The whole thing was wrapped in `except Exception: pass`, so a stamp that never
got written looked exactly like a clean compile.

Real incident (2026-07-17): this container carried both a 2.26.1 and a 2.37.0
dist-info. `version()` answered 2.26.1 while 2.37.0 code was actually running --
verified by probing for a 2.33.0+ symbol. Every PDF compiled here would have
asserted it was built by v2.26.1. Unlike a bad log line, that falsehood is
durable: it survives in the published file after the environment is repaired,
and no later reader can detect it from the PDF alone.

Two silent failures stacked: one wrote the wrong version, the other hid writing
nothing.

The decision functions are pure -- they take the facts as arguments -- so these
run against real values with no mock and no monkeypatch (PA-306 / STX-NM002).
"""

import functools
from pathlib import Path

import pytest

from scitex_writer._mcp.handlers._version_truth import (
    _source_tree_version,
    describe_ambiguous_metadata,
    resolve_stamp_version,
    stamp_version,
    version_stamp_tex,
)

# The exact state measured in the container that surfaced this bug.
AMBIGUOUS = ["2.26.1", "2.37.0"]


def _refusal_message(installed, declared) -> str:
    """Return the refusal message, or "" when the call is allowed through."""
    try:
        resolve_stamp_version(installed, declared)
    except RuntimeError as exc:
        return str(exc)
    return ""


class TestAmbiguousMetadataIsRefused:
    def test_two_distinct_versions_are_refused(self):
        # Arrange
        installed = AMBIGUOUS

        # Act
        message = _refusal_message(installed, "2.26.1")

        # Assert
        assert message != ""

    def test_refusal_raises_rather_than_returning_a_guess(self):
        # Arrange
        installed = AMBIGUOUS

        # Act
        act = functools.partial(resolve_stamp_version, installed, "2.26.1")

        # Assert
        with pytest.raises(RuntimeError):
            act()


class TestRefusalMessage:
    def test_message_names_the_stale_candidate(self):
        # Arrange
        installed = AMBIGUOUS

        # Act
        message = _refusal_message(installed, "2.26.1")

        # Assert
        assert "2.26.1" in message

    def test_message_names_the_current_candidate(self):
        # Arrange
        installed = AMBIGUOUS

        # Act
        message = _refusal_message(installed, "2.26.1")

        # Assert
        assert "2.37.0" in message

    def test_message_hands_back_a_working_repair_command(self):
        # Arrange
        installed = AMBIGUOUS

        # Act
        message = _refusal_message(installed, "2.26.1")

        # Assert
        assert "pip uninstall -y scitex-writer" in message

    def test_message_explains_the_provenance_stake(self):
        # Arrange: the message must say WHY, or a reader will force past it.
        versions = AMBIGUOUS

        # Act
        message = describe_ambiguous_metadata(versions)

        # Assert
        assert "provenance" in message


class TestUnambiguousMetadataIsStamped:
    def test_single_installed_version_is_returned(self):
        # Arrange
        installed = ["2.37.0"]

        # Act
        version = resolve_stamp_version(installed, "2.37.0")

        # Assert
        assert version == "2.37.0"

    def test_same_version_declared_twice_is_not_ambiguous(self):
        # Arrange: duplicate dist-info that AGREE answer the question, so they
        # must not block a compile.
        installed = ["2.37.0", "2.37.0"]

        # Act
        version = resolve_stamp_version(installed, "2.37.0")

        # Assert
        assert version == "2.37.0"

    def test_nothing_installed_defers_to_the_declared_version(self):
        # Arrange: a source tree with nothing installed is legitimate;
        # __version__ falls back to pyproject.toml there.
        installed = []

        # Act
        version = resolve_stamp_version(installed, "0.0.0+local")

        # Assert
        assert version == "0.0.0+local"


class TestStampRendersTheVersion:
    def test_stamp_defines_the_latex_version_macro(self):
        # Arrange
        version = "2.37.0"

        # Act
        tex = version_stamp_tex(version)

        # Assert
        assert "\\def\\ScitexWriterVersion{2.37.0}" in tex

    def test_stamp_sets_the_pdf_creator_metadata(self):
        # Arrange
        version = "2.37.0"

        # Act
        tex = version_stamp_tex(version)

        # Assert
        assert "pdfcreator={Compiled by SciTeX Writer v2.37.0}" in tex


class TestTheRunningSourceTreeBeatsStaleMetadata:
    """One PDF, three claims (card writer-pdf-carries-three-disagreeing-version-claims).

    Measured on the dev checkout 2026-09-17: ``importlib.metadata.version`` said
    2.42.0 while the code being executed was 2.43.5's, so a compile stamped a PDF
    with a version that did not compile it — a single distribution, a wrong
    version, and therefore nothing for the ambiguity veto to notice.
    """

    def _checkout(self, tmp_path, declared_name: str = "scitex-writer") -> str:
        (tmp_path / "src" / "scitex_writer").mkdir(parents=True, exist_ok=True)
        (tmp_path / "pyproject.toml").write_text(
            f'name = "{declared_name}"\nversion = "9.9.9"\n', encoding="utf-8"
        )
        package_file = tmp_path / "src" / "scitex_writer" / "__init__.py"
        package_file.write_text("", encoding="utf-8")
        return str(package_file)

    def test_a_checkout_declares_the_version_of_its_own_code(self, tmp_path):
        # Arrange
        package_file = self._checkout(tmp_path)
        # Act
        found = _source_tree_version(package_file)
        # Assert
        assert found == "9.9.9"

    def test_a_tree_belonging_to_another_project_is_not_borrowed(self, tmp_path):
        # Arrange: an unrelated project whose pyproject sits above the running
        # package — reading IT would be a different falsehood, not a fix.
        package_file = self._checkout(tmp_path, declared_name="some-other-tool")
        # Act
        found = _source_tree_version(package_file)
        # Assert
        assert found is None

    def test_no_pyproject_above_the_package_means_no_source_version(self, tmp_path):
        # Arrange: the WHEEL shape — site-packages has no pyproject.toml — where
        # metadata is exact and must stay the answer.
        (tmp_path / "site-packages" / "scitex_writer").mkdir(parents=True)
        package_file = tmp_path / "site-packages" / "scitex_writer" / "__init__.py"
        package_file.write_text("", encoding="utf-8")
        # Act
        found = _source_tree_version(str(package_file))
        # Assert
        assert found is None

    def test_the_live_stamp_matches_the_running_source_tree(self):
        # Arrange: in THIS checkout the stamp must not be the stale metadata
        # value — the exact claim this card is about.
        import scitex_writer

        # Act
        stamped = stamp_version()
        # Assert
        assert stamped == _source_tree_version(scitex_writer.__file__)


class TestBothWritersRenderOneStamp:
    """The RELATIONSHIP: two writers of the PDF macros, one template.

    The compile path and the re-vendor path answer different questions ("what is
    running" vs "what was vendored"), so the VALUES may differ — the FORMAT must
    not, or the two claims drift apart inside one PDF.
    """

    def test_the_revendor_writer_renders_the_shared_template(self, tmp_path):
        # Arrange
        from scitex_writer._mcp.handlers._update._handler import _restamp_version_tex

        (tmp_path / "00_shared").mkdir()
        # Act
        _restamp_version_tex(tmp_path, "1.2.3")
        # Assert
        assert (
            tmp_path / "00_shared" / "scitex_writer_version.tex"
        ).read_text() == version_stamp_tex("1.2.3")

    def test_the_macros_are_written_in_exactly_one_place(self):
        # Arrange: a literal in a second module is a second template, and the
        # next edit to one of them is invisible in the other. The macro NAME is
        # the needle rather than its escaped ``\def`` form, so this does not
        # depend on how the source escapes a backslash.
        package = Path(__file__).resolve().parents[4] / "src" / "scitex_writer"
        # Act
        authors = [
            path
            for path in package.rglob("*.py")
            if "ScitexWriterVersion" in path.read_text(encoding="utf-8", errors="ignore")
            and "_sphinx_html" not in str(path)
        ]
        # Assert
        assert [p.name for p in authors] == ["_version_truth.py"]

    def test_the_stamp_carries_both_macros_for_one_version(self):
        # Arrange
        # Act
        text = version_stamp_tex("4.5.6")
        # Assert
        assert text.count("4.5.6") == 2
