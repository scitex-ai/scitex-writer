/**
 * Citations panel — rich scholar-aware cite browser.
 *
 * Two sub-tabs:
 *   • **In this manuscript** — entries from 00_shared/bib_files/*.bib
 *   • **Library** — all papers in the user's scholar library
 *
 * Interactions:
 *   • Ctrl/Cmd-click toggles card selection (multi-select).
 *   • Drag a card into Monaco to insert `\cite{key}` (joins selected
 *     keys with commas if the dragged card is part of the selection).
 *   • Click **Enrich bibliography** to shell out to scitex-scholar.
 *   • In the Library tab, click **+** on a card to append a derived
 *     BibTeX entry to bibliography.bib.
 *
 * Port of scitex-cloud's `_citations-panel/` modules, condensed into
 * one file because this panel is the only consumer and splitting adds
 * no value for us.
 */
import {
  type BibEntry,
  bibEntries,
  scholarAddToManuscript,
  scholarEnrich,
  scholarLibrary,
  type ScholarLibraryEntry,
  scholarStatus,
  type ScholarStatus,
} from "./api";
import { invalidateCitationCache } from "./cite-completion";

type CiteTab = "manuscript" | "library";

interface PanelOptions {
  container: HTMLElement;
  onSelectionChange?: (keys: string[]) => void;
}

export class CitationsPanel {
  private el: HTMLElement;
  private activeTab: CiteTab = "manuscript";
  private manuscriptEntries: BibEntry[] | null = null;
  private libraryEntries: ScholarLibraryEntry[] | null = null;
  private scholarState: ScholarStatus | null = null;
  private selected: Set<string> = new Set();
  private onSelectionChange: ((keys: string[]) => void) | undefined;
  private searchTerm = "";

  constructor(opts: PanelOptions) {
    this.el = opts.container;
    this.onSelectionChange = opts.onSelectionChange;
  }

  async render(): Promise<void> {
    // Fire scholar status lookup non-blocking; render shell immediately.
    this.el.innerHTML = this.shellHtml();
    this.wireTabs();
    this.wireSearch();
    this.wireEnrichButton();

    if (!this.scholarState) {
      this.scholarState = await scholarStatus().catch(() => null);
      this.updateEnrichHint();
    }
    await this.renderActiveTab();
  }

  getSelectedKeys(): string[] {
    return Array.from(this.selected);
  }

  clearSelection(): void {
    this.selected.clear();
    this.el
      .querySelectorAll(".citation-card.selected")
      .forEach((c) => c.classList.remove("selected"));
    this.notifySelectionChange();
  }

  private shellHtml(): string {
    return `
      <div class="citations-panel">
        <div class="citations-tabs">
          <button class="citations-tab active" data-tab="manuscript">In this manuscript</button>
          <button class="citations-tab" data-tab="library">Library</button>
        </div>
        <div class="citations-controls">
          <input class="citations-search" type="search"
                 placeholder="Filter by title / key / DOI…" />
          <button class="btn btn-primary btn-sm citations-enrich"
                  title="Enrich bibliography with scitex-scholar">
            <i class="fas fa-magic"></i><span>Enrich</span>
          </button>
        </div>
        <div class="citations-enrich-hint u-hidden"></div>
        <div class="citations-list"><p class="insert-panel-empty">Loading…</p></div>
      </div>
    `;
  }

  private wireTabs(): void {
    this.el.querySelectorAll<HTMLElement>(".citations-tab").forEach((btn) => {
      btn.addEventListener("click", () => {
        const tab = btn.dataset.tab as CiteTab;
        if (tab === this.activeTab) return;
        this.activeTab = tab;
        this.el
          .querySelectorAll<HTMLElement>(".citations-tab")
          .forEach((b) => b.classList.toggle("active", b.dataset.tab === tab));
        void this.renderActiveTab();
      });
    });
  }

  private wireSearch(): void {
    const input = this.el.querySelector<HTMLInputElement>(".citations-search");
    if (!input) return;
    input.addEventListener("input", () => {
      this.searchTerm = input.value.trim().toLowerCase();
      this.redrawList();
    });
  }

  private wireEnrichButton(): void {
    const btn = this.el.querySelector<HTMLButtonElement>(".citations-enrich");
    if (!btn) return;
    btn.addEventListener("click", async () => {
      if (!this.scholarState?.scholar_cli_on_path) {
        this.showEnrichHint(
          "scitex-scholar is not installed. Run <code>pip install scitex-scholar</code> (or <code>uv pip install 'scitex-writer[all]'</code>), then click again.",
        );
        return;
      }
      btn.disabled = true;
      btn.innerHTML = `<i class="fas fa-spinner fa-spin"></i> Enriching…`;
      try {
        const res = await scholarEnrich();
        if (res.ok) {
          // Invalidate caches; re-fetch.
          this.manuscriptEntries = null;
          this.libraryEntries = null;
          invalidateCitationCache();
          await this.renderActiveTab();
          this.showEnrichHint("Enrichment finished.", "success");
        } else {
          this.showEnrichHint(
            `Enrichment failed. <details><summary>Log</summary><pre>${escapeHtml(res.log)}</pre></details>`,
            "error",
          );
        }
      } finally {
        btn.disabled = false;
        btn.innerHTML = `<i class="fas fa-magic"></i> Enrich`;
      }
    });
  }

