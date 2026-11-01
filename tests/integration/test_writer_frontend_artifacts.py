"""Real packaged frontend graph, templates and source-map regressions."""

import json
from pathlib import Path

import pytest
import scitex_writer

STATIC = Path(scitex_writer.__file__).parent / "_django/static/writer"


def entry_graph(manifest):
    """Traverse both required entries and all static/dynamic import edges."""
    pending = ["src/index.ts", "src/viewer.ts"]
    seen = set()
    entries = []
    while pending:
        key = pending.pop()
        if key in seen:
            continue
        seen.add(key)
        entry = manifest[key]
        entries.append(entry)
        pending.extend(entry.get("imports", []))
        pending.extend(entry.get("dynamicImports", []))
    return entries


def source_maps():
    return list((STATIC / "assets").glob("*.js.map"))


@pytest.mark.parametrize("entry,expected", [("src/index.ts", "assets/index.js"), ("src/viewer.ts", "assets/viewer.js")])
def test_packaged_entry_filename_matches_template_contract(entry, expected):
    # Arrange
    path = STATIC / ".vite/manifest.json"
    # Act
    manifest = json.loads(path.read_text())
    # Assert
    assert manifest[entry]["file"] == expected


def test_packaged_styles_use_the_existing_shared_entry():
    # Arrange
    path = STATIC / ".vite/manifest.json"
    # Act
    manifest = json.loads(path.read_text())
    styles = {entry["file"] for entry in manifest.values() if entry["file"].endswith(".css")}
    # Assert
    assert styles <= {"assets/index.css"}


@pytest.mark.parametrize("name", ["editor.html", "viewer.html"])
def test_packaged_templates_include_the_shared_stylesheet(name):
    # Arrange
    template = STATIC.parent.parent / "templates/writer" / name
    # Act
    markup = template.read_text()
    # Assert
    assert "writer/assets/index.css" in markup


def test_packaged_entry_graph_contains_all_declared_assets():
    # Arrange
    manifest = json.loads((STATIC / ".vite/manifest.json").read_text())
    # Act
    missing = [relative for entry in entry_graph(manifest)
               for relative in [entry["file"], *entry.get("css", []), *entry.get("assets", [])]
               if not (STATIC / relative).is_file()]
    # Assert
    assert missing == []


def test_packaged_entry_graph_contains_all_javascript_source_maps():
    # Arrange
    manifest = json.loads((STATIC / ".vite/manifest.json").read_text())
    # Act
    missing = [entry["file"] for entry in entry_graph(manifest)
               if entry["file"].endswith(".js")
               and not (STATIC / (entry["file"] + ".map")).is_file()]
    # Assert
    assert missing == []


def test_packaged_javascript_source_maps_are_present():
    # Arrange
    directory = STATIC / "assets"
    # Act
    maps = list(directory.glob("*.js.map"))
    # Assert
    assert maps


def test_packaged_source_maps_remain_below_the_size_bound():
    # Arrange
    maps = source_maps()
    # Act
    oversized = [path.name for path in maps if path.stat().st_size > 10_000_000]
    # Assert
    assert oversized == []


def test_packaged_source_maps_use_version_three():
    # Arrange
    maps = source_maps()
    # Act
    invalid = [path.name for path in maps if json.loads(path.read_text())["version"] != 3]
    # Assert
    assert invalid == []


def test_packaged_source_maps_preserve_each_source_content():
    # Arrange
    maps = source_maps()
    # Act
    invalid = []
    for path in maps:
        mapping = json.loads(path.read_text())
        if len(mapping["sources"]) != len(mapping["sourcesContent"]):
            invalid.append(path.name)
    # Assert
    assert invalid == []


def test_packaged_source_map_contents_are_actual_strings():
    # Arrange
    maps = source_maps()
    # Act
    invalid = [path.name for path in maps
               if not all(isinstance(content, str) for content in json.loads(path.read_text())["sourcesContent"])]
    # Assert
    assert invalid == []


def test_packaged_source_maps_include_monaco_editor_sources():
    # Arrange
    maps = source_maps()
    # Act
    names = {name for path in maps for name in json.loads(path.read_text())["sources"]}
    # Assert
    assert any("monaco-editor/esm/vs/editor/common/config/editorOptions.js" in name for name in names)


def test_editor_static_module_graph_has_no_evaluation_cycle():
    # Arrange
    manifest = json.loads((STATIC / ".vite/manifest.json").read_text())
    cycles = []
    visited = set()

    def visit(key, parents):
        if key in parents:
            cycles.append(parents[parents.index(key):] + [key])
            return
        if key in visited:
            return
        for dependency in manifest[key].get("imports", []):
            visit(dependency, parents + [key])
        visited.add(key)

    # Act
    for entry in ("src/index.ts", "src/viewer.ts"):
        visit(entry, [])
    # Assert
    assert cycles == []
