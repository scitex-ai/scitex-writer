/**
 * Details panel — collapsible right-hand column matching scitex.ai/apps/writer.
 * Sections: Compilation (Preview/Full status) · Import / Export · Project Info ·
 * Shortcuts. The right pane carries Writer context only — the Overleaf and
 * Prism integrations are folded into a single "Import / Export" section (mirroring
 * the Scholar library Import/Export pattern) rather than permanently occupying
 * the pane as top-level vendor entries. Collapsed/expanded state stored in localStorage.
 */

import { manuscriptHints, projectInfo } from "./api";
import type { Hint, HintsFeed, ProjectInfo } from "./api";

type SectionId =
  | "hints"
  | "compile-preview"
  | "compile-full"
  | "import-export"
  | "project"
  | "shortcuts";

interface SectionDef {
  id: SectionId;
  title: string;
  icon: string;
  wip?: boolean;
  render: () => string;
}

const STORAGE_KEY = "writer-details-open";

/** Optional navigation hooks so a hint row can jump the editor / PDF to the
 * location the hint points at. Both are optional: when a host wires neither
 * (e.g. the read-only viewer), hint rows fall back to plain, non-clickable
 * text — exactly the pre-anchor behaviour. */
export interface DetailsPanelOptions {
  /** Jump the editor to a source file+line (undefined \\ref target, unverified
   * claim, ...). Wired to the Monaco reveal path in index.ts. */
  onJumpToLocation?: (file: string, line: number) => void;
  /** Jump the PDF viewer to a page (1-based). Wired where a PDF viewer exists. */
  onJumpToPage?: (page: number) => void;
}

export class DetailsPanel {
  private container: HTMLElement;
  private open: Set<SectionId>;
  private project: ProjectInfo | null = null;
  private compileState: { preview: string; full: string } = {
    preview: "idle",
    full: "idle",
  };
  private hints: HintsFeed | null = null;
  private onJumpToLocation: ((file: string, line: number) => void) | undefined;
  private onJumpToPage: ((page: number) => void) | undefined;

  constructor(container: HTMLElement, options: DetailsPanelOptions = {}) {
    this.container = container;
    this.onJumpToLocation = options.onJumpToLocation;
    this.onJumpToPage = options.onJumpToPage;
    this.open = this.loadOpenState();
    this.render();
    void this.loadProject();
    void this.refreshHints();
  }

  setCompileStatus(mode: "preview" | "full", status: string): void {
    this.compileState[mode] = status;
    this.render();
  }

  /** Re-fetch the manuscript-hints feed (call after each compile — the feed is
   * rewritten by the "Manuscript Hints" compile stage). Best-effort: a fetch
   * failure leaves the pane showing "no hints", never an error. */
  async refreshHints(): Promise<void> {
    try {
      this.hints = await manuscriptHints();
    } catch (err) {
      console.warn("[details] hints fetch failed", err);
      this.hints = null;
    }
    this.render();
  }

  openSection(id: SectionId): void {
    this.open.add(id);
    this.saveOpenState();
    this.render();
    this.container
      .querySelector<HTMLElement>(`[data-id="${id}"]`)
      ?.scrollIntoView({ behavior: "smooth", block: "start" });
  }

  private async loadProject(): Promise<void> {
    try {
      this.project = await projectInfo();
      this.render();
    } catch (err) {
      console.warn("[details] projectInfo failed", err);
    }
  }

