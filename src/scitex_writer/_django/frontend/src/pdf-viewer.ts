/**
 * PDF pane — backed by the shared L1 viewer (`@scitex/ui/pdf-viewer`, ADR 0001).
 *
 * Swaps Writer's from-scratch pdfjs pane to the shared component (the ADR's
 * "first consumer" step) WITHOUT changing this class's public surface, so
 * existing callers (viewer.ts, index.ts, compile.ts) are untouched:
 *   load / renderPlaceholder / clear / setZoom / setFitWidth / goToPage / zoomPercent
 *
 * Zoom/fit/scroll delegate to L1 (setScale / fitWidth / scrollToPage). On top it
 * adds the pen-annotation loop: L1 hooks (onPenInput / onRegionSelect) →
 * AnnotationStore (the writer-owned neutral port) → setMarks echo. The store is
 * the SSoT the controlled overlay renders from; producers mutate it, consumers
 * read `annotations()` / `exportMarkdown()`.
 */

import {
  createPdfViewer,
  type Mark,
  type PdfRect,
  type PdfTool,
  type PdfViewerApi,
  type PenInput,
} from "@scitex/sdk/ui/pdf-viewer";

import { resourceUrl, postAnnotation } from "./api";
import {
  ANNOTATION_CATEGORIES,
  type Annotation,
  type AnnotationCategory,
  AnnotationStore,
  type AnnotationTool,
  CATEGORY_ICONS,
  CATEGORY_LABELS,
  type EditorMode,
} from "./annotations";
import { type ContextMenuItem, showContextMenu } from "./context-menu";

interface PDFViewerOptions {
  container: HTMLElement;
  /** Called when a new annotation is created (for the comment/details panel). */
  onAnnotate?: (annotation: Annotation) => void;
}

/** L1 pen tool → annotation tool (L1 has no underline/box: rect ↦ box). */
const TOOL_L1_TO_ANN: Record<PdfTool, AnnotationTool> = {
  highlight: "highlight",
  rect: "box",
  freehand: "freehand",
  circle: "circle",
  arrow: "arrow",
};

/** Annotation tool → L1 pen tool (box ↦ rect; underline has no L1 equivalent yet). */
const TOOL_ANN_TO_L1: Partial<Record<AnnotationTool, PdfTool>> = {
  highlight: "highlight",
  box: "rect",
  freehand: "freehand",
  circle: "circle",
  arrow: "arrow",
};

const MIN_SCALE = 0.4;
const MAX_SCALE = 3;

export class PDFViewer {
  private readonly container: HTMLElement;
  private readonly api: PdfViewerApi;
  private readonly store = new AnnotationStore();
  private readonly onAnnotate?: (annotation: Annotation) => void;
  private activeCategory: AnnotationCategory = "highlight";
  private activeTool: AnnotationTool = "highlight";
  private currentMode: EditorMode = "markup";
  private currentDocType = "manuscript";
  private placeholder: HTMLElement | null = null;

  constructor(options: PDFViewerOptions) {
    this.container = options.container;
    this.container.classList.add("pdf-viewer-host");
    this.onAnnotate = options.onAnnotate;
    this.api = createPdfViewer({
      container: this.container,
      hooks: {
        onPenInput: (input) => this.handlePen(input),
        onRegionSelect: (region) => this.handleRegion(region),
      },
    });
    this.container.addEventListener("contextmenu", (e) =>
      this.handleContextMenu(e),
    );
  }

  async load(docType: string): Promise<boolean> {
    this.currentDocType = docType;
    const url =
      resourceUrl(`api/pdf?doc_type=${encodeURIComponent(docType)}&t=${Date.now()}`);
    this.clearPlaceholder();
    try {
      await this.api.load(url);
      this.echoMarks();
      return true;
    } catch (err) {
      console.warn("[pdf-viewer] load failed:", err);
      this.renderPlaceholder();
      return false;
    }
  }

