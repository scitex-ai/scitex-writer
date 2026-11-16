#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# Timestamp: 2026-02-19
# File: tests/python/test_claim.py

"""Tests for scitex_writer claim feature.

Tests CRUD operations and LaTeX rendering via public API (scitex_writer.claim).
All file I/O uses tmp_path to avoid touching actual project files.
"""

import json
from pathlib import Path

import pytest

# Claims are stored in scitex-clew (the one claim store): every test here
# needs the real store, on a throwaway schema.
pytestmark = pytest.mark.usefixtures("clew_store")


def _make_project(tmp_path: Path) -> Path:
    """Create minimal project structure for claim tests."""
    shared = tmp_path / "00_shared"
    shared.mkdir(parents=True)
    return str(tmp_path)


class TestClaimAdd:
    """Test adding claims."""

    def test_add_statistic_result_success_and_result_claim_id_group_compariso(self, tmp_path):
        # Arrange
        import scitex_writer.claim as sc

        project_dir = _make_project(tmp_path)
        # Act
        result = sc.add(
            project_dir=project_dir,
            claim_id="group_comparison",
            claim_type="statistic",
            value={"t": 4.23, "df": 34, "p": 0.00032, "d": 0.87},
            context="Group A vs B",
        )
        # Assert
        assert (result['success']) and (result['claim_id'] == 'group_comparison')

    def test_add_value_result_success(self, tmp_path):
        # Arrange
        import scitex_writer.claim as sc

        project_dir = _make_project(tmp_path)
        # Act
        result = sc.add(
            project_dir=project_dir,
            claim_id="rt_mean",
            claim_type="value",
            value={"value": 42.3, "unit": "ms"},
        )
        # Assert
        assert result["success"]

    def test_add_citation_result_success(self, tmp_path):
        # Arrange
        import scitex_writer.claim as sc

        project_dir = _make_project(tmp_path)
        # Act
        result = sc.add(
            project_dir=project_dir,
            claim_id="key_finding",
            claim_type="citation",
            value={"text": "as previously reported"},
        )
        # Assert
        assert result["success"]

    def test_add_creates_claims_json_claims_file_exists(self, tmp_path):
        # Arrange
        import scitex_writer.claim as sc
        project_dir = _make_project(tmp_path)
        sc.add(
            project_dir=project_dir,
            claim_id="c1",
            claim_type="citation",
            value={"text": "test"},
        )
        # Act
        claims_file = Path(project_dir) / "00_shared" / "claims.json"
        # Act
        # Assert
        assert claims_file.exists()

    def test_add_creates_claims_json_c1_in_data_claims(self, tmp_path):
        # Arrange
        import scitex_writer.claim as sc
        project_dir = _make_project(tmp_path)
        sc.add(
            project_dir=project_dir,
            claim_id="c1",
            claim_type="citation",
            value={"text": "test"},
        )
        claims_file = Path(project_dir) / "00_shared" / "claims.json"
        # Act
        data = json.loads(claims_file.read_text())
        # Act
        # Assert
        assert "c1" in data["claims"]


    def test_add_preserves_existing(self, tmp_path):
        # Arrange
        import scitex_writer.claim as sc

        project_dir = _make_project(tmp_path)
        sc.add(
            project_dir=project_dir,
            claim_id="c1",
            claim_type="citation",
            value={"text": "first"},
        )
        sc.add(
            project_dir=project_dir,
            claim_id="c2",
            claim_type="citation",
            value={"text": "second"},
        )
        # Act
        result = sc.list(project_dir=project_dir)
        # Assert
        assert result["count"] == 2


