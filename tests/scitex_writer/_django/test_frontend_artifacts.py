"""The shipped editor must resolve its complete generated asset graph."""

import json
from pathlib import Path

import scitex_writer


STATIC = Path(scitex_writer.__file__).parent / "_django/static/writer"


def test_packaged_entry_graph_has_all_scripts_styles_fonts_and_maps():
    manifest = json.loads((STATIC / ".vite/manifest.json").read_text())
    assert manifest["src/index.ts"]["file"] == "assets/index.js"
    assert manifest["src/viewer.ts"]["file"] == "assets/viewer.js"
    styles = {entry["file"] for entry in manifest.values() if entry["file"].endswith(".css")}
    assert styles <= {"assets/index.css"}
    for name in ["editor.html", "viewer.html"]:
        template = STATIC.parent.parent / "templates/writer" / name
        assert "writer/assets/index.css" in template.read_text()
    pending = ["src/index.ts", "src/viewer.ts"]
    seen = set()
    while pending:
        key = pending.pop()
        if key in seen:
            continue
        seen.add(key)
        entry = manifest[key]
        for relative in [entry["file"], *entry.get("css", []), *entry.get("assets", [])]:
            assert (STATIC / relative).is_file(), relative
        if entry["file"].endswith(".js"):
            assert (STATIC / (entry["file"] + ".map")).is_file()
        pending.extend(entry.get("imports", []))
        pending.extend(entry.get("dynamicImports", []))


def test_complete_source_maps_fit_the_native_ten_megabyte_file_guard():
    maps = list((STATIC / "assets").glob("*.js.map"))
    assert maps
    source_names = set()
    for path in maps:
        assert path.stat().st_size <= 10_000_000, path.name
        mapping = json.loads(path.read_text())
        assert mapping["version"] == 3
        assert len(mapping["sources"]) == len(mapping["sourcesContent"])
        assert all(isinstance(content, str) for content in mapping["sourcesContent"])
        source_names.update(mapping["sources"])
    assert any("monaco-editor/esm/vs/editor/common/config/editorOptions.js" in name for name in source_names)
