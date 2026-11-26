#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# Test file for: check_citations.py (compiler-owns citation stub gate)

import subprocess
import sys
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parent.parent.parent.parent
sys.path.insert(0, str(ROOT_DIR / "scripts" / "python"))

from _citation_banner import banner_tex_path  # noqa: E402
from check_citations import (  # noqa: E402
    _resolve_tex_paths,
    audit_citations,
    extract_cited_keys,
    iter_bib_entries,
    resolve_bib_paths,
    stub_reason,
)

_CHECK = str(ROOT_DIR / "scripts" / "python" / "check_citations.py")


def _make_project_with_stub(tmp_path):
    """A minimal project citing one real ref + one scholar stub."""
    bib_dir = tmp_path / "00_shared" / "bib_files"
    bib_dir.mkdir(parents=True)
    (bib_dir / "bibliography.bib").write_text(
        "@article{Berens2009,\n title={CircStat},\n doi={10.18637/jss.v031.i10}\n}\n"
        "@article{Stub2023,\n journal={Pending scitex-scholar metadata lookup},\n"
        " note={Auto-generated stub; replace before submission.}\n}\n"
    )
    man = tmp_path / "01_manuscript"
    man.mkdir(parents=True)
    tex = man / "main.tex"
    tex.write_text(r"We cite \citep{Berens2009} and \cite{Stub2023}.")
    return tex


class TestExtractCitedKeys:
    def test_single_cite_command_yields_its_key(self):
        # Arrange
        tex = r"see \cite{Foo2020}"
        # Act
        keys = extract_cited_keys(tex)
        # Assert
        assert keys == {"Foo2020"}

    def test_multiple_keys_in_one_command_all_extracted(self):
        # Arrange
        tex = r"\citep{A2020,B2021, C2022}"
        # Act
        keys = extract_cited_keys(tex)
        # Assert
        assert keys == {"A2020", "B2021", "C2022"}

    def test_citet_with_optional_notes_extracts_key(self):
        # Arrange
        tex = r"\citet[see][p.~5]{Bar2019}"
        # Act
        keys = extract_cited_keys(tex)
        # Assert
        assert keys == {"Bar2019"}

    def test_commented_out_cite_is_ignored(self):
        # Arrange
        tex = "real \\cite{Keep2020}\n% dropped \\cite{Skip1999}"
        # Act
        keys = extract_cited_keys(tex)
        # Assert
        assert keys == {"Keep2020"}

    def test_escaped_percent_is_not_a_comment(self):
        # Arrange
        tex = r"100\% \cite{Keep2020}"
        # Act
        keys = extract_cited_keys(tex)
        # Assert
        assert keys == {"Keep2020"}

    def test_macro_parameter_placeholder_is_not_a_cite_key(self):
        """Regression: ``\\cite{#1}`` in a \\newcommand body names the macro's
        argument, not a key; it was reported as an unlinked citation."""
        # Arrange
        tex = (
            r"\newcommand{\seeref}[1]{see \citep{#1}}"
            r"\newcommand{\both}[2]{\cite{#1, ##2}}"
            "\n"
            r"Body \cite{Real2020}."
        )
        # Act
        keys = extract_cited_keys(tex)
        # Assert
        assert keys == {"Real2020"}

    def test_text_without_citations_yields_empty_set(self):
        # Arrange
        tex = "plain text, no cites"
        # Act
        keys = extract_cited_keys(tex)
        # Assert
        assert keys == set()


class TestIterBibEntries:
    def test_parses_cite_key_and_field_values(self):
        # Arrange
        bib = (
            "@article{Foo2020,\n  title = {A Title},\n  doi = {10.1/x},\n"
            '  journal = "Nature"\n}\n'
        )
        # Act
        entries = dict(iter_bib_entries(bib))
        # Assert
        e = entries.get("Foo2020", {})
        assert (e.get("doi") == "10.1/x") and (e.get("journal") == "Nature")

    def test_nested_braces_in_field_value_parsed(self):
        # Arrange
        bib = "@article{Foo2020,\n  title = {A {Nested} Title},\n  doi = {10.1/x}\n}\n"
        # Act
        entries = dict(iter_bib_entries(bib))
        # Assert
        assert entries.get("Foo2020", {}).get("doi") == "10.1/x"

    def test_string_and_comment_entries_are_skipped(self):
        # Arrange
        bib = "@string{pub = {ACME}}\n@article{Real2020,\n  doi = {10.1/x}\n}\n"
        # Act
        keys = {k for k, _ in iter_bib_entries(bib)}
        # Assert
        assert keys == {"Real2020"}


