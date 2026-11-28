#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# Test file for: render_clew.py -- links never carry a build-host path.

import json
import sys
from pathlib import Path

import pytest

ROOT_DIR = Path(__file__).resolve().parent.parent.parent.parent
sys.path.insert(0, str(ROOT_DIR / "scripts" / "python"))

from render_clew import (  # noqa: E402
    EXTERNAL_LINK_PREFIX,
    _portable_link,
    main,
    render_clew_tex,
)


@pytest.fixture
def nested_writer_tex(tmp_path):
    """Render a nested writer (<repo>/.scitex/writer) whose git-root feed names
    one file inside the repo and one outside it by absolute path; return
    (repo root, rendered clew_rendered.tex text)."""
    (tmp_path / ".git").mkdir()
    runtime = tmp_path / ".scitex" / "clew" / "runtime"
    runtime.mkdir(parents=True)
    writer = tmp_path / ".scitex" / "writer"
    writer.mkdir(parents=True)
    feed = {
        "claims": [
            {
                "claim_id": "inside",
                "status": "verified",
                "link": str(tmp_path / "data" / "s.json"),
            },
            {
                "claim_id": "outside",
                "status": "verified",
                "link": "/scratch/someone/runs/r.json",
            },
        ]
    }
    (runtime / "claims.json").write_text(json.dumps(feed))
    assert main(["render_clew.py", str(writer)]) == 0
    return tmp_path, (writer / "00_shared" / "clew_rendered.tex").read_text()


class TestPortableLink:
    def test_absolute_path_inside_root_becomes_relative(self, tmp_path):
        # Arrange
        link = str(tmp_path / "data" / "summary.json")
        # Act
        out = _portable_link(link, tmp_path)
        # Assert
        assert out == "data/summary.json"

    def test_absolute_path_outside_root_keeps_only_the_file_name(self, tmp_path):
        # Arrange
        root = tmp_path / "paper"
        root.mkdir()
        link = str(tmp_path / "elsewhere" / "runs" / "result.json")
        # Act
        out = _portable_link(link, root)
        # Assert
        assert out == f"{EXTERNAL_LINK_PREFIX}result.json"

    def test_relative_path_is_unchanged(self, tmp_path):
        # Arrange
        link = "scripts/a.py"
        # Act
        out = _portable_link(link, tmp_path)
        # Assert
        assert out == link

    @pytest.mark.parametrize(
        "url", ["https://doi.org/10.1/x", "doi:10.1/x", "file:///tmp/x"]
    )
    def test_urls_are_unchanged(self, tmp_path, url):
        # Arrange
        root = tmp_path
        # Act
        out = _portable_link(url, root)
        # Assert
        assert out == url

    def test_no_root_keeps_the_link(self):
        # Arrange
        link = "/abs/x.json"
        # Act
        out = _portable_link(link, None)
        # Assert
        assert out == link

    def test_symlinked_root_still_relativizes(self, tmp_path):
        # Arrange: the feed names the real path, the root is a symlink to it.
        real = tmp_path / "real"
        (real / "data").mkdir(parents=True)
        alias = tmp_path / "alias"
        alias.symlink_to(real)
        # Act
        out = _portable_link(str(real / "data" / "s.json"), alias)
        # Assert
        assert out == "data/s.json"


class TestRenderedTexHasNoHostPath:
    def test_render_relativizes_against_root(self, tmp_path):
        # Arrange
        link = str(tmp_path / "data" / "paper_x" / "summary.json")
        data = {"claims": [{"claim_id": "c1", "status": "verified", "link": link}]}
        # Act
        tex = render_clew_tex(data, root=tmp_path)
        # Assert
        assert "\\@namedef{clew@link@c1}{data/paper\\_x/summary.json}" in tex

    def test_main_names_in_repo_file_relative_to_git_root(self, nested_writer_tex):
        # Arrange
        _, tex = nested_writer_tex
        # Act
        line = "\\@namedef{clew@link@inside}{data/s.json}"
        # Assert
        assert line in tex

    def test_main_names_out_of_repo_file_by_name_only(self, nested_writer_tex):
        # Arrange
        _, tex = nested_writer_tex
        # Act
        line = "\\@namedef{clew@link@outside}{external: r.json}"
        # Assert
        assert line in tex

    def test_main_writes_no_host_directory(self, nested_writer_tex):
        # Arrange
        root, tex = nested_writer_tex
        # Act
        leaked = [d for d in (str(root), "/scratch/") if d in tex]
        # Assert
        assert leaked == []


if __name__ == "__main__":
    sys.exit(pytest.main([__file__, "-v"]))

# EOF