class TestClaimList:
    """Test listing claims."""

    def test_list_empty_result_success_and_result_count_0_and_result_claim(self, tmp_path):
        # Arrange
        import scitex_writer.claim as sc

        project_dir = _make_project(tmp_path)
        # Act
        result = sc.list(project_dir=project_dir)
        # Assert
        assert (result['success']) and (result['count'] == 0) and (result['claims'] == [])

    def test_list_after_add(self, tmp_path):
        # Arrange
        import scitex_writer.claim as sc

        project_dir = _make_project(tmp_path)
        sc.add(
            project_dir=project_dir,
            claim_id="stat1",
            claim_type="statistic",
            value={"t": 2.1, "df": 20, "p": 0.05, "d": 0.4},
        )
        # Act
        result = sc.list(project_dir=project_dir)
        # Assert
        assert (result['success']) and (result['count'] == 1) and (result['claims'][0]['claim_id'] == 'stat1') and (result['claims'][0]['type'] == 'statistic')

    def test_list_includes_preview(self, tmp_path):
        # Arrange
        import scitex_writer.claim as sc

        project_dir = _make_project(tmp_path)
        sc.add(
            project_dir=project_dir,
            claim_id="s1",
            claim_type="statistic",
            value={"t": 3.5, "df": 10, "p": 0.006, "d": 0.9},
        )
        result = sc.list(project_dir=project_dir)
        # Act
        claim = result["claims"][0]
        # Assert
        assert "preview_nature" in claim


class TestClaimGet:
    """Test getting individual claims."""

    def test_get_existing_result_success_and_result_claim_type_citation(self, tmp_path):
        # Arrange
        import scitex_writer.claim as sc

        project_dir = _make_project(tmp_path)
        sc.add(
            project_dir=project_dir,
            claim_id="my_claim",
            claim_type="citation",
            value={"text": "test text"},
        )
        # Act
        result = sc.get(project_dir=project_dir, claim_id="my_claim")
        # Assert
        assert (result['success']) and (result['claim']['type'] == 'citation')

    def test_get_missing_not_result_success(self, tmp_path):
        # Arrange
        import scitex_writer.claim as sc

        project_dir = _make_project(tmp_path)
        # Act
        result = sc.get(project_dir=project_dir, claim_id="nonexistent")
        # Assert
        assert not result["success"]


class TestClaimRemove:
    """Test removing claims."""

    def test_remove_existing_result_success_and_sc_list_project_dir_project_dir(self, tmp_path):
        # Arrange
        import scitex_writer.claim as sc

        project_dir = _make_project(tmp_path)
        sc.add(
            project_dir=project_dir,
            claim_id="to_delete",
            claim_type="citation",
            value={"text": "delete me"},
        )
        # Act
        result = sc.remove(project_dir=project_dir, claim_id="to_delete")
        # Assert
        assert (result['success']) and (sc.list(project_dir=project_dir)['count'] == 0)

    def test_remove_missing_not_result_success(self, tmp_path):
        # Arrange
        import scitex_writer.claim as sc

        project_dir = _make_project(tmp_path)
        # Act
        result = sc.remove(project_dir=project_dir, claim_id="ghost")
        # Assert
        assert not result["success"]


