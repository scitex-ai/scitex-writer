/**
 * Icon-bar insert panel — Cite / Fig / Table / History tabs between the
 * Monaco editor and the PDF preview. Clicking an entry inserts LaTeX at
 * the cursor in Monaco.
 */

import { listFigures, listTables, resourceUrl } from "./api";
import type { MediaEntry } from "./api";
import { CitationsPanel } from "./citations-panel";

export type InsertPaneId = "cite" | "fig" | "table" | "collab" | "history";

interface PanelOptions {
  bar: HTMLElement;
  panel: HTMLElement;
  getDocType: () => string;
  insertAtCursor: (snippet: string) => void;
}

export class InsertPanel {
  private opts: PanelOptions;
  private active: InsertPaneId | null = null;
  private citationsPanel: CitationsPanel | null = null;
  private figCache: Record<string, MediaEntry[]> = {};
  private tableCache: Record<string, MediaEntry[]> = {};

  constructor(opts: PanelOptions) {
    this.opts = opts;
    this.wireBar();
    this.close();
  }

  private wireBar(): void {
    this.opts.bar
      .querySelectorAll<HTMLElement>("[data-pane]")
      .forEach((btn) => {
        btn.addEventListener("click", () => {
          const pane = btn.dataset.pane as InsertPaneId;
          if (this.active === pane) this.close();
          else this.open(pane);
        });
      });
  }

  close(): void {
    this.active = null;
    this.opts.panel.classList.add("u-hidden");
    this.opts.bar
      .querySelectorAll<HTMLElement>("[data-pane]")
      .forEach((b) => b.classList.remove("active"));
  }

  open(pane: InsertPaneId): void {
    this.active = pane;
    this.opts.panel.classList.remove("u-hidden");
    this.opts.bar
      .querySelectorAll<HTMLElement>("[data-pane]")
      .forEach((b) => b.classList.toggle("active", b.dataset.pane === pane));
    switch (pane) {
      case "cite":
        void this.renderCite();
        break;
      case "fig":
        void this.renderFig();
        break;
      case "table":
        void this.renderTable();
        break;
      case "collab":
        this.renderCollab();
        break;
      case "history":
        this.renderHistory();
        break;
    }
  }

  invalidate(docType: string): void {
    delete this.figCache[docType];
    delete this.tableCache[docType];
  }

  private async renderCite(): Promise<void> {
    this.opts.panel.innerHTML = `<div class="insert-panel-body" id="citations-panel-mount"></div>`;
    const mount = this.opts.panel.querySelector<HTMLElement>(
      "#citations-panel-mount",
    );
    if (!mount) return;
    if (!this.citationsPanel) {
      this.citationsPanel = new CitationsPanel({ container: mount });
    } else {
      // Re-attach to a fresh container (panel was rebuilt).
      (this.citationsPanel as unknown as { el: HTMLElement }).el = mount;
    }
    await this.citationsPanel.render();
  }

  private async renderFig(): Promise<void> {
    const docType = this.opts.getDocType();
    this.setLoading("Figures");
    if (!this.figCache[docType]) {
      try {
        this.figCache[docType] = (await listFigures(docType)).figures;
      } catch (err) {
        this.setError(`Failed to load figures: ${err}`);
        return;
      }
    }
    this.renderList(
      "Figures",
      this.figCache[docType].map((figure) => ({
        label: figure.name,
        sub: figure.label ? `\\ref{${figure.label}}` : "",
        insert: figure.insert,
        thumbnail_url: figure.thumbnail_url,
        media_ext: figure.media_ext,
      })),
    );
  }

  private async renderTable(): Promise<void> {
    const docType = this.opts.getDocType();
    this.setLoading("Tables");
    if (!this.tableCache[docType]) {
      try {
        this.tableCache[docType] = (await listTables(docType)).tables;
      } catch (err) {
        this.setError(`Failed to load tables: ${err}`);
        return;
      }
    }
    this.renderList(
      "Tables",
      this.tableCache[docType].map((table) => ({
        label: table.name,
        sub: table.label ? `\\ref{${table.label}}` : "",
        insert: table.insert,
        thumbnail_url: table.thumbnail_url,
        media_ext: table.media_ext,
      })),
    );
  }

