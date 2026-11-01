"""Real section compiler/API integration; requires Writer's LaTeX toolchain.

Run with the checkout's src first on PYTHONPATH; touches only a private temp tree.
"""
import hashlib
import json
import tempfile
from pathlib import Path

from django.conf import settings

settings.configure(DEFAULT_CHARSET="utf-8", SECRET_KEY="section-preview-test-only")
from django.test import RequestFactory
import pymupdf as fitz
from scitex_writer._django.handlers.preview import handle_section_pdf, handle_section_preview
from scitex_writer._django.services import ProjectState


def post(project, path, content):
    request = RequestFactory().post(
        "/api/preview", data=json.dumps({"section_path": path, "content": content}),
        content_type="application/json",
    )
    response = handle_section_preview(request, project)
    data = json.loads(response.content)
    assert response.status_code == 200 and data.get("success"), data
    response = handle_section_pdf(
        RequestFactory().get("/api/preview/pdf", {"preview_id": data["preview_id"]}), project,
    )
    blob = b"".join(response.streaming_content)
    response.close()
    with fitz.open(stream=blob, filetype="pdf") as pdf:
        pages = len(pdf)
        text = " ".join(" ".join(page.get_text() for page in pdf).split())
    return data, blob, pages, text


with tempfile.TemporaryDirectory(prefix="writer-section-preview-") as directory:
    # Arrange: saved files differ from unsaved buffers; full artifact is separate.
    root = Path(directory)
    (root / "abstract.tex").write_text("Saved abstract remains unchanged.")
    (root / "methods.tex").write_text("Saved methods remains unchanged.")
    project = ProjectState(root)
    abstract = r"\begin{abstract}Scoped abstract sentinel.\end{abstract}"
    methods = r"\section{Methods}Scoped methods sentinel."
    # Act: real packaged snippet wrapper + compiler; real Django PDF adapter.
    a, blob, a_pages, a_text = post(project, "abstract.tex", abstract)
    full = root / "01_manuscript/manuscript.pdf"
    full.parent.mkdir()
    full.write_bytes(blob)
    before = hashlib.sha256(full.read_bytes()).hexdigest()
    b, _, b_pages, b_text = post(project, "methods.tex", methods)
    cached, _, _, _ = post(project, "abstract.tex", abstract)
    # Assert: isolated sections, correct cache, preserved full PDF and source.
    assert a_pages == 1 and "Scoped abstract sentinel." in a_text and "Methods" not in a_text
    assert b_pages == 1 and "Scoped methods sentinel." in b_text and "Abstract" not in b_text
    assert a["preview_id"] != b["preview_id"] and cached["cached"] is True
    assert hashlib.sha256(full.read_bytes()).hexdigest() == before
    assert (root / "abstract.tex").read_text() == "Saved abstract remains unchanged."
    print(json.dumps({"abstract_pages": a_pages, "methods_pages": b_pages, "distinct_previews": True, "cache_hit": True, "full_pdf_preserved": True, "source_preserved": True}))