class TestStubReason:
    def test_auto_generated_note_marks_a_stub(self):
        # Arrange
        fields = {"note": "Auto-generated stub; replace before submission."}
        # Act
        reason = stub_reason(fields)
        # Assert
        assert reason is not None

    def test_pending_journal_marker_marks_a_stub(self):
        # Arrange
        fields = {"journal": "Pending scitex-scholar metadata lookup"}
        # Act
        reason = stub_reason(fields)
        # Assert
        assert reason is not None

    def test_complete_entry_is_not_a_stub(self):
        # Arrange
        fields = {"title": "Real", "doi": "10.1/x", "journal": "Nature"}
        # Act
        reason = stub_reason(fields)
        # Assert
        assert reason is None

    def test_missing_doi_alone_is_not_a_stub(self):
        # Arrange: a legitimate book/arXiv entry with no DOI must NOT be flagged
        # (no false positives) -- only a scholar stamp marks a stub.
        fields = {"title": "A Book", "publisher": "MIT Press"}
        # Act
        reason = stub_reason(fields)
        # Assert
        assert reason is None


class TestAuditCitations:
    _ENTRIES = {
        "Good2020": {"doi": "10.1/x", "title": "Real"},
        "Stub2023": {"note": "Auto-generated stub; replace before submission."},
        "NoDoi2018": {"title": "A Book", "publisher": "MIT Press"},
    }

    def test_cited_stub_entry_is_reported(self):
        # Arrange
        cited = {"Stub2023"}
        # Act
        stubs, missing, no_doi = audit_citations(cited, self._ENTRIES)
        # Assert
        assert (len(stubs) == 1) and (stubs[0][0] == "Stub2023")

    def test_missing_entry_reported_as_missing_not_stub(self):
        # Arrange
        cited = {"Ghost2000"}
        # Act
        stubs, missing, no_doi = audit_citations(cited, self._ENTRIES)
        # Assert
        assert (missing == ["Ghost2000"]) and (stubs == [])

    def test_missing_doi_is_info_only_not_stub(self):
        # Arrange
        cited = {"NoDoi2018"}
        # Act
        stubs, missing, no_doi = audit_citations(cited, self._ENTRIES)
        # Assert
        assert (stubs == []) and (no_doi == ["NoDoi2018"])

    def test_clean_cited_entry_passes_all_buckets_empty(self):
        # Arrange
        cited = {"Good2020"}
        # Act
        stubs, missing, no_doi = audit_citations(cited, self._ENTRIES)
        # Assert
        assert (stubs == []) and (missing == []) and (no_doi == [])


class TestResolveTexPathsFallback:
    """Without --tex and without $SCITEX_WRITER_COMPILED_TEX the gate scans
    the project's .tex -- but only sources that can be built."""

    def _tree(self, tmp_path):
        live = tmp_path / "01_manuscript" / "contents" / "intro.tex"
        live.parent.mkdir(parents=True)
        live.write_text(r"\cite{Live2020}")
        old = [
            tmp_path / "01_manuscript" / "legacy" / "contents" / "intro_old.tex",
            tmp_path / "01_manuscript" / "archive" / "manuscript_v001.tex",
            tmp_path / "01_manuscript" / "logs" / "build.tex",
        ]
        for path in old:
            path.parent.mkdir(parents=True)
            path.write_text(r"\cite{Old1999}")
        diff = tmp_path / "01_manuscript" / "manuscript_diff.tex"
        diff.write_text(r"\cite{Old1999}")
        return live

    def test_legacy_archive_logs_and_diff_tex_are_not_scanned(self, tmp_path):
        # Arrange
        live = self._tree(tmp_path)
        env = {"SCITEX_WRITER_COMPILED_TEX": ""}
        # Act
        paths = _resolve_tex_paths(tmp_path, None, environ=env)
        # Assert
        assert paths == [str(live)]

    def test_project_under_a_directory_named_archive_is_still_scanned(self, tmp_path):
        """Only directories BELOW the project root are excluded."""
        # Arrange
        root = tmp_path / "archive" / "my-paper"
        live = self._tree(root)
        # Act
        paths = _resolve_tex_paths(root, None, environ={})
        # Assert
        assert paths == [str(live)]

    def test_compiled_tex_from_env_wins_over_the_fallback(self, tmp_path):
        # Arrange
        self._tree(tmp_path)
        compiled = tmp_path / "01_manuscript" / "manuscript.tex"
        compiled.write_text(r"\cite{Live2020}")
        env = {"SCITEX_WRITER_COMPILED_TEX": str(compiled)}
        # Act
        paths = _resolve_tex_paths(tmp_path, None, environ=env)
        # Assert
        assert paths == [str(compiled)]


