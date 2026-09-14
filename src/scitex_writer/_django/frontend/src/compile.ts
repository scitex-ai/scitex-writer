/**
 * Compile workflow — POST /api/compile, poll /api/compile/status, load PDF.
 * Status lamp (green/yellow/red), log drawer, preview-full toggle.
 */

import { apiPost, apiGet } from "./api";
import {
  type CompileDiagnostics,
  type JumpToLocation,
  renderCompileDiagnostics,
} from "./compile-diagnostics";
import { diagnosticsTranslate as t } from "./compile-diagnostics-i18n";
import type { PDFViewer } from "./pdf-viewer";

export type CompileMode = "preview" | "full";
export type LampStatus = "idle" | "compiling" | "ok" | "error";

interface CompileStatusResponse {
  compiling: boolean;
  result: {
    success?: boolean;
    error?: string;
    log?: string;
    diagnostics?: CompileDiagnostics;
  } | null;
  log: string;
}

interface CompileOptions {
  lamp: HTMLElement | null;
  logContent: HTMLElement | null;
  logPanel: HTMLElement | null;
  logTitle?: HTMLElement | null;
  diagnosticsContent?: HTMLElement | null;
  fullLogToggleBtn?: HTMLElement | null;
  /** Reveal a diagnostic's file:line in the editor. */
  onJumpToLocation?: JumpToLocation;
  toggleLogBtn: HTMLElement | null;
  closeLogBtn: HTMLElement | null;
  compileBtn: HTMLElement | null;
  modeToggleBtn: HTMLElement | null;
  pdf: PDFViewer;
  getDocType: () => string;
  /** Optional observer — Details panel subscribes to live lamp state. */
  onStatusChange?: (mode: CompileMode, status: LampStatus) => void;
}

export class CompileController {
  private opts: CompileOptions;
  private mode: CompileMode = "preview";
  private polling: number | null = null;
  private status: LampStatus = "idle";
  private afterCompileListeners: Array<(success: boolean) => void> = [];

  /** Subscribe to "compile finished" (success or error). */
  public onAfterCompile(cb: (success: boolean) => void): void {
    this.afterCompileListeners.push(cb);
  }

  constructor(opts: CompileOptions) {
    this.opts = opts;
    this.wireEvents();
    this.updateLamp("idle");
    this.updateModeButton();
  }

  private wireEvents(): void {
    this.opts.compileBtn?.addEventListener("click", () => void this.compile());
    this.opts.toggleLogBtn?.addEventListener("click", () => this.toggleLog());
    this.opts.closeLogBtn?.addEventListener("click", () =>
      this.setLogOpen(false),
    );
    this.opts.modeToggleBtn?.addEventListener("click", () => this.toggleMode());
    this.opts.fullLogToggleBtn?.addEventListener("click", () =>
      this.setFullLogVisible(this.fullLogHidden()),
    );
    if (this.opts.logTitle) this.opts.logTitle.textContent = t("panelTitle");
    window.addEventListener("keydown", (event) => {
      if (
        (event.ctrlKey || event.metaKey) &&
        event.shiftKey &&
        event.key === "B"
      ) {
        event.preventDefault();
        void this.compile();
      }
    });
  }

  async compile(): Promise<void> {
    if (this.status === "compiling") return;
    const docType = this.opts.getDocType();
    this.updateLamp("compiling");
    this.setLog("");
    this.showDiagnostics(null, true);
    try {
      const { effectivePdfDarkMode } = await import("./pdf-theme");
      await apiPost("api/compile", {
        doc_type: docType,
        draft: this.mode === "preview",
        dark_mode: effectivePdfDarkMode(),
      });
      this.pollStatus(docType);
    } catch (err) {
      this.showRequestFailure(err);
    }
  }

