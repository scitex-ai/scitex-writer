/**
 * App-level annotation UI for the interactive paper editor (ADR 0001, slice 2).
 *
 * The pen loop (L1 viewer → AnnotationStore) is the neutral core; THIS is the
 * writer-app-specific chrome that makes it a research-review tool, kept out of
 * `@scitex/ui` L1 on purpose (scitex-ui's #274 guidance — the domain categories
 * are paper-review semantics, not a generic PDF concern):
 *   - a mode switch (Read / Markup / Review),
 *   - domain-category buttons (Claim / Issue / Citation-needed / Figure-check …),
 *   - pen-tool buttons (highlight / box / circle / arrow / freehand),
 *   - a per-comment box with OS voice → text (loosely-coupled Web Speech),
 *   - Markdown export of the comment thread.
 *
 * It drives the viewer through a narrow structural interface (AnnotationController)
 * so the two stay decoupled — the UI never imports the PDF component.
 */

import {
  ANNOTATION_CATEGORIES,
  type Annotation,
  type AnnotationCategory,
  type AnnotationTool,
  CATEGORY_ICONS,
  CATEGORY_LABELS,
  type EditorMode,
} from "./annotations";
import { type ContextMenuItem, showContextMenu } from "./context-menu";
import { createVoiceInput } from "./voice-input";

/** The slice of PDFViewer the annotation UI drives (structural — keeps them decoupled). */
export interface AnnotationController {
  setCategory(category: AnnotationCategory): void;
  setTool(tool: AnnotationTool): void;
  setMode(mode: EditorMode): void;
  annotations(): Annotation[];
  setAnnotationText(id: string, text: string): void;
  setAnnotationCategory(id: string, category: AnnotationCategory): void;
  removeAnnotation(id: string): void;
  exportMarkdown(title?: string): string;
}

export interface AnnotationUIOptions {
  toolbar: HTMLElement;
  panel: HTMLElement;
  controller: AnnotationController;
}

export interface AnnotationUIHandle {
  /** Wire to the viewer's onAnnotate — registers a freshly created mark. */
  onAnnotate(annotation: Annotation): void;
}

interface ModeSpec {
  mode: EditorMode;
  icon: string;
  label: string;
}
interface ToolSpec {
  tool: AnnotationTool;
  icon: string;
  label: string;
}

const MODES: readonly ModeSpec[] = [
  { mode: "read", icon: "fa-book-open", label: "Read" },
  { mode: "markup", icon: "fa-pen-nib", label: "Markup" },
  { mode: "review", icon: "fa-comments", label: "Review" },
];

const PEN_TOOLS: readonly ToolSpec[] = [
  { tool: "highlight", icon: "fa-highlighter", label: "Highlight" },
  { tool: "box", icon: "fa-vector-square", label: "Box" },
  { tool: "circle", icon: "fa-circle-notch", label: "Circle" },
  { tool: "arrow", icon: "fa-arrow-right", label: "Arrow" },
  { tool: "freehand", icon: "fa-pen", label: "Freehand" },
];

function iconButton(icon: string, title: string): HTMLButtonElement {
  const b = document.createElement("button");
  b.type = "button";
  b.className = "btn btn-icon btn-sm annot-btn";
  b.title = title;
  b.setAttribute("aria-label", title);
  b.innerHTML = `<i class="fas ${icon}"></i>`;
  return b;
}