class TestResolveBibPaths:
    def _make_symlinked_tree(self, tmp_path):
        """A project whose contents/bibliography.bib is a symlink chain to the
        real (legacy-style) enriched bib -- mirrors the live neurovista tree."""
        real = tmp_path / "shared" / "bib_files" / "enriched.bib"
        real.parent.mkdir(parents=True)
        real.write_text("@article{Foo2020,\n  doi = {10.1/x}\n}\n")
        mid = tmp_path / "shared" / "bibliography.bib"
        mid.symlink_to(real)
        contents = tmp_path / "01_manuscript" / "contents"
        contents.mkdir(parents=True)
        (contents / "bibliography.bib").symlink_to(mid)
        tex = contents / "main.tex"
        tex.write_text(r"\bibliography{bibliography}" + "\n\\cite{Foo2020}")
        return tex, real

    def test_follows_symlink_chain_from_bibliography_command(self, tmp_path):
        # Arrange
        tex, real = self._make_symlinked_tree(tmp_path)
        # Act
        resolved = resolve_bib_paths(tmp_path, [str(tex)], None)
        # Assert
        assert resolved == [real.resolve()]

    def test_explicit_bib_argument_overrides_tex_target(self, tmp_path):
        # Arrange
        tex, real = self._make_symlinked_tree(tmp_path)
        other = tmp_path / "other.bib"
        other.write_text("@article{Bar,\n doi={10.2/y}\n}\n")
        # Act
        resolved = resolve_bib_paths(tmp_path, [str(tex)], str(other))
        # Assert
        assert resolved == [other.resolve()]

    def test_addbibresource_with_extension_resolves(self, tmp_path):
        # Arrange
        contents = tmp_path / "01_manuscript" / "contents"
        contents.mkdir(parents=True)
        bib = contents / "refs.bib"
        bib.write_text("@article{Baz,\n doi={10.3/z}\n}\n")
        tex = contents / "main.tex"
        tex.write_text(r"\addbibresource{refs.bib}")
        # Act
        resolved = resolve_bib_paths(tmp_path, [str(tex)], None)
        # Assert
        assert resolved == [bib.resolve()]


class TestBannerModeCli:
    def test_banner_mode_exits_zero_so_compile_proceeds(self, tmp_path):
        # Arrange
        tex = _make_project_with_stub(tmp_path)
        # Act
        proc = subprocess.run(
            [sys.executable, _CHECK, str(tmp_path), "--tex", str(tex), "--level", "banner"],
            capture_output=True, text=True,
        )
        # Assert
        assert proc.returncode == 0

    def test_banner_mode_writes_the_banner_artifact(self, tmp_path):
        # Arrange
        tex = _make_project_with_stub(tmp_path)
        # Act
        subprocess.run(
            [sys.executable, _CHECK, str(tmp_path), "--tex", str(tex), "--level", "banner"],
            capture_output=True, text=True,
        )
        # Assert
        assert banner_tex_path(tmp_path).is_file()

    def test_strict_error_mode_fails_and_writes_no_banner(self, tmp_path):
        # Arrange
        tex = _make_project_with_stub(tmp_path)
        # Act
        proc = subprocess.run(
            [sys.executable, _CHECK, str(tmp_path), "--tex", str(tex), "--level", "error"],
            capture_output=True, text=True,
        )
        # Assert
        assert (proc.returncode == 1) and (not banner_tex_path(tmp_path).exists())

    def test_clean_run_removes_a_stale_banner(self, tmp_path):
        # Arrange: leave a stale banner, then run against a stub-free project.
        bib_dir = tmp_path / "00_shared" / "bib_files"
        bib_dir.mkdir(parents=True)
        (bib_dir / "bibliography.bib").write_text(
            "@article{Berens2009,\n title={CircStat},\n doi={10.1/x}\n}\n"
        )
        man = tmp_path / "01_manuscript"
        man.mkdir(parents=True)
        tex = man / "main.tex"
        tex.write_text(r"\citep{Berens2009}")
        banner_tex_path(tmp_path).parent.mkdir(parents=True, exist_ok=True)
        banner_tex_path(tmp_path).write_text("stale banner")
        # Act
        subprocess.run(
            [sys.executable, _CHECK, str(tmp_path), "--tex", str(tex), "--level", "banner"],
            capture_output=True, text=True,
        )
        # Assert
        assert not banner_tex_path(tmp_path).exists()


if __name__ == "__main__":
    import pytest

    sys.exit(pytest.main([__file__, "-v"]))
