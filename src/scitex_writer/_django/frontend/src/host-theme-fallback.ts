/**
 * Host theme-toggle fallback — wires the host-injected `#theme-toggle`
 * ("Switch to dark/light mode") when the host's own theme bundle is absent.
 *
 * On hub-served leaf pages (`/apps/writer/`, `/apps/writer/viewer/`) the
 * SiteContentFrameMiddleware prepends hub's global header — including the
 * theme row — but the standalone shell never loads hub's JS bundles, so
 * hub's `theme-switcher.ts` (the row's only owner) never runs there and the
 * row is a dead button: clicking changes nothing until a reload, which only
 * re-applies whatever was already stored.
 *
 * This fallback is deliberately last-resort: when `window.SciTeX.theme`
 * exists the host owns the row and we stay out of the way (no double
 * wiring). Otherwise we apply the toggle exactly like the host would —
 * `data-theme` (+ `data-color-mode`) on `<html>`, the canonical storage
 * keys, and the `theme-changed` event — so the shell CSS, the Monaco
 * observer and any host listener all react in the same tick.
 */

export type UiTheme = "dark" | "light";

/** Canonical key converged with scitex-ui's ThemeProvider ("stx-theme"). */
export const THEME_STORAGE_KEY = "stx-theme";
/**
 * Legacy hub key. Still written in sync for one release cycle — cached
 * bundles and tool embeds listen on it — and still honoured at boot.
 */
export const THEME_LEGACY_STORAGE_KEY = "scitex-theme-preference";

function renderedTheme(): UiTheme {
  const rendered = document.documentElement.getAttribute("data-theme");
  if (rendered === "dark" || rendered === "light") return rendered;
  const stored = readStoredTheme();
  return stored ?? "dark";
}

export function readStoredTheme(): UiTheme | null {
  try {
    const stored =
      localStorage.getItem(THEME_STORAGE_KEY) ??
      localStorage.getItem(THEME_LEGACY_STORAGE_KEY);
    if (stored === "dark" || stored === "light") return stored;
  } catch {
    /* private mode / storage disabled — fall through to default */
  }
  return null;
}

/**
 * Apply a theme exactly the way the host's theme-switcher would: attribute
 * on `<html>` (the shell CSS and the Monaco MutationObserver both key off
 * it), the canonical storage keys, and the `theme-changed` contract event.
 */
export function applyUiTheme(theme: UiTheme): void {
  const html = document.documentElement;
  html.dataset.theme = theme;
  html.setAttribute("data-color-mode", theme);
  try {
    localStorage.setItem(THEME_STORAGE_KEY, theme);
    localStorage.setItem(THEME_LEGACY_STORAGE_KEY, theme);
  } catch {
    /* storage unavailable — the attribute change still applies live */
  }
  syncHostThemeToggle();
  syncWriterThemeButton();
  document.dispatchEvent(new CustomEvent("theme-changed", { detail: { theme } }));
}

/** Refresh the host row's label/aria from the RENDERED theme. */
export function syncHostThemeToggle(): void {
  const toggleBtn = document.getElementById("theme-toggle");
  if (!toggleBtn) return;
  const theme = renderedTheme();
  const actionLabel =
    theme === "dark"
      ? toggleBtn.dataset.labelLight || "Switch to light mode"
      : toggleBtn.dataset.labelDark || "Switch to dark mode";
  toggleBtn.setAttribute("aria-label", actionLabel);
  const visibleLabel = toggleBtn.querySelector<HTMLElement>(
    "[data-theme-toggle-label]",
  );
  if (visibleLabel) visibleLabel.textContent = actionLabel;
}

/** Refresh the writer toolbar's own toggle (no-op when absent, e.g. viewer). */
export function syncWriterThemeButton(): void {
  const themeBtn = document.querySelector<HTMLButtonElement>("#btn-toggle-theme");
  if (!themeBtn) return;
  const mode = renderedTheme();
  const icon = themeBtn.querySelector<HTMLElement>("i");
  if (icon) {
    // fa-circle-half-stroke unambiguously signals a toggle — avoids the
    // "sun icon looks like a gear" readability issue with fa-sun.
    icon.className = "fas fa-circle-half-stroke";
  }
  themeBtn.classList.toggle("theme-dark", mode === "dark");
  themeBtn.classList.toggle("theme-light", mode === "light");
  themeBtn.title = `Theme: ${mode} (click to switch)`;
}

function hostThemeApiPresent(): boolean {
  return (
    (window as unknown as { SciTeX?: { theme?: unknown } }).SciTeX?.theme !==
    undefined
  );
}

/**
 * Wire the host-injected `#theme-toggle` when — and only when — the host
 * bundle that owns it is absent. Returns true when the fallback attached.
 */
export function wireHostThemeToggle(): boolean {
  if (hostThemeApiPresent()) return false;
  const toggleBtn = document.getElementById("theme-toggle");
  if (!toggleBtn) return false;
  if (toggleBtn.dataset.hostThemeFallback === "wired") return true;
  toggleBtn.dataset.hostThemeFallback = "wired";
  syncHostThemeToggle();
  toggleBtn.addEventListener("click", () => {
    applyUiTheme(renderedTheme() === "dark" ? "light" : "dark");
  });
  return true;
}