  renderPlaceholder(message = "No PDF available."): void {
    this.clearPlaceholder();
    const el = document.createElement("div");
    el.className = "pdf-placeholder";
    el.innerHTML = `<p>${message}</p><p class="hint">Click Compile to generate.</p>`;
    this.container.appendChild(el);
    this.placeholder = el;
  }

  private clearPlaceholder(): void {
    this.placeholder?.remove();
    this.placeholder = null;
  }

  clear(): void {
    this.store.replaceAll([]);
    this.echoMarks();
    this.renderPlaceholder();
  }

  setZoom(delta: number): void {
    const next = Math.max(
      MIN_SCALE,
      Math.min(MAX_SCALE, this.api.getScale() + delta),
    );
    void this.api.setScale(next);
  }

  setFitWidth(): void {
    void this.api.fitWidth();
  }

  /** Scroll a 1-based page into view (the Hints "jump to page" anchor). */
  goToPage(page: number): void {
    this.api.scrollToPage(page);
  }

  get zoomPercent(): number {
    return Math.round(this.api.getScale() * 100);
  }

  // --- annotation layer -----------------------------------------------------

  /** Category applied to the next mark (the domain buttons). */
  setCategory(category: AnnotationCategory): void {
    this.activeCategory = category;
  }

  /** Active pen tool (maps annotation-tool naming onto L1's PdfTool). */
  setTool(tool: AnnotationTool): void {
    this.activeTool = tool;
    const t = TOOL_ANN_TO_L1[tool];
    if (t) this.api.setTool(t);
  }

  /**
   * Editor mode (ADR 0001 §2): Read/Review disable pen editing, Markup enables
   * it. Marks keep rendering in every mode — only the pen overlay's
   * interactivity toggles, via L1's `setInteractive` (scitex-ui-pdf-viewer-l1).
   * Guarded with `?.` so this is a no-op until that L1 method lands, keeping the
   * mode switch shippable in the meantime.
   */
  setMode(mode: EditorMode): void {
    this.currentMode = mode;
    const interactive = mode === "markup";
    (
      this.api as { setInteractive?: (enabled: boolean) => void }
    ).setInteractive?.(interactive);
  }

  annotations(): Annotation[] {
    return this.store.list();
  }

  /** Update an annotation's note text (from the comment box / voice input). */
  setAnnotationText(id: string, text: string): void {
    this.store.update(id, { text });
    this.echoMarks();
  }

  /** Re-categorize an existing annotation (the row right-click menu). */
  setAnnotationCategory(id: string, category: AnnotationCategory): void {
    this.store.update(id, { category });
    this.echoMarks();
  }

  removeAnnotation(id: string): void {
    this.store.remove(id);
    this.echoMarks();
  }

  exportMarkdown(title?: string): string {
    return this.store.toMarkdown(title);
  }

  destroy(): void {
    this.api.destroy();
  }

  private handlePen(input: PenInput): void {
    const first = input.path[0];
    if (!first) return;
    const ann = this.store.add(
      {
        page: input.page,
        anchor: { page: input.page, pdfX: first.x, pdfY: first.y },
        path: input.path.map((pt) => [pt.x, pt.y] as [number, number]),
        tool: TOOL_L1_TO_ANN[input.tool],
        category: this.activeCategory,
        text: "",
      },
      new Date().toISOString(),
    );
    this.echoMarks();
    this.onAnnotate?.(ann);
    this.postToBackend(ann);
  }

  private handleRegion(region: PdfRect): void {
    // Only turn a drag into a persistent box when the box tool is deliberately
    // active. Otherwise a stray drag (e.g. trying to select text) silently
    // created an undeletable rectangle — the reported surprise.
    if (this.activeTool !== "box") return;
    const ann = this.store.add(
      {
        page: region.page,
        anchor: { page: region.page, pdfX: region.x, pdfY: region.y },
        region: {
          page: region.page,
          x0: region.x,
          y0: region.y,
          x1: region.x + region.w,
          y1: region.y + region.h,
        },
        tool: "box",
        category: this.activeCategory,
        text: "",
      },
      new Date().toISOString(),
    );
    this.echoMarks();
    this.onAnnotate?.(ann);
    this.postToBackend(ann);
  }

