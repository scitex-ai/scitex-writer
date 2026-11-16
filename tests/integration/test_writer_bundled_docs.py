"""The offline documentation shipped by Writer must identify its own version."""

import re
from importlib.metadata import version
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
DOCS = ROOT / "src/scitex_writer/_sphinx_html"
VERSION = version("scitex-writer")


def test_bundled_docs_title_identifies_project_version():
    # Arrange
    index = (DOCS / "index.html").read_text()
    # Act
    title = re.search(r"<title>(.*?)</title>", index).group(1)
    # Assert
    assert f"SciTeX Writer v{VERSION}" in title


def test_bundled_docs_search_options_identify_project_version():
    # Arrange
    script = (DOCS / "_static/documentation_options.js").read_text()
    # Act
    version = re.search(r"\bVERSION:\s*(['\"])(.*?)\1", script).group(2)
    # Assert
    assert version == VERSION


def test_docs_builder_refuses_wrong_installed_version_before_replacing_files(tmp_path):
    # Arrange
    import shutil
    import subprocess
    import sys

    (tmp_path / "scripts").mkdir()
    script = tmp_path / "scripts/build_docs.py"
    shutil.copyfile(ROOT / "scripts/build_docs.py", script)
    (tmp_path / "pyproject.toml").write_text('[project]\nversion = "0.0.0.dev0"\n')
    output = tmp_path / "src/scitex_writer/_sphinx_html"
    output.mkdir(parents=True)
    sentinel = output / "keep.txt"
    sentinel.write_text("unchanged")
    # Act
    result = subprocess.run(
        [sys.executable, str(script)], capture_output=True, text=True
    )
    # Assert
    assert (
        result.returncode != 0,
        "Install this checkout" in result.stderr,
        sentinel.read_text(),
    ) == (True, True, "unchanged")


def test_installed_offline_docs_keep_every_local_html_and_css_resource():
    # Arrange
    from html.parser import HTMLParser
    from importlib.metadata import distribution
    from urllib.parse import unquote, urlsplit

    docs = Path(distribution("scitex-writer").locate_file("scitex_writer/_sphinx_html"))
    missing = []

    class References(HTMLParser):
        def __init__(self):
            super().__init__()
            self.urls = []

        def handle_starttag(self, tag, attrs):
            self.urls.extend(
                value for key, value in attrs if key in {"href", "src"} and value
            )

    # Act
    for page in sorted(docs.rglob("*")):
        if page.suffix == ".html":
            parser = References()
            parser.feed(page.read_text())
            urls = parser.urls
        elif page.suffix == ".css":
            urls = re.findall(r"url\(\s*['\"]?([^)'\"\s]+)", page.read_text())
        else:
            continue
        for url in urls:
            parsed = urlsplit(url)
            if parsed.scheme or parsed.netloc or not parsed.path:
                continue
            target = page.parent / unquote(parsed.path)
            if not target.is_file():
                missing.append((page.relative_to(docs).as_posix(), url))
    # Assert
    assert missing == []