  private renderHistory(): void {
    this.opts.panel.innerHTML = `
      <div class="insert-panel-header">Version history</div>
      <div class="insert-panel-body">
        <p class="insert-panel-empty">Git history integration lands in a later PR.</p>
      </div>
    `;
  }

  private renderCollab(): void {
    this.opts.panel.innerHTML = `
      <div class="insert-panel-header">Real-time collaboration</div>
      <div class="insert-panel-body insert-panel-info">
        <p><strong>Not supported in this local instance.</strong></p>
        <p>
          Collaboration (operational transforms, presence, inline comments)
          requires a cloud backend with auth, WebSocket consumers, and a
          shared project store.
        </p>
        <p>
          Two ways to use it:
        </p>
        <ul>
          <li>
            Public hosted instance &mdash;
            <a href="https://scitex.ai/apps/writer/" target="_blank" rel="noreferrer">
              scitex.ai/apps/writer/
            </a>
          </li>
          <li>
            Self-host &mdash; the
            <a href="https://github.com/ywatanabe1989/scitex-cloud" target="_blank" rel="noreferrer">
              scitex-cloud
            </a>
            backend is AGPL-3.0 and runnable on your own infrastructure.
          </li>
        </ul>
      </div>
    `;
  }

  private setLoading(title: string): void {
    this.opts.panel.innerHTML = `
      <div class="insert-panel-header">${title}</div>
      <div class="insert-panel-body"><p class="insert-panel-empty">Loading…</p></div>
    `;
  }

  private setError(msg: string): void {
    this.opts.panel.innerHTML = `
      <div class="insert-panel-header">Error</div>
      <div class="insert-panel-body"><p class="insert-panel-error">${msg}</p></div>
    `;
  }

  private renderList(
    title: string,
    items: Array<{
      label: string;
      sub: string;
      insert: string;
      thumbnail_url?: string | null;
      media_ext?: string | null;
    }>,
  ): void {
    if (items.length === 0) {
      this.opts.panel.innerHTML = `
        <div class="insert-panel-header">${title}</div>
        <div class="insert-panel-body"><p class="insert-panel-empty">(none)</p></div>
      `;
      return;
    }
    const anyThumbnail = items.some((i) => i.thumbnail_url);
    const listHtml = items
      .map((item, index) => {
        const thumb = item.thumbnail_url
          ? `<img class="insert-item-thumb" src="${escapeAttr(resourceUrl(item.thumbnail_url.replace(/^\//, "")))}" alt="" loading="lazy" />`
          : anyThumbnail
            ? `<div class="insert-item-thumb insert-item-thumb--empty">${escapeHtml((item.media_ext || "").toUpperCase().replace(".", ""))}</div>`
            : "";
        return `
        <div class="insert-item ${anyThumbnail ? "insert-item--thumb" : ""}"
             data-index="${index}"
             data-insert="${escapeAttr(item.insert)}">
          ${thumb}
          <div class="insert-item-meta">
            <div class="insert-item-label">${escapeHtml(item.label)}</div>
            <div class="insert-item-sub">${escapeHtml(item.sub)}</div>
            <div class="insert-item-snippet">${escapeHtml(item.insert)}</div>
          </div>
        </div>`;
      })
      .join("");
    this.opts.panel.innerHTML = `
      <div class="insert-panel-header">${title}<span class="insert-count">${items.length}</span></div>
      <div class="insert-panel-body insert-panel-body--${anyThumbnail ? "grid" : "list"}">${listHtml}</div>
    `;
    this.opts.panel
      .querySelectorAll<HTMLElement>(".insert-item")
      .forEach((el) => {
        el.addEventListener("click", () => {
          const snippet = el.dataset.insert || "";
          if (snippet) this.opts.insertAtCursor(snippet);
        });
      });
  }
}

function escapeHtml(text: string): string {
  return text
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;");
}

function escapeAttr(text: string): string {
  return escapeHtml(text).replace(/'/g, "&#39;");
}
