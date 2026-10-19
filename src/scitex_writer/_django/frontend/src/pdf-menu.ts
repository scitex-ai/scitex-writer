/**
 * PDF options hamburger menu — shared by the editor (index.ts) and the
 * read-only viewer (viewer.ts). CCT4485: the six small PDF op icons collapse
 * into one hamburger; every op keeps its button ID (so existing action
 * wiring is untouched) and gains a keyboard shortcut.
 *
 * Shortcuts (also listed in Details > Shortcuts):
 *   Ctrl+= / Ctrl++  zoom in      (editor + viewer)
 *   Ctrl+-           zoom out     (editor + viewer)
 *   Ctrl+0           fit width    (editor + viewer)
 *   Ctrl+Shift+R     refresh PDF  (editor only)
 *   Alt+T            cycle PDF theme (editor only)
 *   Alt+D            download PDF (editor only)
 *
 * Shortcuts fire globally (menu open or closed) by delegating to the real
 * buttons' click handlers, so there is exactly one action path per op.
 */

function clickIfPresent(root: ParentNode, selector: string): boolean {
  const el = root.querySelector<HTMLElement>(selector);
  if (!el) return false;
  el.click();
  return true;
}

function isEditableTarget(target: EventTarget | null): boolean {
  const el = target as HTMLElement | null;
  if (!el || typeof (el as HTMLElement).closest !== "function") return false;
  return Boolean(
    (el as HTMLElement).closest(
      "input, textarea, select, [contenteditable='true'], [contenteditable='']",
    ),
  );
}

export function mountPdfMenu(root: HTMLElement): void {
  const menuBtn = root.querySelector<HTMLButtonElement>("#btn-pdf-menu");
  const menuList = root.querySelector<HTMLElement>("#pdf-menu-list");
  if (!menuBtn || !menuList) return;

  const setOpen = (open: boolean) => {
    menuList.classList.toggle("u-hidden", !open);
    menuBtn.setAttribute("aria-expanded", open ? "true" : "false");
  };
  const isOpen = () => !menuList.classList.contains("u-hidden");

  menuBtn.addEventListener("click", (event) => {
    event.stopPropagation();
    setOpen(!isOpen());
  });

  // Choosing an op dismisses the menu (standard menu behaviour).
  menuList.querySelectorAll<HTMLElement>(".pdf-menu-item").forEach((item) => {
    item.addEventListener("click", () => setOpen(false));
  });

  document.addEventListener("click", (event) => {
    if (!isOpen()) return;
    const target = event.target as HTMLElement | null;
    if (target && menuList.contains(target)) return;
    setOpen(false);
  });

  document.addEventListener("keydown", (event) => {
    if (event.key === "Escape" && isOpen()) {
      setOpen(false);
      menuBtn.focus();
    }
  });

  window.addEventListener("keydown", (event) => {
    // Alt-letter PDF ops never fire while typing in a form field.
    const mod = event.ctrlKey || event.metaKey;
    const key = event.key;

    if (mod && (key === "=" || key === "+")) {
      event.preventDefault();
      clickIfPresent(root, "#btn-pdf-zoom-in");
      return;
    }
    if (mod && key === "-") {
      event.preventDefault();
      clickIfPresent(root, "#btn-pdf-zoom-out");
      return;
    }
    if (mod && key === "0") {
      event.preventDefault();
      clickIfPresent(root, "#btn-pdf-fit");
      return;
    }
    if (mod && event.shiftKey && (key === "R" || key === "r")) {
      if (root.querySelector("#btn-refresh-pdf")) {
        event.preventDefault();
        clickIfPresent(root, "#btn-refresh-pdf");
      }
      return;
    }
    if (event.altKey && !mod && (key === "t" || key === "T")) {
      if (isEditableTarget(event.target)) return;
      if (root.querySelector("#btn-pdf-theme")) {
        event.preventDefault();
        clickIfPresent(root, "#btn-pdf-theme");
      }
      return;
    }
    if (event.altKey && !mod && (key === "d" || key === "D")) {
      if (isEditableTarget(event.target)) return;
      if (root.querySelector("#btn-pdf-download")) {
        event.preventDefault();
        clickIfPresent(root, "#btn-pdf-download");
      }
    }
  });
}