class TestClaimFormat:
    """Test formatting claims into rendered strings."""

    def test_format_statistic_nature(self, tmp_path):
        # Arrange
        import scitex_writer.claim as sc

        project_dir = _make_project(tmp_path)
        sc.add(
            project_dir=project_dir,
            claim_id="s1",
            claim_type="statistic",
            value={"t": 4.23, "df": 34, "p": 0.00032, "d": 0.87},
        )
        # Act
        result = sc.format(project_dir=project_dir, claim_id="s1", style="nature")
        # Assert
        assert (result['success']) and ('t' in result['rendered']) and ('4.23' in result['rendered'])

    def test_format_statistic_apa(self, tmp_path):
        # Arrange
        import scitex_writer.claim as sc

        project_dir = _make_project(tmp_path)
        sc.add(
            project_dir=project_dir,
            claim_id="s1",
            claim_type="statistic",
            value={"t": 4.23, "df": 34, "p": 0.00032, "d": 0.87},
        )
        # Act
        result = sc.format(project_dir=project_dir, claim_id="s1", style="apa")
        # Assert
        assert (result['success']) and ('Cohen' in result['rendered'])

    def test_format_statistic_plain(self, tmp_path):
        # Arrange
        import scitex_writer.claim as sc

        project_dir = _make_project(tmp_path)
        sc.add(
            project_dir=project_dir,
            claim_id="s1",
            claim_type="statistic",
            value={"t": 4.23, "df": 34, "p": 0.00032, "d": 0.87},
        )
        # Act
        result = sc.format(project_dir=project_dir, claim_id="s1", style="plain")
        # Assert
        assert (result['success']) and ('$' not in result['rendered'])

    def test_format_p_small(self, tmp_path):
        """p < 0.001 should render as < 0.001, not 0.000."""
        # Arrange
        import scitex_writer.claim as sc

        project_dir = _make_project(tmp_path)
        sc.add(
            project_dir=project_dir,
            claim_id="s1",
            claim_type="statistic",
            value={"t": 5.0, "df": 100, "p": 0.0005, "d": 1.0},
        )
        # Act
        result = sc.format(project_dir=project_dir, claim_id="s1", style="nature")
        # Assert
        assert (result['success']) and ('0.001' in result['rendered'])

    def test_format_citation_result_success_and_as_shown_previously_in_result_r(self, tmp_path):
        # Arrange
        import scitex_writer.claim as sc

        project_dir = _make_project(tmp_path)
        sc.add(
            project_dir=project_dir,
            claim_id="c1",
            claim_type="citation",
            value={"text": "as shown previously"},
        )
        # Act
        result = sc.format(project_dir=project_dir, claim_id="c1", style="nature")
        # Assert
        assert (result['success']) and ('as shown previously' in result['rendered'])

    def test_format_value_result_success_and_42_3_in_result_rendered_and_ms_(self, tmp_path):
        # Arrange
        import scitex_writer.claim as sc

        project_dir = _make_project(tmp_path)
        sc.add(
            project_dir=project_dir,
            claim_id="v1",
            claim_type="value",
            value={"value": 42.3, "unit": "ms"},
        )
        # Act
        result = sc.format(project_dir=project_dir, claim_id="v1", style="nature")
        # Assert
        assert (result['success']) and ('42.3' in result['rendered']) and ('ms' in result['rendered'])


