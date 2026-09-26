/**
 * Writer's phone layout (<=768px): one pane at a time, explicit tabs, and a
 * bottom action bar with Save / Log / Compile.
 *
 * WHY THIS EXISTS: below 768px the scitex-ui shell stacks every pane
 * vertically, which is the right default for a workspace but wrong for writer —
 * the section list, the editor and the PDF end up as three full-height blocks
 * on one column, so the editor is off-screen until you scroll past the nav and
 * the editor's own bottom edge is never where the compile controls are. Writer
 * therefore declares its own single-pane layout: the switcher picks ONE
 * surface, and the choice lives on `body[data-writer-mobile-pane]`, which is
 * the only hook `static/writer/css/editor-mobile.css` reads.
 *
 * EXPLICIT TABS, NO SWIPE. A horizontal gesture over the editor would race
 * Monaco's own text selection and the PDF viewer's pan, and the failure mode
 * (typing turns into a pane switch) is worse than a tap. scitex-ui extracts the
 * shared primitive from these real implementations (operator 2026-09-14), so
 * the shared version can only be as good as what is here first.
 *
 * The desktop layout is untouched: every rule the stylesheet adds is inside
 * `@media (max-width: 768px)`, and this module only writes state.
 */

export type MobilePane = "files" | "editor" | "preview";

/**
 * ONE breakpoint, mirrored by `@media (max-width: 768px)` in
 * `static/writer/css/editor-mobile.css` (and equal to scitex-ui's mobile
 * breakpoint, so writer and the shell switch at the same width). A custom
 * property cannot be read by `matchMedia`, so the two literals have to be kept
 * in step by hand — `test_views_editor_mobile.py` pins both.
 */
export const MOBILE_BREAKPOINT = "(max-width: 768px)";

const PANES: readonly MobilePane[] = ["files", "editor", "preview"];

/** The editor is what a writer opens the app for. */
const DEFAULT_PANE: MobilePane = "editor";

export function isMobileViewport(): boolean {
  return window.matchMedia(MOBILE_BREAKPOINT).matches;
}

export interface MobileLayoutHooks {
  /** Save now, without waiting for the autosave debounce. */
  onSave?: () => void;
  /** Open the compilation log/diagnostics panel. */
  onToggleLog?: () => void;
  /** A pane became active — the caller re-lays out what it owns (Monaco was
   * hidden, so it needs a layout pass; the PDF needs a fit-width). */
  onPaneChange?: (pane: MobilePane) => void;
}

/**
 * The pane switcher and the bottom action bar.
 *
 * Compile is NOT re-implemented here: the bar's button forwards a click to the
 * desktop `#btn-compile`, so there is exactly one compile entry point and one
 * `CompileController` — the bar only mirrors that controller's in-flight state.
 */
export class MobileLayout {
  private readonly hooks: MobileLayoutHooks;
  private readonly tabs = new Map<MobilePane, HTMLButtonElement>();
  private readonly compileBtn: HTMLButtonElement | null;
  private readonly lamp: HTMLElement | null;
  private pane: MobilePane = DEFAULT_PANE;

  constructor(root: HTMLElement, hooks: MobileLayoutHooks = {}) {
    this.hooks = hooks;

    const switcher = root.querySelector<HTMLElement>("#writer-mobile-panes");
    for (const button of Array.from(
      switcher?.querySelectorAll<HTMLButtonElement>("[data-mobile-pane]") ?? [],
    )) {
      const pane = button.dataset.mobilePane as MobilePane;
      if (!PANES.includes(pane)) continue;
      this.tabs.set(pane, button);
      button.addEventListener("click", () => this.setPane(pane));
    }

    root
      .querySelector<HTMLElement>("#btn-mobile-save")
      ?.addEventListener("click", () => this.hooks.onSave?.());
    root
      .querySelector<HTMLElement>("#btn-mobile-log")
      ?.addEventListener("click", () => this.hooks.onToggleLog?.());

    // The desktop button is hidden on a phone but still the real control; a
    // hidden element receives programmatic clicks, so forwarding keeps the
    // controller, the polling and the diagnostics in one place.
    this.compileBtn = root.querySelector<HTMLButtonElement>("#btn-mobile-compile");
    const desktopCompileBtn =
      root.querySelector<HTMLButtonElement>("#btn-compile");
    this.compileBtn?.addEventListener("click", () => desktopCompileBtn?.click());

    // Compile status is published on the lamp (`lamp-compiling` and friends),
    // so the bar mirrors that instead of duplicating the controller's state.
    this.lamp = root.querySelector<HTMLElement>("#compile-lamp");
    if (this.compileBtn && this.lamp) {
      this.syncCompileButton();
      new MutationObserver(() => this.syncCompileButton()).observe(this.lamp, {
        attributes: true,
        attributeFilter: ["class"],
      });
    }

    this.setPane(this.readPane());
  }

  get activePane(): MobilePane {
    return this.pane;
  }

  setPane(pane: MobilePane): void {
    this.pane = pane;
    document.body.dataset.writerMobilePane = pane;
    for (const [name, button] of this.tabs) {
      const active = name === pane;
      button.classList.toggle("is-active", active);
      if (active) button.setAttribute("aria-current", "true");
      else button.removeAttribute("aria-current");
    }
    this.hooks.onPaneChange?.(pane);
  }

  private readPane(): MobilePane {
    // Set before first paint by an inline script in editor.html; absent when
    // that script did not run, in which case the default is also what the
    // template's markup shows as active.
    const initial = document.body.dataset.writerMobilePane as
      | MobilePane
      | undefined;
    return initial && PANES.includes(initial) ? initial : DEFAULT_PANE;
  }

  private syncCompileButton(): void {
    if (!this.compileBtn || !this.lamp) return;
    const compiling = this.lamp.classList.contains("lamp-compiling");
    this.compileBtn.disabled = compiling;
    const label = this.compileBtn.querySelector<HTMLElement>("span");
    if (label) label.textContent = compiling ? "Compiling…" : "Compile";
    this.compileBtn.setAttribute("aria-busy", String(compiling));
  }
}
