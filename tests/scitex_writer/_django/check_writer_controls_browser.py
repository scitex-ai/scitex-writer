"""Exercise real Writer components in Chromium with disposable API fixtures.

Run explicitly with the project's Python environment and a Chromium path.
No user projects, database, annotation writes, or compile endpoints are used.
"""

from __future__ import annotations

import argparse
import json
import subprocess
import tempfile
from pathlib import Path

from playwright.sync_api import sync_playwright


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--chromium", required=True)
    args = parser.parse_args()
    repo = Path(__file__).resolve().parents[3]
    django = repo / "src/scitex_writer/_django"
    frontend = django / "frontend"
    with tempfile.TemporaryDirectory(prefix="writer-controls-") as directory:
        temp = Path(directory)
        entry = temp / "entry.ts"
        entry.write_text(
            """
import {InsertPanel} from "INSERT";
import {mountAnnotationUI} from "ANNOT";
import {mountPdfMenu} from "MENU";
Object.assign(window,{InsertPanel,mountAnnotationUI,mountPdfMenu});
""".replace("INSERT", str(frontend / "src/insert-panel.ts"))
            .replace("ANNOT", str(frontend / "src/annotation-ui.ts"))
            .replace("MENU", str(frontend / "src/pdf-menu.ts"))
        )
        bundle = temp / "components.js"
        subprocess.run(
            [
                str(frontend / "node_modules/.bin/esbuild"),
                str(entry),
                "--bundle",
                "--format=iife",
                f"--outfile={bundle}",
            ],
            check=True,
            capture_output=True,
        )
        with sync_playwright() as p:
            browser = p.chromium.launch(executable_path=args.chromium, headless=True)
            page = browser.new_page(viewport={"width": 1100, "height": 1000})
            errors = []
            page.on("pageerror", lambda error: errors.append(str(error)))

            def respond(route):
                path = route.request.url
                if "/api/figures" in path or "/api/tables" in path:
                    key = "figures" if "/api/figures" in path else "tables"
                    route.fulfill(
                        json={
                            key: [
                                {
                                    "name": "Fixture",
                                    "label": "fixture",
                                    "insert": r"\ref{fixture}",
                                    "thumbnail_url": "/thumb.svg",
                                    "media_ext": ".svg",
                                }
                            ]
                        }
                    )
                elif "/thumb.svg" in path:
                    route.fulfill(
                        content_type="image/svg+xml",
                        body='<svg xmlns="http://www.w3.org/2000/svg" width="40" height="40"><rect width="40" height="40" fill="gray"/></svg>',
                    )
                else:
                    route.fulfill(
                        content_type="text/html",
                        body="""<div class="writer-app" data-api-base="/" data-app-mode="standalone" data-project-dir="fixture">
<nav id="bar"><button data-pane="pdf">PDF</button><button data-pane="fig">Fig</button><button data-pane="table">Table</button></nav>
<div class="pdf-menu"><button id="btn-pdf-menu" aria-expanded="false">PDF and annotation options</button><div id="pdf-menu-list" class="pdf-menu-list u-hidden"><button class="pdf-menu-item">Fit</button></div></div>
<div id="toolbar"></div><div id="annotations"></div><div id="panel"></div><div class="monaco-editor"><div class="margin">Gutter</div></div></div>""",
                    )

            page.route("http://writer.test/**", respond)
            page.goto("http://writer.test/")
            for name in ["editor.css", "annotations.css"]:
                page.add_style_tag(
                    content=(django / "static/writer/css" / name).read_text()
                )
            page.add_style_tag(
                content=":root {--workspace-border-default:rgb(80,90,100)} .u-hidden{display:none!important}"
            )
            page.add_script_tag(path=str(bundle))
            page.evaluate("""() => {
window.inserted=[];window.modes=[];
window.panel=new window.InsertPanel({bar:document.querySelector('#bar'),panel:document.querySelector('#panel'),getDocType:()=> 'manuscript',insertAtCursor:text=>window.inserted.push(text)});
window.mountAnnotationUI({toolbar:document.querySelector('#toolbar'),panel:document.querySelector('#annotations'),menu:{button:document.querySelector('#btn-pdf-menu'),list:document.querySelector('#pdf-menu-list')},controller:{setMode:v=>window.modes.push(v),setTool:()=>{},setCategory:()=>{},annotations:()=>[],setAnnotationText:()=>{},setAnnotationCategory:()=>{},removeAnnotation:()=>{},exportMarkdown:()=>''}});
window.mountPdfMenu(document.querySelector('.writer-app'));
}""")
            for pane in ["fig", "table"]:
                page.locator(f'[data-pane="{pane}"]').click()
                row = page.locator(".insert-item")
                row.wait_for()
                page.wait_for_function(
                    'document.querySelector(".insert-item-thumb").naturalWidth > 0'
                )
                assert row.locator(".insert-item-sub").count() == 0
                assert (
                    row.locator(".insert-item-snippet").inner_text() == r"\ref{fixture}"
                )
                before = page.evaluate("window.inserted.length")
                row.locator("img").click()
                assert page.evaluate("window.inserted.length") == before
                transfer = page.evaluate_handle("new DataTransfer()")
                row.dispatch_event("dragstart", {"dataTransfer": transfer})
                assert (
                    transfer.evaluate(
                        '(data)=>data.getData("application/x-scitex-insert")'
                    )
                    == r"\ref{fixture}"
                )
                row.locator(".insert-item-action").click()
                assert page.evaluate("window.inserted.length") == before + 1
            assert page.locator("#btn-annot-menu").count() == 0
            assert (
                page.locator("#toolbar").evaluate("(el)=>getComputedStyle(el).display")
                == "none"
            )
            page.locator("#btn-pdf-menu").click()
            page.get_by_role("menuitem", name="Markup mode").click()
            assert page.evaluate("window.modes.at(-1)") == "markup"
            assert page.locator("#pdf-menu-list").evaluate(
                '(el)=>el.classList.contains("u-hidden")'
            )
            page.locator("#btn-pdf-menu").click()
            page.keyboard.press("Escape")
            assert page.locator("#btn-pdf-menu").evaluate(
                "(el)=>document.activeElement===el"
            )
            edge = page.locator(".margin").evaluate(
                "(el)=>{let s=getComputedStyle(el);return [s.borderLeftWidth,s.borderRightWidth,s.borderLeftColor]}"
            )
            assert edge == ["1px", "1px", "rgb(80, 90, 100)"]
            assert errors == [], errors
            print(
                json.dumps(
                    {
                        "figure_and_table": [
                            "thumbnail rendered",
                            "row click inert",
                            "drag MIME preserved",
                            "explicit Insert reference",
                            "no duplicate ref",
                        ],
                        "shared_menu": [
                            "one trigger",
                            "mode callback",
                            "Escape focus return",
                            "empty toolbar hidden",
                        ],
                        "gutter": edge,
                        "page_errors": errors,
                    }
                )
            )
            browser.close()


if __name__ == "__main__":
    main()
