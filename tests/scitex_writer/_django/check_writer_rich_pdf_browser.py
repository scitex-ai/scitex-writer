"""Real PDF.js Writer consumer proof using normal wheel-derived npm packages.

Pass the frontend directory produced by a normal npm install/build. All HTTP
resources and annotation writes below are disposable protocol fixtures.
"""

from __future__ import annotations

import argparse
import json
import subprocess
import tempfile
from pathlib import Path
from urllib.parse import parse_qs, urlsplit

from playwright.sync_api import sync_playwright


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--chromium", required=True)
    parser.add_argument("--frontend", type=Path, required=True)
    parser.add_argument("--pdf-fixture", type=Path, required=True)
    args = parser.parse_args()
    frontend = args.frontend
    with tempfile.TemporaryDirectory(prefix="writer-rich-test-") as directory:
        temp = Path(directory)
        with tempfile.NamedTemporaryFile(
            mode="w", dir=frontend, suffix=".ts", delete=False
        ) as entry:
            entry.write(
                """import {createWriterPdfViewer} from './src/rich-pdf-adapter';import {PDFViewer} from './src/pdf-viewer';import * as pdfjs from 'pdfjs-dist';pdfjs.GlobalWorkerOptions.workerSrc='/pdf.worker.mjs';Object.assign(window,{createWriterPdfViewer,PDFViewer,pdfjs});"""
            )
            source = Path(entry.name)
        bundle = temp / "test.js"
        try:
            subprocess.run(
                [
                    str(frontend / "node_modules/.bin/esbuild"),
                    str(source),
                    "--bundle",
                    "--preserve-symlinks",
                    "--format=esm",
                    "--loader:.css=empty",
                    f"--outfile={bundle}",
                ],
                check=True,
            )
        finally:
            source.unlink()
        html = """<main class="writer-app" data-api-base="/writer/" data-project-id="fixture/project"><meta name="writer-csrf-token" content="fixture-dom-token"><div id="viewer" style="width:750px;height:480px;overflow:auto"></div></main><script type="module" src="/test.js"></script>"""
        requests = []
        posts = []
        records = [
            {
                "annotation_id": "seed",
                "page": 1,
                "payload": {"text": "Stored fixture note"},
                "region": {"x0": 60, "y0": 620, "x1": 240, "y1": 655},
            },
            {
                "annotation_id": "locked",
                "page": 1,
                "payload": {"text": "Locked fixture provenance"},
                "region": {"x0": 100, "y0": 400, "x1": 220, "y1": 450},
                "source_ref": {"locked": True},
            },
        ]
        with sync_playwright() as p:
            browser = p.chromium.launch(executable_path=args.chromium, headless=True)
            page = browser.new_page(viewport={"width": 1200, "height": 900})
            errors = []
            page.on("pageerror", lambda err: errors.append(str(err)))

            def serve(route):
                url = urlsplit(route.request.url)
                path = url.path
                if path == "/test.js":
                    route.fulfill(
                        content_type="text/javascript", body=bundle.read_bytes()
                    )
                elif path == "/pdf.worker.mjs":
                    route.fulfill(
                        content_type="text/javascript",
                        body=(
                            frontend / "node_modules/pdfjs-dist/build/pdf.worker.mjs"
                        ).read_bytes(),
                    )
                elif path.startswith("/writer/api/"):
                    query = parse_qs(url.query)
                    requests.append(
                        {"path": path, "query": query, "method": route.request.method}
                    )
                    assert query.get("project") == ["fixture/project"]
                    if path in ["/writer/api/pdf", "/writer/api/preview/pdf"]:
                        route.fulfill(
                            content_type="application/pdf",
                            body=args.pdf_fixture.read_bytes(),
                        )
                    elif path == "/writer/api/annotations":
                        if route.request.method == "POST":
                            assert (
                                route.request.headers.get("x-csrftoken")
                                == "fixture-dom-token"
                            )
                            body = route.request.post_data_json
                            posts.append(body)
                            record = {"annotation_id": f"saved-{len(posts)}", **body}
                            records.append(record)
                            route.fulfill(
                                json={
                                    "ok": True,
                                    "annotation_id": record["annotation_id"],
                                    "source_ref": {},
                                    "notified": False,
                                    "notify_error": None,
                                }
                            )
                        else:
                            route.fulfill(
                                json={"annotations": records, "count": len(records)}
                            )
                    else:
                        raise AssertionError("Unexpected API operation " + path)
                else:
                    route.fulfill(content_type="text/html", body=html)

            page.route("http://writer-rich.test/**", serve)
            page.goto("http://writer-rich.test/")
            page.wait_for_function('typeof window.createWriterPdfViewer==="function"')
            page.evaluate(
                """async()=>{window.api=createWriterPdfViewer({container:document.querySelector('#viewer'),pdfjs,workerSrc:'/pdf.worker.mjs'},{getDocType:()=> 'manuscript',canMutate:()=>true});api.setInteractive(false);await api.load('/writer/api/pdf?project=fixture%2Fproject');}"""
            )
            assert page.locator("#viewer canvas").count() == 4
            page.get_by_role(
                "button", name="Locked fixture provenance", exact=True
            ).click()
            assert page.get_by_role("textbox", name="New PDF comment").is_disabled()
            # Even altered DOM cannot bypass the canonical target lock.
            page.get_by_role("textbox", name="New PDF comment").evaluate(
                "(el)=>el.disabled=false"
            )
            page.get_by_role("button", name="Add comment").evaluate(
                "(el)=>el.disabled=false"
            )
            page.get_by_role("textbox", name="New PDF comment").fill(
                "Attempted mutation"
            )
            page.get_by_role("button", name="Add comment").click()
            page.get_by_role("status").get_by_text(
                "Comment mutation refused by document policy"
            ).wait_for()
            assert posts == []
            page.get_by_role("button", name="Close comments").click()
            page.get_by_role("button", name="Stored fixture note", exact=True).click()
            page.get_by_role("textbox", name="New PDF comment").fill(
                "Writer persisted note"
            )
            page.get_by_role("button", name="Add comment").click()
            page.get_by_text("Writer persisted note", exact=True).wait_for()
            assert len(posts) == 1 and posts[0]["doc_type"] == "manuscript"
            assert posts[0]["region"] == {"x0": 60, "y0": 620, "x1": 240, "y1": 655}
            page.evaluate('api.load("/writer/api/pdf?project=fixture%2Fproject&t=2")')
            assert page.locator(".lp-rich-comments").count() == 0
            assert (
                page.get_by_role(
                    "button", name="Writer persisted note", exact=True
                ).count()
                == 1
            )
            page.evaluate(
                """async()=>{api.destroy();window.annotationCount=0;window.wrapper=new PDFViewer({container:document.querySelector('#viewer'),onAnnotate:()=>annotationCount++});if(!await wrapper.loadPreview('preview-fixture'))throw new Error('Section preview failed');}"""
            )
            preview = [
                item for item in requests if item["path"] == "/writer/api/preview/pdf"
            ]
            assert preview[-1]["query"]["preview_id"] == ["preview-fixture"]
            assert (
                page.evaluate("wrapper.downloadUrl").find("/writer/api/preview/pdf?")
                != -1
            )
            assert page.locator(".stx-pdf-text-layer").count() == 2
            assert page.locator("#viewer").evaluate(
                "(el)=>el.scrollWidth<=el.clientWidth+1"
            )
            assert any(
                item["query"].get("doc_type") == ["section-preview-fixture"]
                for item in requests
                if item["path"] == "/writer/api/annotations"
            )
            page.evaluate('wrapper.load("manuscript")')
            assert "/writer/api/pdf?" in page.evaluate("wrapper.downloadUrl")
            assert "preview_id=" not in page.evaluate("wrapper.downloadUrl")
            page.evaluate(
                "wrapper.setMode('markup');wrapper.setTool('box');document.querySelector('#viewer').scrollTop=0;document.querySelector('#viewer').scrollLeft=0"
            )
            box = page.locator("#viewer").bounding_box()
            page.mouse.move(box["x"] + 250, box["y"] + 300)
            page.mouse.down()
            page.mouse.move(box["x"] + 300, box["y"] + 350, steps=4)
            page.mouse.up()
            page.wait_for_function("annotationCount===1")
            page.wait_for_timeout(100)
            assert len(posts) == 2, posts
            assert posts[-1]["payload"]["tool"] == "box"
            page.evaluate("wrapper.destroy()")
            assert page.locator("#viewer").evaluate("(el)=>el.childElementCount") == 0
            assert errors == [], errors
            print(
                json.dumps(
                    {
                        "wheel_frontend": True,
                        "actual_pdf_pages": 2,
                        "annotation_post": {
                            "project_scope": True,
                            "csrf_dom_token": True,
                            "coordinates_unchanged": True,
                        },
                        "canonical_lock_blocks_callback": True,
                        "reload_persisted_note": True,
                        "section_preview_and_full_routes_distinct": True,
                        "fit_width_without_overflow": True,
                        "no_compile_or_manuscript_writes": True,
                        "fixture_annotation_posts": len(posts),
                        "page_errors": errors,
                    }
                )
            )
            browser.close()


if __name__ == "__main__":
    main()