  private updateEnrichHint(): void {
    if (!this.scholarState) return;
    if (!this.scholarState.scholar_cli_on_path) {
      this.showEnrichHint(
        "Optional: install <code>scitex-scholar</code> to enrich citations with abstracts, DOIs, impact factors, and OA links.",
        "info",
      );
    }
  }

  private showEnrichHint(
    html: string,
    kind: "info" | "success" | "error" = "info",
  ): void {
    const hint = this.el.querySelector<HTMLElement>(".citations-enrich-hint");
    if (!hint) return;
    hint.className = `citations-enrich-hint citations-enrich-hint--${kind}`;
    hint.innerHTML = html;
  }

  private async renderActiveTab(): Promise<void> {
    if (this.activeTab === "manuscript") {
      if (!this.manuscriptEntries) {
        try {
          this.manuscriptEntries = (await bibEntries()).entries;
        } catch (err) {
          this.setListError(String(err));
          return;
        }
      }
    } else {
      if (!this.libraryEntries) {
        try {
          const res = await scholarLibrary(500, 0);
          this.libraryEntries = res.entries;
          if (res.reason === "no_library") {
            this.libraryEntries = [];
          }
        } catch (err) {
          this.setListError(String(err));
          return;
        }
      }
    }
    this.redrawList();
  }

  private redrawList(): void {
    const list = this.el.querySelector<HTMLElement>(".citations-list");
    if (!list) return;
    const entries =
      this.activeTab === "manuscript"
        ? this.filteredManuscript()
        : this.filteredLibrary();
    if (entries.length === 0) {
      list.innerHTML = `<p class="insert-panel-empty">${
        this.activeTab === "library" && !this.scholarState?.library_root
          ? "No scholar library linked. Run the Enrich button or <code>scitex scholar link-project-tree &lt;project&gt;</code>."
          : "(no matches)"
      }</p>`;
      return;
    }
    list.innerHTML = entries.map((e) => this.cardHtml(e)).join("");
    this.wireCardEvents(list);
  }

  private filteredManuscript(): BibEntry[] {
    const all = this.manuscriptEntries ?? [];
    if (!this.searchTerm) return all;
    const q = this.searchTerm;
    return all.filter(
      (e) =>
        e.citation_key.toLowerCase().includes(q) ||
        (e.title || "").toLowerCase().includes(q) ||
        (e.doi || "").toLowerCase().includes(q) ||
        (e.scholar?.title || "").toLowerCase().includes(q),
    );
  }

  private filteredLibrary(): ScholarLibraryEntry[] {
    const all = this.libraryEntries ?? [];
    if (!this.searchTerm) return all;
    const q = this.searchTerm;
    return all.filter(
      (e) =>
        (e.title || "").toLowerCase().includes(q) ||
        (e.doi || "").toLowerCase().includes(q) ||
        (e.paper_id || "").toLowerCase().includes(q),
    );
  }

  private cardHtml(entry: BibEntry | ScholarLibraryEntry): string {
    if ("citation_key" in entry) return this.manuscriptCardHtml(entry);
    return this.libraryCardHtml(entry);
  }

  private manuscriptCardHtml(e: BibEntry): string {
    const s = e.scholar;
    const title = s?.title || e.title || e.citation_key;
    const authors = s?.authors?.slice(0, 3).join(", ") || "";
    const year = s?.year ?? "";
    const venue = s?.short_journal || s?.journal || "";
    const oa = s?.is_open_access
      ? `<span class="badge badge-oa" title="Open access">OA</span>`
      : "";
    const ifBadge =
      s?.impact_factor != null
        ? `<span class="badge badge-if" title="Impact factor">IF ${Number(s.impact_factor).toFixed(1)}</span>`
        : "";
    const citesBadge =
      s?.citation_count != null
        ? `<span class="badge badge-cites" title="Times cited">${s.citation_count}×</span>`
        : "";
    const isSelected = this.selected.has(e.citation_key);
    return `
      <div class="citation-card ${isSelected ? "selected" : ""}"
           draggable="true"
           data-kind="manuscript"
           data-citation-key="${escapeAttr(e.citation_key)}">
        <div class="citation-card-head">
          <div class="citation-key"><code>${escapeHtml(e.citation_key)}</code></div>
          <div class="citation-badges">${oa}${ifBadge}${citesBadge}</div>
        </div>
        <div class="citation-title">${escapeHtml(title)}</div>
        <div class="citation-sub">
          ${escapeHtml(authors)}${authors && (year || venue) ? " · " : ""}${escapeHtml(String(year))}${year && venue ? " · " : ""}${escapeHtml(venue)}
        </div>
        ${s?.abstract ? `<div class="citation-abstract">${escapeHtml(s.abstract)}</div>` : ""}
      </div>
    `;
  }