  /**
   * Right-click on the PDF area (Markup mode only, operator request — "make
   * effective use of right-click to enrich the menu"): a quick category-pick
   * menu that drops a small marker at the exact click point, instead of
   * requiring toolbar tool+category selection then a drag.
   */
  private handleContextMenu(event: MouseEvent): void {
    if (this.currentMode !== "markup") return;
    const coords = this.api.getCoords(event.clientX, event.clientY);
    if (!coords) return;
    event.preventDefault();
    const items: ContextMenuItem[] = ANNOTATION_CATEGORIES.map((category) => ({
      label: CATEGORY_LABELS[category],
      icon: CATEGORY_ICONS[category],
      onSelect: () => this.addQuickMark(coords, category),
    }));
    showContextMenu(event.clientX, event.clientY, items);
  }

  /** Drop a small square mark at a point (right-click quick-add). */
  private addQuickMark(
    coords: { page: number; pdfX: number; pdfY: number },
    category: AnnotationCategory,
  ): void {
    const { page, pdfX, pdfY } = coords;
    const size = 8;
    const ann = this.store.add(
      {
        page,
        anchor: { page, pdfX, pdfY },
        region: {
          page,
          x0: pdfX - size,
          y0: pdfY - size,
          x1: pdfX + size,
          y1: pdfY + size,
        },
        tool: "box",
        category,
        text: "",
      },
      new Date().toISOString(),
    );
    this.echoMarks();
    this.onAnnotate?.(ann);
    this.postToBackend(ann);
  }

  /**
   * POST a freshly-created mark to the backend (ADR 0001 pen-tablet feedback
   * loop, spike 0 — docs/04_DESIGN_PDF_ANNOTATION_FEEDBACK_LOOP.md). Fire and
   * forget: a failed POST never blocks the client-side mark (it already
   * rendered via echoMarks) and is surfaced via console.warn, not swallowed.
   * Backend spike 0 is POST+GET only (no update endpoint yet), so this fires
   * once at creation; later text edits stay client-side-only until a future
   * spike adds PATCH. The category label is used as the initial comment when
   * the mark has none yet — the backend requires non-empty text, and the
   * category is a real fact about the mark, not invented prose.
   */
  private postToBackend(ann: Annotation): void {
    const region: Record<string, number> = ann.region
      ? {
          x0: ann.region.x0,
          y0: ann.region.y0,
          x1: ann.region.x1,
          y1: ann.region.y1,
        }
      : { pdfX: ann.anchor.pdfX, pdfY: ann.anchor.pdfY };
    postAnnotation({
      page: ann.page,
      doc_type: this.currentDocType,
      kind: "text_comment",
      payload: {
        text: ann.text.trim() || CATEGORY_LABELS[ann.category],
        category: ann.category,
        tool: ann.tool,
      },
      region,
    }).catch((err) => {
      console.warn("[pdf-viewer] postAnnotation failed:", err);
    });
  }

  private echoMarks(): void {
    this.api.setMarks(this.store.list().map((a) => this.toMark(a)));
  }

  private toMark(a: Annotation): Mark {
    const mark: Mark = {
      id: a.id,
      page: a.page,
      tool: TOOL_ANN_TO_L1[a.tool] ?? "highlight",
      label: a.text || undefined,
    };
    if (a.region) {
      mark.rect = {
        x: a.region.x0,
        y: a.region.y0,
        w: a.region.x1 - a.region.x0,
        h: a.region.y1 - a.region.y0,
      };
    }
    if (a.path) {
      mark.path = a.path.map(([x, y]) => ({ x, y }));
    }
    return mark;
  }
}
