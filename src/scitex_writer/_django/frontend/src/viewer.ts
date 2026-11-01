/**
 * Viewer entry point — read-only live-paper view.
 * Claims list + PDF preview + click-through DAG. No editing.
 * Bundled by Vite to `static/writer/assets/viewer.js`.
 */

import {
  type ClaimRow,
  loadClaims,
  renderClaimDetails,
  renderClaimsList,
  renderDagFor,
} from "./claims-list";
import { PDFViewer } from "./pdf-viewer";
import { wireHostThemeToggle } from "./host-theme-fallback";
import { mountPdfMenu } from "./pdf-menu";

declare global {
  interface Window {
    mermaid?: {
      initialize: (config: Record<string, unknown>) => void;
      render: (
        id: string,
        code: string,
      ) => Promise<{ svg: string; bindFunctions?: (el: Element) => void }>;
    };
  }
}

async function bootstrap(): Promise<void> {
  const root = document.querySelector<HTMLElement>(".writer-app--viewer");
  if (!root) return;

  // Same dead-row fallback as the editor (hub header is injected here too).
  wireHostThemeToggle();

  window.mermaid?.initialize({ startOnLoad: false, theme: "dark" });

  const pdfContainer = root.querySelector<HTMLElement>("#pdf-container");
  const pdf = pdfContainer ? new PDFViewer({ container: pdfContainer }) : null;
  pdf?.renderPlaceholder("No PDF compiled yet.");

  const docSelect = root.querySelector<HTMLSelectElement>("#doc-type-select");
  const initialDocType = docSelect?.value || "manuscript";
  await pdf?.load(initialDocType);

  docSelect?.addEventListener("change", async () => {
    await pdf?.load(docSelect.value);
  });

  wirePdfControls(root, pdf);
  mountPdfMenu(root);
  wireTabs(root);

  const claimsList = root.querySelector<HTMLElement>("#viewer-claims-list");
  const badge = root.querySelector<HTMLElement>("#claims-count-badge");
  const popup = root.querySelector<HTMLElement>("#viewer-popup");
  const popupBody = root.querySelector<HTMLElement>("#viewer-popup-body");
  const popupTitle = root.querySelector<HTMLElement>("#viewer-popup-title");
  const popupClose = root.querySelector<HTMLElement>("#viewer-popup-close");
  const dagContainer = root.querySelector<HTMLElement>("#dag-container");

  popupClose?.addEventListener("click", () => popup?.classList.add("u-hidden"));

  const claims = await loadClaims();
  if (badge)
    badge.textContent = `${claims.length} claim${claims.length === 1 ? "" : "s"}`;

  if (!claimsList) return;
  renderClaimsList(claimsList, claims, async (claim: ClaimRow) => {
    if (popup && popupTitle && popupBody) {
      popupTitle.textContent = claim.claim_id;
      popupBody.innerHTML = renderClaimDetails(claim);
      popup.classList.remove("u-hidden");
    }
    if (dagContainer) await renderDagFor(claim, dagContainer);
  });
}

function wirePdfControls(root: HTMLElement, pdf: PDFViewer | null): void {
  root
    .querySelector<HTMLElement>("#btn-pdf-zoom-in")
    ?.addEventListener("click", () => pdf?.setZoom(0.1));
  root
    .querySelector<HTMLElement>("#btn-pdf-zoom-out")
    ?.addEventListener("click", () => pdf?.setZoom(-0.1));
  root
    .querySelector<HTMLElement>("#btn-pdf-fit")
    ?.addEventListener("click", () => pdf?.setFitWidth());
}

function wireTabs(root: HTMLElement): void {
  root.querySelectorAll<HTMLElement>(".preview-tab").forEach((tab) => {
    tab.addEventListener("click", () => {
      const view = tab.dataset.view;
      root
        .querySelectorAll<HTMLElement>(".preview-tab")
        .forEach((t) => t.classList.toggle("active", t === tab));
      root
        .querySelectorAll<HTMLElement>(".preview-view")
        .forEach((v) => v.classList.toggle("active", v.id === `${view}-view`));
    });
  });
}

void bootstrap();
