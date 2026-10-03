#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# File: tests/scitex_writer/_mcp/handlers/test__archive_pipeline.py

"""Tests for the pure-Python archive pipeline (port of process_archive.sh).

Real inputs throughout: a real git repository under ``tmp_path`` holding real
compiled outputs, and the same config keys the shell read. The timestamp is
injected as an argument (``now=``) rather than patched -- the pipeline takes it as
a parameter precisely so the archive id is testable without a mock.

The dirty-tree case is the contract: an archive is stamped with a commit hash, so
it may only snapshot a tree that actually matches that commit.
"""

import os
import subprocess
from datetime import datetime

import pytest

from scitex_writer._mcp.handlers import _archive_pipeline

_CONFIG = (
    "paths:\n"
    '  doc_log_dir: "./01_manuscript/logs"\n'
    '  compiled_tex: "./01_manuscript/manuscript.tex"\n'
    '  compiled_pdf: "./01_manuscript/manuscript.pdf"\n'
    '  diff_tex: "./01_manuscript/manuscript_diff.tex"\n'
    '  diff_pdf: "./01_manuscript/manuscript_diff.pdf"\n'
    '  archive_dir: "./01_manuscript/archive"\n'
)

_STAMP = datetime(2026, 7, 12, 9, 30, 0)


@pytest.fixture(autouse=True)
def _isolated_git_environment(tmp_path):
    """Keep hook-local Git context out of temporary projects, then restore it."""
    local_env_vars = subprocess.run(
        ["git", "-C", str(tmp_path.resolve()), "rev-parse", "--local-env-vars"],
        check=True,
        capture_output=True,
        text=True,
    ).stdout.splitlines()
    saved_values = {name: os.environ[name] for name in local_env_vars if name in os.environ}
    try:
        for name in local_env_vars:
            os.environ.pop(name, None)
        yield
    finally:
        for name in local_env_vars:
            os.environ.pop(name, None)
        os.environ.update(saved_values)


def _git_cmd(repo, *args):
    subprocess.run(
        ["git", "-C", str(repo), *args], check=True, capture_output=True, text=True
    )


def _seed_project(tmp_path, outputs=("manuscript.tex", "manuscript.pdf")):
    """A real, CLEAN git project holding the given compiled outputs."""
    cfg = tmp_path / "config"
    cfg.mkdir()
    (cfg / "config_manuscript.yaml").write_text(_CONFIG, encoding="utf-8")
    doc = tmp_path / "01_manuscript"
    doc.mkdir()
    for name in outputs:
        (doc / name).write_bytes(b"%PDF-1.4 content\n")
    _git_cmd(tmp_path, "init", "-q")
    _git_cmd(tmp_path, "config", "user.email", "tester@example.com")
    _git_cmd(tmp_path, "config", "user.name", "Tester")
    _git_cmd(tmp_path, "add", "-A")
    _git_cmd(tmp_path, "commit", "-q", "-m", "compiled outputs")
    return tmp_path


def _archive_dir(project):
    return project / "01_manuscript" / "archive"


class TestArchivedName:
    def test_plain_stem_gets_the_id_appended(self):
        # Arrange
        stem = "manuscript"
        # Act
        name = _archive_pipeline.archived_name(stem, "20260712-093000_abc1234")
        # Assert
        assert name == "manuscript_20260712-093000_abc1234"

    def test_diff_stem_keeps_the_diff_marker_last(self):
        # Arrange
        stem = "manuscript_diff"
        # Act
        name = _archive_pipeline.archived_name(stem, "20260712-093000_abc1234")
        # Assert
        assert name == "manuscript_20260712-093000_abc1234_diff"


class TestPipelineErrors:
    def test_invalid_doc_type_returns_actionable_error(self):
        # Arrange
        bad_doc_type = "poster"
        # Act
        result = _archive_pipeline.process(".", bad_doc_type)
        # Assert
        assert result["success"] is False and "poster" in result["error"]

    def test_missing_project_dir_returns_error_hint(self, tmp_path):
        # Arrange
        absent = tmp_path / "nope"
        # Act
        result = _archive_pipeline.process(str(absent), "manuscript")
        # Assert
        assert result["success"] is False and "not found" in result["error"]

    def test_missing_config_returns_error_hint(self, tmp_path):
        # Arrange
        (tmp_path / "01_manuscript").mkdir()
        # Act
        result = _archive_pipeline.process(str(tmp_path), "manuscript")
        # Assert
        assert result["success"] is False and "Config not found" in result["error"]

    def test_no_archive_flag_skips_pipeline(self, tmp_path):
        # Arrange
        project = _seed_project(tmp_path)
        # Act
        result = _archive_pipeline.process(str(project), "manuscript", no_archive=True)
        # Assert
        assert result["skipped"] is True

    def test_escaping_config_path_is_refused(self, tmp_path):
        # Arrange
        project = tmp_path / "proj"
        (project / "config").mkdir(parents=True)
        (project / "config" / "config_manuscript.yaml").write_text(
            _CONFIG.replace('archive_dir: "./01', 'archive_dir: "../01'),
            encoding="utf-8",
        )
        (project / "01_manuscript").mkdir()
        # Act
        result = _archive_pipeline.process(str(project), "manuscript")
        # Assert
        assert "OUTSIDE the project root" in result["error"]


