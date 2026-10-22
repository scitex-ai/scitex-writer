/**
 * Writer's phone layout (<=768px): one pane at a time, explicit tabs.
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
 * NO BOTTOM ACTION BAR (operator 2026-10-22): the Save/Log/Compile bar is
 * dropped — the toolbar row already carries Log, Compile + the Draft/Full
 * mode select on every viewport, and Save is autosave (debounced flushSave +
 * save-status indicator, same path Ctrl+S takes), so a second fixed bar
 * duplicates entry points instead of adding reachability. The
 * one CompileController stays the only compile entry point. (The removed bar
 * used to forward to #btn-compile and mirror the lamp; that whole layer is
 * gone.)
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

import { controlsTranslate } from "./controls-i18n";

export type MobilePane = "files" | "editor" | "preview" | "details";

/**
 * ONE breakpoint, mirrored by `@media (max-width: 768px)` in
 * `static/writer/css/editor-mobile.css` (and equal to scitex-ui's mobile
 * breakpoint, so writer and the shell switch at the same width). A custom
 * property cannot be read by `matchMedia`, so the two literals have to be kept
 * in step by hand — `test_views_editor_mobile.py` pins both.
 */
export const MOBILE_BREAKPOINT = "(max-width: 768px)";

const PANES: readonly MobilePane[] = ["files", "editor", "preview", "details"];

/** The editor is what a writer opens the app for. */
const DEFAULT_PANE: MobilePane = "editor";

export function isMobileViewport(): boolean {
  return window.matchMedia(MOBILE_BREAKPOINT).matches;
}

export interface MobileLayoutHooks {
  /** A pane became active — the caller re-lays out what it owns (Monaco was
   * hidden, so it needs a layout pass; the PDF needs a fit-width). */
  onPaneChange?: (pane: MobilePane) => void;
}

/**
 * The pane switcher.
 *
 * Compile is NOT re-implemented here: #btn-compile in the toolbar row is the
 * one compile entry point and the one `CompileController`. Log is the toolbar
 * #btn-toggle-log; Save is autosave with a status indicator. Nothing here
 * forwards or mirrors — the bar is gone.
 */
export class MobileLayout {
  private readonly hooks: MobileLayoutHooks;
  private readonly tabs = new Map<MobilePane, HTMLButtonElement>();
  private pane: MobilePane = DEFAULT_PANE;

  constructor(root: HTMLElement, hooks: MobileLayoutHooks = {}) {
    this.hooks = hooks;

    // Edge-zone single-finger pane swipe (operator gap): a horizontal swipe
    // starting within EDGE_PX of the screen edge moves one pane left/right.
    // Edges only — never over Monaco (selection) or the PDF (pan). Vertical
    // drift beyond SLOP_PX, multi-touch, or form targets cancel. The shell's
    // two-finger collapse stays untouched.
    this.wireEdgeSwipe(root);

    const switcher = root.querySelector<HTMLElement>("#writer-mobile-panes");
    for (const button of Array.from(
      switcher?.querySelectorAll<HTMLButtonElement>("[data-mobile-pane]") ?? [],
    )) {
      const pane = button.dataset.mobilePane as MobilePane;
      if (!PANES.includes(pane)) continue;
      this.tabs.set(pane, button);
      if (pane === "details") button.textContent = controlsTranslate("details");
      button.addEventListener("click", () => this.setPane(pane));
    }

    // Save/Log/Compile live in the toolbar row on every viewport now — no
    // forwarding, no mirroring, nothing to wire here.

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

  /**
   * Edge-zone single-finger pane swipe.
   *
   * A horizontal swipe that STARTS within EDGE_PX of the left/right screen
   * edge moves one pane in swipe direction (left-edge swipe-right = previous
   * pane, right-edge swipe-left = next pane). Anywhere else the gesture is
   * ignored — Monaco owns horizontal drags for selection, the PDF owns them
   * for pan. Vertical drift > SLOP_PX, multi-touch, or a start inside an
   * input/select/textarea/contenteditable cancels.
   */
  private wireEdgeSwipe(root: HTMLElement): void {
    const EDGE_PX = 24;
    const THRESHOLD_PX = 48;
    const SLOP_PX = 32;
    let startX = 0;
    let startY = 0;
    let tracking = false;

    const isFormTarget = (t: EventTarget | null): boolean =>
      t instanceof HTMLElement &&
      Boolean(t.closest("input, textarea, select, [contenteditable='true']"));

    root.addEventListener(
      "touchstart",
      (e) => {
        if (!isMobileViewport() || e.touches.length !== 1) {
          tracking = false;
          return;
        }
        const t = e.touches[0];
        const w = window.innerWidth;
        if (t.clientX > EDGE_PX && t.clientX < w - EDGE_PX) return;
        if (isFormTarget(e.target)) return;
        startX = t.clientX;
        startY = t.clientY;
        tracking = true;
      },
      { passive: true },
    );

    root.addEventListener(
      "touchmove",
      (e) => {
        if (!tracking || e.touches.length !== 1) {
          tracking = false;
          return;
        }
        const t = e.touches[0];
        if (Math.abs(t.clientY - startY) > SLOP_PX) tracking = false;
      },
      { passive: true },
    );

    root.addEventListener("touchend", (e) => {
      if (!tracking) return;
      tracking = false;
      if (!isMobileViewport()) return;
      const t = e.changedTouches[0];
      const dx = t.clientX - startX;
      if (Math.abs(dx) < THRESHOLD_PX) return;
      if (Math.abs(t.clientY - startY) > SLOP_PX) return;
      const i = PANES.indexOf(this.pane);
      const next = dx < 0 ? i + 1 : i - 1;
      if (next < 0 || next >= PANES.length) return;
      this.setPane(PANES[next]);
    });
  }
}