  private sections(): SectionDef[] {
    const dot = (state: string) => {
      const colors: Record<string, string> = {
        idle: "#888",
        compiling: "var(--warning, #d97706)",
        ok: "var(--success, #16a34a)",
        error: "var(--danger, #dc2626)",
      };
      return `<span class="details-dot" style="background:${colors[state] || colors.idle}" title="${state}"></span>`;
    };

    return [
      {
        id: "hints",
        title: "Hints",
        icon: "fa-bell",
        render: () => this.renderHints(),
      },
      {
        id: "compile-preview",
        title: "Compilation — Preview",
        icon: "fa-circle-dot",
        render: () => `
          <div class="details-row">
            <span>Status</span><span>${dot(this.compileState.preview)} ${this.compileState.preview}</span>
          </div>
          <p class="details-hint">Compiles the current section only. Fast iteration.</p>
        `,
      },
      {
        id: "compile-full",
        title: "Compilation — Full",
        icon: "fa-file-pdf",
        render: () => `
          <div class="details-row">
            <span>Status</span><span>${dot(this.compileState.full)} ${this.compileState.full}</span>
          </div>
          <p class="details-hint">Compiles the full manuscript (all sections + bibliography).</p>
        `,
      },
      {
        id: "import-export",
        title: "Import / Export",
        icon: "fa-right-left",
        render: () => `
          <div class="details-iec">
            <div class="details-iec-subhead"><i class="fas fa-cloud-arrow-up"></i> Overleaf <span class="details-wip-badge">WIP</span></div>
            <p class="details-hint">
              Overleaf ZIP import / export is on the roadmap.
              Meanwhile: compile locally and upload the PDF to Overleaf manually.
            </p>
            <div class="details-iec-subhead"><i class="fas fa-wand-magic-sparkles"></i> Prism (OpenAI) <span class="details-wip-badge">WIP</span></div>
            <p class="details-hint">
              Inline AI drafting (GPT-based) will be wired in a later PR.
            </p>
          </div>
        `,
      },
      {
        id: "project",
        title: "Project Info",
        icon: "fa-circle-info",
        render: () => {
          if (!this.project) return `<p class="details-hint">Loading…</p>`;
          return `
            <div class="details-row"><span>Name</span><span>${escapeHtml(this.project.project_name)}</span></div>
            <div class="details-row"><span>Path</span><span class="details-mono">${escapeHtml(this.project.project_dir)}</span></div>
            <div class="details-row"><span>Doc types</span><span>${escapeHtml(this.project.doc_types.join(", ") || "(none)")}</span></div>
            <div class="details-row"><span>Shared</span><span>${this.project.has_shared ? "yes" : "no"}</span></div>
          `;
        },
      },
      {
        id: "shortcuts",
        title: "Shortcuts",
        icon: "fa-keyboard",
        render: () => `
          <div class="details-row"><kbd>Ctrl</kbd>+<kbd>S</kbd><span>Save current section</span></div>
          <div class="details-row"><kbd>Ctrl</kbd>+<kbd>Shift</kbd>+<kbd>B</kbd><span>Compile</span></div>
          <div class="details-row"><kbd>Esc</kbd><span>Close open panel</span></div>
        `,
      },
    ];
  }

  /** Render the hints feed as a quiet digest: a severity summary line, then one
   * row per hint (most-severe first, already sorted by the feed). An empty feed
   * reads "the paper is quiet" — verified claims never appear. */
  private renderHints(): string {
    const feed = this.hints;
    if (!feed || feed.summary.total === 0) {
      return `<p class="details-hint">✓ No hints — the paper is quiet.</p>`;
    }
    const dotColor: Record<string, string> = {
      error: "var(--danger, #dc2626)",
      warning: "var(--warning, #d97706)",
      advice: "var(--info, #2563eb)",
      info: "#888",
    };
    const sev = feed.summary.by_severity;
    const chips = ["error", "warning", "advice", "info"]
      .filter((s) => sev[s])
      .map((s) => `${sev[s]} ${s}`)
      .join(" · ");
    const CAP = 50;
    const rows = feed.hints
      .slice(0, CAP)
      .map((f) => {
        const color = dotColor[f.severity] || "#888";
        return `
          <div class="details-row" title="${escapeHtml(f.kind)} · ${escapeHtml(f.source)}">
            <span><span class="details-dot" style="background:${color}"></span> ${escapeHtml(f.message)}</span>
            ${this.renderHintLocation(f)}
          </div>`;
      })
      .join("");
    const more =
      feed.hints.length > CAP
        ? `<p class="details-hint">+${feed.hints.length - CAP} more (showing first ${CAP}).</p>`
        : "";
    return `
      <p class="details-hint">${chips}</p>
      ${rows}
      ${more}
      <p class="details-hint">Refreshes on compile. Verified claims stay silent.</p>
    `;
  }