  /** A compile request that never reached the engine still explains itself. */
  private showRequestFailure(err: unknown): void {
    const message = String(err);
    this.setLog(message);
    this.updateLamp("error");
    this.showDiagnostics(
      {
        status: { kind: "scitex", code: "request-failed", message },
        report: { package: "scitex-writer", ok: false, checks: [], summary: message },
        items: [
          {
            cause: "unknown",
            severity: "error",
            message: t("requestFailed", { error: message }),
            hint: t("requestFailedHint"),
            context: "",
            file: null,
            line: null,
          },
        ],
        log_path: null,
      },
      false,
    );
    this.setLogOpen(true);
  }

  private pollStatus(docType: string): void {
    if (this.polling) window.clearTimeout(this.polling);
    const tick = async () => {
      try {
        const status =
          await apiGet<CompileStatusResponse>("api/compile/status");
        if (status.log) this.setLog(status.log);
        if (status.compiling) {
          this.polling = window.setTimeout(tick, 800);
          return;
        }
        const success = status.result?.success ?? false;
        this.updateLamp(success ? "ok" : "error");
        if (!status.log && status.result?.error) {
          this.setLog(status.result.error);
        }
        const diagnostics = status.result?.diagnostics;
        this.showDiagnostics(diagnostics, success);
        const hasErrors = (diagnostics?.items ?? []).some(
          (item) => item.severity === "error",
        );
        if (!success || hasErrors) this.setLogOpen(true);
        if (success) await this.opts.pdf.load(docType);
        for (const cb of this.afterCompileListeners) {
          try {
            cb(success);
          } catch (err) {
            console.error("[compile] afterCompile listener failed", err);
          }
        }
      } catch (err) {
        this.showRequestFailure(err);
      }
    };
    this.polling = window.setTimeout(tick, 400);
  }

  private updateLamp(status: LampStatus): void {
    this.status = status;
    const lamp = this.opts.lamp;
    if (lamp) {
      lamp.className = `writer-lamp lamp-${status}`;
      const title =
        status === "compiling"
          ? "Compiling…"
          : status === "ok"
            ? "Last compile: success"
            : status === "error"
              ? "Last compile: error"
              : "Idle";
      lamp.title = title;
    }
    this.opts.onStatusChange?.(this.mode, status);
  }

  /** Render the diagnostics list; the raw log stays behind "Show full log". */
  private showDiagnostics(
    diagnostics: CompileDiagnostics | null | undefined,
    success: boolean,
  ): void {
    const container = this.opts.diagnosticsContent;
    if (!container) return;
    const shown = renderCompileDiagnostics(container, diagnostics, {
      success,
      onJump: this.opts.onJumpToLocation,
    });
    container.classList.toggle("u-hidden", shown === 0);
    this.setFullLogVisible(shown === 0);
  }

  private fullLogHidden(): boolean {
    return this.opts.logContent?.classList.contains("u-hidden") ?? false;
  }

  private setFullLogVisible(visible: boolean): void {
    this.opts.logContent?.classList.toggle("u-hidden", !visible);
    const button = this.opts.fullLogToggleBtn;
    if (button) {
      button.textContent = visible ? t("hideFullLog") : t("showFullLog");
      button.setAttribute("aria-expanded", String(visible));
    }
  }

  private setLog(text: string): void {
    if (this.opts.logContent) this.opts.logContent.textContent = text;
  }

  private setLogOpen(open: boolean): void {
    this.opts.logPanel?.classList.toggle("u-hidden", !open);
  }

  private toggleLog(): void {
    if (!this.opts.logPanel) return;
    const isHidden = this.opts.logPanel.classList.contains("u-hidden");
    this.setLogOpen(isHidden);
  }

  private toggleMode(): void {
    this.mode = this.mode === "preview" ? "full" : "preview";
    this.updateModeButton();
  }

  private updateModeButton(): void {
    const btn = this.opts.modeToggleBtn;
    if (!btn) return;
    btn.textContent = this.mode === "preview" ? "Preview" : "Full";
    btn.classList.toggle("active-full", this.mode === "full");
  }
}