  private libraryCardHtml(e: ScholarLibraryEntry): string {
    return `
      <div class="citation-card citation-card--library"
           data-kind="library"
           data-paper-id="${escapeAttr(e.paper_id)}"
           ${e.doi ? `data-doi="${escapeAttr(e.doi)}"` : ""}>
        <div class="citation-card-head">
          <div class="citation-title">${escapeHtml(e.title || "(untitled)")}</div>
          <button class="btn btn-icon btn-sm citation-add-btn" title="Add to manuscript">
            <i class="fas fa-plus"></i>
          </button>
        </div>
        <div class="citation-sub">
          ${escapeHtml(String(e.year ?? ""))}${e.year && e.venue ? " · " : ""}${escapeHtml(e.venue || "")}${e.doi ? ` · <code>${escapeHtml(e.doi)}</code>` : ""}
        </div>
      </div>
    `;
  }

  private wireCardEvents(list: HTMLElement): void {
    list.querySelectorAll<HTMLElement>(".citation-card").forEach((card) => {
      const kind = card.dataset.kind as "manuscript" | "library";
      if (kind === "manuscript") {
        card.addEventListener("click", (e) =>
          this.handleManuscriptClick(card, e as MouseEvent),
        );
        card.addEventListener("dragstart", (e) =>
          this.handleDragStart(card, e as DragEvent),
        );
        card.addEventListener("dragend", () =>
          card.classList.remove("dragging"),
        );
      } else {
        const btn = card.querySelector<HTMLButtonElement>(".citation-add-btn");
        btn?.addEventListener("click", (e) => {
          e.stopPropagation();
          void this.handleLibraryAdd(card, btn);
        });
      }
    });
  }

  private handleManuscriptClick(card: HTMLElement, e: MouseEvent): void {
    const key = card.dataset.citationKey;
    if (!key) return;
    if (e.ctrlKey || e.metaKey) {
      if (this.selected.has(key)) {
        this.selected.delete(key);
        card.classList.remove("selected");
      } else {
        this.selected.add(key);
        card.classList.add("selected");
      }
      this.notifySelectionChange();
    } else {
      // Plain click without modifier = single select (replace set).
      this.el
        .querySelectorAll(".citation-card.selected")
        .forEach((c) => c.classList.remove("selected"));
      this.selected.clear();
      this.selected.add(key);
      card.classList.add("selected");
      this.notifySelectionChange();
    }
  }

  private handleDragStart(card: HTMLElement, e: DragEvent): void {
    const key = card.dataset.citationKey;
    if (!key || !e.dataTransfer) return;
    const payload =
      this.selected.has(key) && this.selected.size > 1
        ? `\\cite{${Array.from(this.selected).join(",")}}`
        : `\\cite{${key}}`;
    // Custom MIME lets Monaco-drop filter by source; text/plain kept as a
    // fallback so dropping into other text fields still works.
    e.dataTransfer.setData("application/x-scitex-cite", payload);
    e.dataTransfer.setData("text/plain", payload);
    e.dataTransfer.effectAllowed = "copy";
    card.classList.add("dragging");
  }

  private async handleLibraryAdd(
    card: HTMLElement,
    btn: HTMLButtonElement,
  ): Promise<void> {
    const paperId = card.dataset.paperId;
    if (!paperId) return;
    const original = btn.innerHTML;
    btn.disabled = true;
    btn.innerHTML = `<i class="fas fa-spinner fa-spin"></i>`;
    try {
      const res = await scholarAddToManuscript(paperId);
      if (res.ok) {
        btn.innerHTML = `<i class="fas fa-check"></i>`;
        this.manuscriptEntries = null;
        invalidateCitationCache();
      } else {
        btn.innerHTML = `<i class="fas fa-exclamation-triangle"></i>`;
        console.error("add-to-manuscript failed:", res.error);
      }
    } finally {
      setTimeout(() => {
        btn.disabled = false;
        btn.innerHTML = original;
      }, 1500);
    }
  }

  private setListError(msg: string): void {
    const list = this.el.querySelector<HTMLElement>(".citations-list");
    if (list)
      list.innerHTML = `<p class="insert-panel-error">${escapeHtml(msg)}</p>`;
  }

  private notifySelectionChange(): void {
    this.onSelectionChange?.(Array.from(this.selected));
  }
}

function escapeHtml(text: string): string {
  return String(text)
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;");
}

function escapeAttr(text: string): string {
  return escapeHtml(text).replace(/'/g, "&#39;");
}