export function mountAnnotationUI(opts: AnnotationUIOptions): AnnotationUIHandle {
  const { toolbar, panel, controller } = opts;
  let activeField: HTMLTextAreaElement | null = null;
  let activeMic: HTMLElement | null = null;

  const voice = createVoiceInput({
    onResult: (text, isFinal) => {
      if (!activeField || !isFinal) return;
      const trimmed = text.trim();
      if (!trimmed) return;
      const sep =
        activeField.value && !activeField.value.endsWith(" ") ? " " : "";
      activeField.value = activeField.value + sep + trimmed;
      activeField.dispatchEvent(new Event("input", { bubbles: true }));
    },
    onStateChange: (listening) => {
      activeMic?.classList.toggle("listening", listening);
    },
  });

  // --- toolbar: one hamburger, menu holds modes / categories / tools.
  // Operator 2026-10-23: seventeen small buttons in a row are unreadable —
  // they live in a hamburger menu (like the PDF ops menu) with shortcuts.
  // The SAME button elements move into the menu, so existing wiring, IDs
  // and .active states keep working with exactly one action path each.
  toolbar.classList.add("annot-toolbar");
  toolbar.replaceChildren();

  const menuBtn = iconButton("fa-bars", "Annotation tools");
  menuBtn.id = "btn-annot-menu";
  menuBtn.setAttribute("aria-haspopup", "menu");
  menuBtn.setAttribute("aria-expanded", "false");
  menuBtn.setAttribute("aria-controls", "annot-menu-list");
  const menuList = document.createElement("div");
  menuList.id = "annot-menu-list";
  menuList.className = "annot-menu-list u-hidden";
  menuList.setAttribute("role", "menu");

  const setMenuOpen = (open: boolean): void => {
    menuList.classList.toggle("u-hidden", !open);
    menuBtn.setAttribute("aria-expanded", open ? "true" : "false");
  };
  const isMenuOpen = (): boolean => !menuList.classList.contains("u-hidden");
  menuBtn.addEventListener("click", (event) => {
    event.stopPropagation();
    setMenuOpen(!isMenuOpen());
  });
  document.addEventListener("click", (event) => {
    if (!isMenuOpen()) return;
    const target = event.target as HTMLElement | null;
    if (target && menuList.contains(target)) return;
    setMenuOpen(false);
  });
  document.addEventListener("keydown", (event) => {
    if (event.key === "Escape" && isMenuOpen()) {
      setMenuOpen(false);
      menuBtn.focus();
    }
  });

  // Menu sections keep the row groups' structure (and their .active
  // underline cues) with a heading + shortcut hints per item.
  function menuSection(label: string): HTMLElement {
    const section = document.createElement("div");
    section.className = "annot-menu-section";
    section.setAttribute("role", "group");
    section.setAttribute("aria-label", label);
    const heading = document.createElement("span");
    heading.className = "annot-menu-heading";
    heading.textContent = label;
    section.appendChild(heading);
    const row = document.createElement("div");
    row.className = "annot-menu-row";
    section.appendChild(row);
    menuList.appendChild(section);
    return row;
  }
  function menuify(button: HTMLButtonElement, shortcut?: string): void {
    button.setAttribute("role", "menuitem");
    if (shortcut) {
      const kbd = document.createElement("kbd");
      kbd.textContent = shortcut;
      button.appendChild(document.createTextNode(" "));
      button.appendChild(kbd);
    }
    button.addEventListener("click", () => setMenuOpen(false));
  }

  const modeRow = menuSection("Modes");
  const modeButtons = new Map<EditorMode, HTMLButtonElement>();
  const modeShortcuts: Record<EditorMode, string> = {
    read: "Alt+1",
    markup: "Alt+2",
    review: "Alt+3",
  };
  for (const spec of MODES) {
    const b = iconButton(spec.icon, `${spec.label} mode`);
    b.append(document.createTextNode(` ${spec.label}`));
    b.addEventListener("click", () => setMode(spec.mode));
    modeButtons.set(spec.mode, b);
    menuify(b, modeShortcuts[spec.mode]);
    modeRow.appendChild(b);
  }

  const catRow = menuSection("Categories");
  const catButtons = new Map<AnnotationCategory, HTMLButtonElement>();
  for (const category of ANNOTATION_CATEGORIES) {
    const b = iconButton(CATEGORY_ICONS[category], CATEGORY_LABELS[category]);
    b.dataset.category = category;
    b.append(document.createTextNode(` ${CATEGORY_LABELS[category]}`));
    b.addEventListener("click", () => setCategory(category));
    catButtons.set(category, b);
    menuify(b);
    catRow.appendChild(b);
  }

  const toolRow = menuSection("Tools");
  const toolButtons = new Map<AnnotationTool, HTMLButtonElement>();
  // Alt+1/2/3 are modes; tools take Alt+4..8 in row order (Alt+T and Alt+D
  // already belong to the PDF menu; Alt+F opens the browser menu).
  const toolShortcutKeys = ["4", "5", "6", "7", "8"];
  PEN_TOOLS.forEach((spec, index) => {
    const b = iconButton(spec.icon, spec.label);
    b.append(document.createTextNode(` ${spec.label}`));
    b.addEventListener("click", () => setTool(spec.tool));
    toolButtons.set(spec.tool, b);
    const shortcut = `Alt+${toolShortcutKeys[index]}`;
    menuify(b, shortcut);
    toolRow.appendChild(b);
  });

  const actionRow = menuSection("Comments");
  const clearBtn = iconButton("fa-trash", "Delete all comments");
  clearBtn.append(document.createTextNode(" Delete all"));
  clearBtn.classList.add("annot-clear");
  clearBtn.addEventListener("click", clearAll);

  const exportBtn = iconButton("fa-file-arrow-down", "Export comments as Markdown");
  exportBtn.append(document.createTextNode(" Export"));
  exportBtn.classList.add("annot-export");
  exportBtn.addEventListener("click", exportMarkdown);

  for (const b of [clearBtn, exportBtn]) {
    menuify(b);
    actionRow.appendChild(b);
  }

  toolbar.append(menuBtn, menuList);

  // Shortcuts fire globally (menu open or closed) by delegating to the
  // menu buttons' own click handlers — one action path, like pdf-menu.
  function isEditableTarget(target: EventTarget | null): boolean {
    const el = target as HTMLElement | null;
    if (!el || typeof (el as HTMLElement).closest !== "function") return false;
    return Boolean(
      (el as HTMLElement).closest(
        "input, textarea, select, [contenteditable='true'], [contenteditable='']",
      ),
    );
  }
  document.addEventListener("keydown", (event) => {
    if (!event.altKey || event.ctrlKey || event.metaKey) return;
    if (isEditableTarget(event.target)) return;
    const key = event.key.toLowerCase();
    const byKey: Record<string, HTMLButtonElement | undefined> = {
      "1": modeButtons.get("read"),
      "2": modeButtons.get("markup"),
      "3": modeButtons.get("review"),
      "4": toolButtons.get("highlight"),
      "5": toolButtons.get("box"),
      "6": toolButtons.get("circle"),
      "7": toolButtons.get("arrow"),
      "8": toolButtons.get("freehand"),
    };
    const target = byKey[key];
    if (target) {
      event.preventDefault();
      target.click();
    }
  });

  // --- panel ---
  panel.classList.add("annot-panel");

  function setMode(next: EditorMode): void {
    controller.setMode(next);
    for (const [mode, b] of modeButtons) b.classList.toggle("active", mode === next);
    toolbar.dataset.mode = next;
    panel.dataset.mode = next;
    if (next !== "markup") voice.stop();
  }

  function setCategory(next: AnnotationCategory): void {
    controller.setCategory(next);
    for (const [category, b] of catButtons)
      b.classList.toggle("active", category === next);
  }

  function setTool(next: AnnotationTool): void {
    controller.setTool(next);
    for (const [tool, b] of toolButtons) b.classList.toggle("active", tool === next);
  }

  function clearAll(): void {
    const items = controller.annotations();
    if (items.length === 0) return;
    const ok = globalThis.confirm?.(
      `Delete all ${items.length} comment${items.length === 1 ? "" : "s"}?`,
    );
    if (ok === false) return;
    for (const annotation of [...items]) controller.removeAnnotation(annotation.id);
    renderPanel();
  }

  function exportMarkdown(): void {
    const md = controller.exportMarkdown();
    const blob = new Blob([md], { type: "text/markdown" });
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = "review-comments.md";
    document.body.appendChild(a);
    a.click();
    a.remove();
    URL.revokeObjectURL(url);
  }

  function renderPanel(focusId?: string): void {
    const items = controller.annotations();
    panel.replaceChildren();
    // Visibility is content-based (hidden only when empty), NOT mode-based — so
    // comments (and their delete buttons) stay reachable in every mode. Losing
    // access to your own marks when switching to Read was the reported trap.
    panel.classList.toggle("annot-panel--empty", items.length === 0);
    if (items.length === 0) {
      const empty = document.createElement("p");
      empty.className = "annot-empty";
      empty.textContent =
        "No comments yet. Mark the PDF in Markup mode to start.";
      panel.appendChild(empty);
      return;
    }
    for (const annotation of items) {
      panel.appendChild(renderRow(annotation, annotation.id === focusId));
    }
  }

  function renderRow(annotation: Annotation, focus: boolean): HTMLElement {
    const row = document.createElement("div");
    row.className = "annot-row";
    row.dataset.category = annotation.category;
    // Right-click quick menu (operator request): change category or delete
    // without hunting for the trash icon.
    row.addEventListener("contextmenu", (event) => {
      event.preventDefault();
      const items: ContextMenuItem[] = [
        ...ANNOTATION_CATEGORIES.filter((c) => c !== annotation.category).map(
          (category) => ({
            label: `Set: ${CATEGORY_LABELS[category]}`,
            icon: CATEGORY_ICONS[category],
            onSelect: () => {
              controller.setAnnotationCategory(annotation.id, category);
              renderPanel();
            },
          }),
        ),
        { separator: true },
        {
          label: "Delete comment",
          icon: "fa-trash",
          danger: true,
          onSelect: () => {
            controller.removeAnnotation(annotation.id);
            renderPanel();
          },
        },
      ];
      showContextMenu(event.clientX, event.clientY, items);
    });

    const head = document.createElement("div");
    head.className = "annot-row-head";
    const badge = document.createElement("span");
    badge.className = "annot-badge";
    badge.innerHTML = `<i class="fas ${CATEGORY_ICONS[annotation.category]}"></i> ${
      CATEGORY_LABELS[annotation.category]
    }`;
    const page = document.createElement("span");
    page.className = "annot-page";
    page.textContent = `p.${annotation.page}`;
    const del = iconButton("fa-trash", "Delete comment");
    del.classList.add("annot-del");
    del.addEventListener("click", () => {
      controller.removeAnnotation(annotation.id);
      renderPanel();
    });
    head.append(badge, page, del);

    const body = document.createElement("div");
    body.className = "annot-row-body";
    const textarea = document.createElement("textarea");
    textarea.className = "annot-text";
    textarea.rows = 2;
    textarea.placeholder = "Comment… (dictate with OS voice input or the mic)";
    textarea.value = annotation.text;
    textarea.addEventListener("input", () =>
      controller.setAnnotationText(annotation.id, textarea.value),
    );
    textarea.addEventListener("focus", () => {
      activeField = textarea;
    });
    body.appendChild(textarea);

    if (voice.supported) {
      const mic = iconButton("fa-microphone", "Dictate this comment");
      mic.classList.add("annot-mic");
      mic.addEventListener("click", () => {
        activeField = textarea;
        activeMic = mic;
        textarea.focus();
        voice.toggle();
      });
      body.appendChild(mic);
    }

    row.append(head, body);
    if (focus) {
      queueMicrotask(() => textarea.focus());
    }
    return row;
  }

  setMode("markup");
  setCategory("highlight");
  setTool("highlight");
  renderPanel();

  return {
    onAnnotate(annotation) {
      renderPanel(annotation.id);
    },
  };
}