class TestClaimRender:
    """Test rendering all claims to claims_rendered.tex."""

    def test_render_creates_tex_result_success(self, tmp_path):
        # Arrange
        import scitex_writer.claim as sc
        project_dir = _make_project(tmp_path)
        sc.add(
            project_dir=project_dir,
            claim_id="grp",
            claim_type="statistic",
            value={"t": 4.23, "df": 34, "p": 0.00032, "d": 0.87},
        )
        # Act
        result = sc.render(project_dir=project_dir)
        # Act
        # Assert
        assert result["success"]

    def test_render_creates_tex_tex_path_exists(self, tmp_path):
        # Arrange
        import scitex_writer.claim as sc
        project_dir = _make_project(tmp_path)
        sc.add(
            project_dir=project_dir,
            claim_id="grp",
            claim_type="statistic",
            value={"t": 4.23, "df": 34, "p": 0.00032, "d": 0.87},
        )
        result = sc.render(project_dir=project_dir)
        # Act
        tex_path = Path(project_dir) / "00_shared" / "claims_rendered.tex"
        # Act
        # Assert
        assert tex_path.exists()


    def test_render_tex_has_macro(self, tmp_path):
        # Arrange
        import scitex_writer.claim as sc

        project_dir = _make_project(tmp_path)
        sc.add(
            project_dir=project_dir,
            claim_id="my_stat",
            claim_type="statistic",
            value={"t": 2.0, "df": 10, "p": 0.03, "d": 0.5},
        )
        sc.render(project_dir=project_dir)
        # Act
        tex = (Path(project_dir) / "00_shared" / "claims_rendered.tex").read_text()
        # Assert
        assert ('\\vclaim' in tex) and ('mystat' in tex)

    def test_render_all_styles(self, tmp_path):
        """Rendered .tex defines nature, apa, and plain macros for each claim."""
        # Arrange
        import scitex_writer.claim as sc

        project_dir = _make_project(tmp_path)
        sc.add(
            project_dir=project_dir,
            claim_id="s1",
            claim_type="statistic",
            value={"t": 3.0, "df": 20, "p": 0.005, "d": 0.7},
        )
        sc.render(project_dir=project_dir)
        # Act
        tex = (Path(project_dir) / "00_shared" / "claims_rendered.tex").read_text()
        # Assert
        assert ('@nature' in tex) and ('@apa' in tex) and ('@plain' in tex)

    def test_render_empty_result_success_and_result_claims_count_0(self, tmp_path):
        # Arrange
        import scitex_writer.claim as sc
        project_dir = _make_project(tmp_path)
        # Act
        result = sc.render(project_dir=project_dir)
        # Act
        # Assert
        assert (result['success']) and (result['claims_count'] == 0)

    def test_render_empty_tex_path_exists(self, tmp_path):
        # Arrange
        import scitex_writer.claim as sc
        project_dir = _make_project(tmp_path)
        result = sc.render(project_dir=project_dir)
        # Act
        tex_path = Path(project_dir) / "00_shared" / "claims_rendered.tex"
        # Act
        # Assert
        assert tex_path.exists()


    def test_render_emits_hypertarget_for_living_paper(self, tmp_path):
        """Each claim's rendered output wraps in \\hypertarget{vclaim-<id>}{…}
        so PDF.js can locate claim text for Living Paper hover popups (#133).
        The target is emitted once per claim via a one-shot flag so repeat
        \\vclaim{id} calls don't warn about duplicate destinations."""
        # Arrange
        import scitex_writer.claim as sc

        project_dir = _make_project(tmp_path)
        sc.add(
            project_dir=project_dir,
            claim_id="group_comparison",
            claim_type="statistic",
            value={"t": 4.23, "df": 34, "p": 0.00032, "d": 0.87},
        )
        sc.render(project_dir=project_dir)
        # Act
        tex = (Path(project_dir) / "00_shared" / "claims_rendered.tex").read_text()
        # Hypertarget name uses the sanitized id
        # Assert
        assert ('\\hypertarget{vclaim-groupcomparison}' in tex) and ('v@claim@groupcomparison@anchored' in tex) and (all((f'v@claim@groupcomparison@{style}' in tex for style in ('nature', 'apa', 'plain'))))

    def test_render_hypertarget_not_re_emitted_after_first_call(self, tmp_path):
        """The one-shot flag pattern should let multiple \\vclaim{id} calls
        expand without re-emitting the same named destination."""
        # Arrange
        import scitex_writer.claim as sc

        project_dir = _make_project(tmp_path)
        sc.add(
            project_dir=project_dir,
            claim_id="x",
            claim_type="value",
            value={"number": 42, "unit": "Hz"},
        )
        sc.render(project_dir=project_dir)
        # Act
        tex = (Path(project_dir) / "00_shared" / "claims_rendered.tex").read_text()
        # The guarded expansion pattern
        # Assert
        assert ('\\expandafter\\ifx\\csname v@claim@x@anchored\\endcsname\\relax' in tex) and ('\\global\\@namedef{v@claim@x@anchored}' in tex)


class TestClaimPublicApi:
    """Test that scitex_writer.claim exposes the correct public interface."""

    def test_public_functions_exist(self):
        # Arrange
        # Act
        # Assert
        import scitex_writer.claim as sc

        for name in ["add", "list", "get", "remove", "format", "render"]:
            assert (hasattr(sc, name)) and (callable(getattr(sc, name)))

    def test_claim_not_in_top_level_all(self):
        """Internal dataclasses should not appear in scitex_writer.__all__."""
        # Arrange
        # Act
        import scitex_writer as sw

        # Assert
        assert all(name not in sw.__all__ for name in ['CompilationResult', 'ManuscriptTree', 'RevisionTree', 'SupplementaryTree']), f'{name} should be hidden from __all__'

    def test_claim_in_top_level_all(self):
        """claim module should be in scitex_writer.__all__."""
        # Arrange
        # Act
        import scitex_writer as sw

        # Assert
        assert "claim" in sw.__all__
