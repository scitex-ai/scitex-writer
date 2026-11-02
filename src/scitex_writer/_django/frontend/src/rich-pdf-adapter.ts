/** Writer owns URL/auth and its annotation-record → rich PDF translations. */
import {
  createPdfViewer,
  type Mark,
  type PdfSource,
  type PdfViewerApi,
  type PdfViewerOptions,
} from "@scitex/sdk/ui/pdf-viewer";
import {
  createRichPdfViewer,
  type PdfComment,
  type PdfOverlay,
  type PdfTarget,
} from "@scitex/live-paper/pdf-provider";
import "@scitex/live-paper/pdf-provider.css";
import { apiGet, postAnnotation } from "./api";

interface StoredAnnotation {
  annotation_id: string;
  page: number;
  payload: { text?: string };
  region?: Record<string, number>;
  source_ref?: { locked?: boolean; readonly?: boolean };
  author?: string;
}
export interface WriterPdfAdapterOptions {
  getDocType(): string;
  canMutate(action: string): boolean;
  onPortError?(error: unknown): void;
}
function bbox(record: StoredAnnotation): number[] | null {
  const region = record.region;
  if (!region) return null;
  if (["x0", "y0", "x1", "y1"].every((key) => Number.isFinite(region[key])))
    return [region.x0, region.y0, region.x1, region.y1];
  if (Number.isFinite(region.pdfX) && Number.isFinite(region.pdfY))
    return [region.pdfX - 8, region.pdfY - 8, region.pdfX + 8, region.pdfY + 8];
  return null;
}
export function annotationOverlay(record: StoredAnnotation): PdfOverlay | null {
  const box = bbox(record);
  return box
    ? {
        id: `stored:${record.annotation_id}`,
        page: record.page,
        bbox: box,
        label: record.payload.text || "Annotation",
        readonly:
          record.source_ref?.locked === true ||
          record.source_ref?.readonly === true,
      }
    : null;
}
function markOverlay(mark: Mark): PdfOverlay | null {
  const rect = mark.rect;
  const points = mark.path;
  const box = rect
    ? [rect.x, rect.y, rect.x + rect.w, rect.y + rect.h]
    : points?.length
      ? [
          Math.min(...points.map((p) => p.x)),
          Math.min(...points.map((p) => p.y)),
          Math.max(...points.map((p) => p.x)),
          Math.max(...points.map((p) => p.y)),
        ]
      : null;
  return box
    ? {
        id: mark.id,
        page: mark.page,
        bbox: box,
        label: mark.label || "Annotation",
        readonly: mark.meta?.readonly === true || mark.meta?.locked === true,
      }
    : null;
}

/** Preserve the existing SDK API while all loads and rich UI use the provider. */
export function createWriterPdfViewer(
  options: PdfViewerOptions,
  adapter: WriterPdfAdapterOptions,
): PdfViewerApi {
  const { container, src, ...rendererOptions } = options;
  let marks: Mark[] = [];
  let records: StoredAnnotation[] = [];
  let recordSource = "";
  let recordLoad: Promise<StoredAnnotation[]> | null = null;
  const overlayFeed = () =>
    [...records.map(annotationOverlay), ...marks.map(markOverlay)].filter(
      (item): item is PdfOverlay => item !== null,
    );
  const commentFeed = (): PdfComment[] => [
    ...records
      .filter((item) => item.payload.text)
      .map((item) => ({
        id: item.annotation_id,
        body: item.payload.text!,
        author: item.author,
        target: { overlayId: `stored:${item.annotation_id}` },
      })),
    ...marks
      .filter((item) => item.label)
      .map((item) => ({
        id: `local:${item.id}`,
        body: item.label!,
        target: { overlayId: item.id },
      })),
  ];
  async function readRecords(documentId: string): Promise<StoredAnnotation[]> {
    if (recordSource !== documentId || !recordLoad) {
      recordSource = documentId;
      records = [];
      const docType = adapter.getDocType();
      recordLoad = apiGet<{ annotations: StoredAnnotation[] }>(
        `api/annotations?doc_type=${encodeURIComponent(docType)}`,
      ).then((response) => response.annotations);
    }
    const pending = recordLoad;
    try {
      const result = await pending;
      if (recordSource === documentId && recordLoad === pending)
        records = result;
      return result;
    } catch (error) {
      if (recordSource === documentId && recordLoad === pending)
        recordLoad = null;
      throw error;
    }
  }
  const rich = createRichPdfViewer({
    container,
    createPdfViewer,
    rendererOptions: { ...rendererOptions, textLayer: true, linkLayer: true },
    ports: {
      documents: {
        resolve(key) {
          if (
            !(
              typeof key === "string" ||
              key instanceof URL ||
              key instanceof ArrayBuffer
            )
          )
            throw new TypeError("Writer PDF source required");
          return {
            id:
              typeof key === "string"
                ? key
                : key instanceof URL
                  ? key.href
                  : "buffer",
            src: key,
          };
        },
      },
      overlays: {
        async list(document) {
          await readRecords(document.id);
          return overlayFeed();
        },
      },
      comments: {
        async list(document) {
          await readRecords(document.id);
          return commentFeed();
        },
        async create(_document, target: PdfTarget, body) {
          const overlay = overlayFeed().find(
            (item) => item.id === target.overlayId,
          );
          const page = overlay?.page ?? target.page;
          const box = overlay?.bbox ?? target.bbox;
          if (!page || !box)
            throw new Error("A PDF region is required for a comment");
          const response = await postAnnotation({
            page,
            doc_type: adapter.getDocType(),
            kind: "text_comment",
            payload: { text: body },
            region: { x0: box[0], y0: box[1], x1: box[2], y1: box[3] },
          });
          if (!response.ok || !response.annotation_id)
            throw new Error("Writer annotation was not saved");
          records = [
            ...records,
            {
              annotation_id: response.annotation_id,
              page,
              payload: { text: body },
              region: { x0: box[0], y0: box[1], x1: box[2], y1: box[3] },
            },
          ];
          return { id: response.annotation_id, body, target };
        },
      },
      policy: { canMutate: ({ action }) => adapter.canMutate(action) },
      events: {
        emit(event) {
          if (event.type === "port-error" || event.type === "mutation-error")
            adapter.onPortError?.(event.error);
        },
      },
    },
  });
  const api: PdfViewerApi = {
    load: async (source: PdfSource) => {
      await rich.load(source);
    },
    getCoords: (x, y) => rich.renderer.getCoords(x, y),
    setTool: (tool) => rich.renderer.setTool(tool),
    setInteractive: (enabled) => rich.renderer.setInteractive(enabled),
    setScale: (scale) => rich.renderer.setScale(scale),
    getScale: () => rich.renderer.getScale(),
    fitWidth: () => rich.renderer.fitWidth(),
    scrollToPage: (page) => rich.renderer.scrollToPage(page),
    setMarks(values) {
      marks = [...values];
      rich.renderer.setMarks(values);
      rich.setOverlays(overlayFeed());
      rich.setComments(commentFeed());
    },
    getMarks: () => rich.renderer.getMarks(),
    setPalette: (palette) => rich.renderer.setPalette(palette),
    destroy: () => rich.destroy(),
  };
  if (src !== undefined) void api.load(src);
  return api;
}