class TestCleanTreeGate:
    def test_dirty_tree_is_skipped_not_archived(self, tmp_path):
        # Arrange
        project = _seed_project(tmp_path)
        (project / "01_manuscript" / "manuscript.tex").write_text(
            "edited\n", encoding="utf-8"
        )
        # Act
        result = _archive_pipeline.process(str(project), "manuscript")
        # Assert
        assert result["skipped"] is True

    def test_dirty_tree_skip_states_its_reason(self, tmp_path):
        # Arrange
        project = _seed_project(tmp_path)
        (project / "01_manuscript" / "manuscript.tex").write_text(
            "edited\n", encoding="utf-8"
        )
        # Act
        result = _archive_pipeline.process(str(project), "manuscript")
        # Assert
        assert "uncommitted changes" in result["skip_reason"]

    def test_dirty_tree_writes_no_archive_file(self, tmp_path):
        # Arrange
        project = _seed_project(tmp_path)
        (project / "01_manuscript" / "manuscript.tex").write_text(
            "edited\n", encoding="utf-8"
        )
        # Act
        _archive_pipeline.process(str(project), "manuscript")
        # Assert
        assert list(_archive_dir(project).glob("*")) == []

    def test_non_git_project_is_skipped_not_archived(self, tmp_path):
        # Arrange
        cfg = tmp_path / "config"
        cfg.mkdir()
        (cfg / "config_manuscript.yaml").write_text(_CONFIG, encoding="utf-8")
        (tmp_path / "01_manuscript").mkdir()
        # Act
        result = _archive_pipeline.process(str(tmp_path), "manuscript")
        # Assert
        assert result["skipped"] is True


class TestCleanTreeArchive:
    @pytest.fixture
    def archived(self, tmp_path):
        project = _seed_project(
            tmp_path,
            outputs=(
                "manuscript.tex",
                "manuscript.pdf",
                "manuscript_diff.tex",
                "manuscript_diff.pdf",
            ),
        )
        return project, _archive_pipeline.process(
            str(project), "manuscript", now=_STAMP
        )

    def test_archive_id_carries_timestamp_and_hash(self, archived):
        # Arrange
        _, result = archived
        # Act
        archive_id = result["archive_id"]
        # Assert
        assert archive_id.startswith("20260712-093000_")

    def test_every_compiled_output_is_archived(self, archived):
        # Arrange
        _, result = archived
        # Act
        count = len(result["archived"])
        # Assert
        assert count == 4

    def test_stamped_copy_is_written_to_disk(self, archived):
        # Arrange
        project, result = archived
        # Act
        stamped = _archive_dir(project) / f"manuscript_{result['archive_id']}.pdf"
        # Assert
        assert stamped.is_file()

    def test_diff_copy_keeps_the_diff_marker_last(self, archived):
        # Arrange
        project, result = archived
        # Act
        stamped = _archive_dir(project) / f"manuscript_{result['archive_id']}_diff.pdf"
        # Assert
        assert stamped.is_file()

    def test_unstamped_current_copy_is_written(self, archived):
        # Arrange
        project, _ = archived
        # Act
        current = _archive_dir(project) / "manuscript.pdf"
        # Assert
        assert current.is_file()

    def test_archived_content_matches_the_source(self, archived):
        # Arrange
        project, result = archived
        stamped = _archive_dir(project) / f"manuscript_{result['archive_id']}.pdf"
        # Act
        content = stamped.read_bytes()
        # Assert
        assert content == (project / "01_manuscript" / "manuscript.pdf").read_bytes()

    def test_absent_output_is_reported_as_missing(self, tmp_path):
        # Arrange
        project = _seed_project(tmp_path, outputs=("manuscript.tex",))
        # Act
        result = _archive_pipeline.process(str(project), "manuscript", now=_STAMP)
        # Assert
        assert len(result["missing"]) == 3

    def test_absent_output_does_not_fail_the_run(self, tmp_path):
        # Arrange
        project = _seed_project(tmp_path, outputs=("manuscript.tex",))
        # Act
        result = _archive_pipeline.process(str(project), "manuscript", now=_STAMP)
        # Assert
        assert result["success"] is True, result.get("error")