  /** The right-aligned location cell for one hint row.
   *
   * - `file`+`line` present and an editor-jump hook is wired → a clickable
   *   `file:line` anchor that reveals that source line in the editor.
   * - `page` present and a PDF-jump hook is wired → a clickable `p.N` anchor
   *   that scrolls the PDF viewer to that page (additive, shown alongside).
   * - otherwise → plain, non-clickable text (`file:line`, or `line N`, or
   *   nothing) — preserving the pre-anchor behaviour for hosts that wire no
   *   navigation and for hints that carry no jumpable location. */
  private renderHintLocation(hint: Hint): string {
    const loc = hint.location;
    if (!loc) return "";
    const parts: string[] = [];

    if (loc.file && loc.line != null) {
      const label = `${escapeHtml(loc.file)}:${loc.line}`;
      parts.push(
        this.onJumpToLocation
          ? `<a href="#" class="details-hint-jump" data-jump-file="${escapeHtml(
              loc.file,
            )}" data-jump-line="${loc.line}" title="Jump to ${label}">${label}</a>`
          : `<span class="details-mono">${label}</span>`,
      );
    } else if (loc.file) {
      parts.push(`<span class="details-mono">${escapeHtml(loc.file)}</span>`);
    } else if (loc.line != null) {
      parts.push(`<span class="details-mono">line ${loc.line}</span>`);
    }

    if (loc.page != null && this.onJumpToPage) {
      parts.push(
        `<a href="#" class="details-hint-jump" data-jump-page="${loc.page}" title="Jump to page ${loc.page} in the PDF">p.${loc.page}</a>`,
      );
    } else if (loc.page != null) {
      parts.push(`<span class="details-mono">p.${loc.page}</span>`);
    }

    return parts.join(" ");
  }

  private render(): void {
    const sections = this.sections();
    this.container.innerHTML = `
      <div class="details-header">
        <i class="fas fa-sliders"></i> Details
      </div>
      <div class="details-body">
        ${sections
          .map(
            (s) => `
          <div class="details-section ${this.open.has(s.id) ? "open" : ""}" data-id="${s.id}">
            <button class="details-section-toggle" data-toggle="${s.id}">
              <i class="fas ${s.icon}"></i>
              <span class="details-section-title">${s.title}</span>
              ${s.wip ? `<span class="details-wip-badge">WIP</span>` : ""}
              <i class="fas fa-chevron-right details-chevron"></i>
            </button>
            ${this.open.has(s.id) ? `<div class="details-section-body">${s.render()}</div>` : ""}
          </div>`,
          )
          .join("")}
      </div>
    `;
    this.container
      .querySelectorAll<HTMLElement>("[data-toggle]")
      .forEach((el) => {
        el.addEventListener("click", () => {
          const id = el.dataset.toggle as SectionId;
          if (this.open.has(id)) this.open.delete(id);
          else this.open.add(id);
          this.saveOpenState();
          this.render();
        });
      });

    // Hint location anchors → editor / PDF jump. Only present when the host
    // wired the corresponding callback (see renderHintLocation).
    this.container
      .querySelectorAll<HTMLElement>(".details-hint-jump")
      .forEach((el) => {
        el.addEventListener("click", (event) => {
          event.preventDefault();
          const page = el.dataset.jumpPage;
          if (page != null) {
            this.onJumpToPage?.(Number(page));
            return;
          }
          const file = el.dataset.jumpFile;
          const line = el.dataset.jumpLine;
          if (file && line != null) {
            this.onJumpToLocation?.(file, Number(line));
          }
        });
      });
  }

  private loadOpenState(): Set<SectionId> {
    try {
      const raw = localStorage.getItem(STORAGE_KEY);
      if (!raw) return new Set(["compile-preview", "project"]);
      return new Set(JSON.parse(raw));
    } catch {
      return new Set(["hints", "compile-preview", "project"]);
    }
  }

  private saveOpenState(): void {
    try {
      localStorage.setItem(STORAGE_KEY, JSON.stringify(Array.from(this.open)));
    } catch {
      /* quota etc — ignore */
    }
  }
}

function escapeHtml(text: string): string {
  return text
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;");
}
