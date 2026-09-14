/**
 * SciTeX Writer entry point — Monaco LaTeX editor with section navigation.
 * Bundled by Vite; output lands at `static/writer/assets/index.js` and is
 * loaded by `editor.html` as a module script.
 */

import {
  MonacoEditor,
  registerLatexLanguage,
  waitForMonaco,
} from "@scitex/ui/monaco-editor";

import { getFile, saveFile, projectInfo } from "./api";
import type { SectionEntry } from "./api";
import { SectionTabs } from "./sections";
import { countWords, mountToolbar } from "./toolbar";
import { PDFViewer } from "./pdf-viewer";
import { type AnnotationUIHandle, mountAnnotationUI } from "./annotation-ui";
import { CompileController } from "./compile";
import { InsertPanel } from "./insert-panel";
import { DetailsPanel } from "./details-panel";
import { registerCiteProviders } from "./cite-completion";
import { ClaimsTab } from "./claims-tab";
import {
  cyclePdfThemeMode,
  getPdfThemeMode,
  pdfThemeIcon,
  pdfThemeLabel,
} from "./pdf-theme";

const SAVE_DEBOUNCE_MS = 800;

async function bootstrap(): Promise<void> {
  const root = document.querySelector<HTMLElement>(".writer-app");
  if (!root) {
    console.warn("[writer] .writer-app container not found — aborting init");
    return;
  }

  // Monaco needs LaTeX registered before we create any editor
  const monaco = await waitForMonaco();
  registerLatexLanguage(monaco);
  registerCiteProviders(monaco);

  const editorContainer = root.querySelector<HTMLElement>("#editor-container");
  if (!editorContainer) return;

  // Replace the welcome message with the Monaco host
  editorContainer.innerHTML =
    '<div id="monaco-host" class="monaco-host"></div>';
  const host = editorContainer.querySelector<HTMLElement>("#monaco-host")!;

  const editor = new MonacoEditor({
    container: host,
    language: "latex",
    value: "% Loading…",
    lineNumbers: "on",
    wordWrap: "on",
    minimap: true,
    fontSize: 14,
    tabSize: 2,
  });
  await editor.initialize();

  // Force layout once after the shell has stabilised — automaticLayout
  // via ResizeObserver misses the initial container-size flip when
  // shell panes are hidden via CSS after Monaco init. Without this,
  // line numbers render at the wrong Y offset.
  requestAnimationFrame(() => {
    editor.getEditor()?.layout();
  });

  // Toolbar wiring
  const tabsEl = root.querySelector<HTMLElement>("#section-tabs");
  const sections = tabsEl
    ? new SectionTabs(tabsEl, (section) => {
        void loadSection(section);
      })
    : null;

  // PDF viewer + annotation UI (ADR 0001). The viewer produces marks into its
  // AnnotationStore; the UI (mode switch, domain buttons, comment box, voice,
  // markdown export) drives it and renders the comment thread. onAnnotate is
  // forwarded through a mutable handle so the two can be wired in either order.
  const pdfContainer = root.querySelector<HTMLElement>("#pdf-container");
  let annotationUI: AnnotationUIHandle | null = null;
  const pdf = pdfContainer
    ? new PDFViewer({
        container: pdfContainer,
        onAnnotate: (annotation) => annotationUI?.onAnnotate(annotation),
      })
    : null;
  pdf?.renderPlaceholder();

  const annotToolbar = root.querySelector<HTMLElement>("#annot-toolbar");
  const annotPanel = root.querySelector<HTMLElement>("#annot-panel");
  if (pdf && annotToolbar && annotPanel) {
    annotationUI = mountAnnotationUI({
      toolbar: annotToolbar,
      panel: annotPanel,
      controller: pdf,
    });
  }

  // Details right panel (Hints / Compilation / Overleaf / Prism / Project /
  // Shortcuts). Hint rows with a source location become click-to-jump anchors:
  // file+line reveals the line in Monaco (switching sections if needed); page
  // scrolls the PDF viewer.
  const detailsEl = root.querySelector<HTMLElement>("#details-panel");
  const details = detailsEl
    ? new DetailsPanel(detailsEl, {
        onJumpToLocation: (file, line) => {
          void jumpToSourceLocation(file, line);
        },
        onJumpToPage: (page) => {
          pdf?.goToPage(page);
        },
      })
    : null;

  // Compile controller — pushes lamp status into the Details panel so
  // Compilation-Preview / Compilation-Full show live status dots.
  const compile = pdf
    ? new CompileController({
        lamp: root.querySelector<HTMLElement>("#compile-lamp"),
        logContent: root.querySelector<HTMLElement>("#log-content"),
        logPanel: root.querySelector<HTMLElement>("#log-panel"),
        toggleLogBtn: root.querySelector<HTMLElement>("#btn-toggle-log"),
        closeLogBtn: root.querySelector<HTMLElement>("#btn-close-log"),
        compileBtn: root.querySelector<HTMLElement>("#btn-compile"),
        modeToggleBtn: root.querySelector<HTMLElement>("#btn-compile-mode"),
        pdf,
        getDocType: () =>
          root.querySelector<HTMLSelectElement>("#doc-type-select")?.value ||
          "manuscript",
        onStatusChange: (mode, status) => {
          details?.setCompileStatus(mode, status);
        },
      })
    : null;

  // Keyboard shortcut icon → expand the Shortcuts section in Details
  root
    .querySelector<HTMLElement>("#btn-show-shortcuts")
    ?.addEventListener("click", () => {
      details?.openSection("shortcuts");
    });

  // Download PDF
  root
    .querySelector<HTMLElement>("#btn-pdf-download")
    ?.addEventListener("click", () => {
      const docType =
        root.querySelector<HTMLSelectElement>("#doc-type-select")?.value ||
        "manuscript";
      const a = document.createElement("a");
      a.href =
        `/api/pdf?doc_type=${encodeURIComponent(docType)}` +
        `&working_dir=${encodeURIComponent(
          (root as HTMLElement).dataset.projectDir || "",
        )}&download=1&t=${Date.now()}`;
      a.download = `${docType}.pdf`;
      document.body.appendChild(a);
      a.click();
      a.remove();
    });

  const toolbar = mountToolbar(root, {
    onDocType: async (docType) => {
      await sections?.load(docType);
      await pdf?.load(docType);
      insert?.invalidate(docType);
    },
    onFontSize: (size) => {
      editor.getEditor()?.updateOptions({ fontSize: size });
    },
    onTheme: () => {
      // scitex-ui's theme observer handles Monaco — nothing else needed
    },
  });

  root
    .querySelector<HTMLElement>("#btn-refresh-pdf")
    ?.addEventListener("click", async () => {
      const dt =
        root.querySelector<HTMLSelectElement>("#doc-type-select")?.value ||
        "manuscript";
      await pdf?.load(dt);
    });

  root
    .querySelector<HTMLElement>("#btn-pdf-zoom-in")
    ?.addEventListener("click", () => pdf?.setZoom(0.1));
  root
    .querySelector<HTMLElement>("#btn-pdf-zoom-out")
    ?.addEventListener("click", () => pdf?.setZoom(-0.1));
  root
    .querySelector<HTMLElement>("#btn-pdf-fit")
    ?.addEventListener("click", () => pdf?.setFitWidth());

  // PDF theme override (auto / light / dark) — separate from UI theme.
  const pdfThemeBtn = root.querySelector<HTMLElement>("#btn-pdf-theme");
  if (pdfThemeBtn) {
    const syncBtn = () => {
      const mode = getPdfThemeMode();
      const icon = pdfThemeBtn.querySelector<HTMLElement>("i");
      if (icon) icon.className = `fas ${pdfThemeIcon(mode)}`;
      pdfThemeBtn.setAttribute("title", pdfThemeLabel(mode));
    };
    syncBtn();
    pdfThemeBtn.addEventListener("click", () => {
      cyclePdfThemeMode();
      syncBtn();
    });
  }

  // silence unused warnings until richer use later
  void compile;

  // Insert panel (cite/fig/table/history icon bar)
  const insertBar = root.querySelector<HTMLElement>("#insert-bar");
  const insertPanel = root.querySelector<HTMLElement>("#insert-panel");
  const insert =
    insertBar && insertPanel
      ? new InsertPanel({
          bar: insertBar,
          panel: insertPanel,
          getDocType: () =>
            root.querySelector<HTMLSelectElement>("#doc-type-select")?.value ||
            "manuscript",
          insertAtCursor: (snippet) => {
            const mEditor = editor.getEditor();
            if (!mEditor) return;
            const selection = mEditor.getSelection();
            mEditor.executeEdits("insert-panel", [
              {
                range: selection,
                text: snippet,
                forceMoveMarkers: true,
              },
            ]);
            mEditor.focus();
          },
        })
      : null;

  // Citation drop: drag a card into the Monaco host → insert at drop position.
  // Only accept our own custom MIME type so arbitrary text drops (e.g. a
  // paragraph from another tab) don't go through this path.
  const CITE_MIME = "application/x-scitex-cite";
  host.addEventListener("dragover", (e) => {
    if (e.dataTransfer?.types.includes(CITE_MIME)) {
      e.preventDefault();
      e.dataTransfer.dropEffect = "copy";
    }
  });
  host.addEventListener("drop", (e) => {
    if (!e.dataTransfer?.types.includes(CITE_MIME)) return;
    const payload = e.dataTransfer.getData(CITE_MIME);
    if (!payload || !payload.startsWith("\\cite")) return;
    e.preventDefault();
    const mEditor = editor.getEditor();
    if (!mEditor) return;
    const target = mEditor.getTargetAtClientPoint?.(e.clientX, e.clientY);
    const position = target?.position || mEditor.getPosition();
    if (!position) return;
    mEditor.executeEdits("cite-drop", [
      {
        range: {
          startLineNumber: position.lineNumber,
          endLineNumber: position.lineNumber,
          startColumn: position.column,
          endColumn: position.column,
        },
        text: payload,
        forceMoveMarkers: true,
      },
    ]);
    mEditor.focus();
  });

  // Declare state BEFORE any loadSection trigger (TDZ guard).
  let currentPath: string | null = null;
  let saveTimer: number | null = null;
  let isLoadingFile = false;

  // Claims tab (Living Paper #133): render claim cards with verification
  // badges + DAG; clicking "Find in source" searches the current file for
  // \vclaim{<id>} and reveals that Monaco line.
  const claimsMount = root.querySelector<HTMLElement>("#claims-list");
  const claimsTab = claimsMount
    ? new ClaimsTab({
        mount: claimsMount,
        onJumpToClaim: (claimId) => {
          const mEditor = editor.getEditor();
          if (!mEditor) return;
          const model = mEditor.getModel();
          if (!model) return;
          const matches = model.findMatches(
            `\\vclaim{${claimId}}`,
            false,
            false,
            true,
            null,
            false,
          ) as Array<{ range: unknown }>;
          if (matches.length === 0) return;
          const range = (matches[0] as { range: { startLineNumber: number } })
            .range;
          mEditor.revealLineInCenter(range.startLineNumber);
          mEditor.setPosition({
            lineNumber: range.startLineNumber,
            column: 1,
          });
          mEditor.focus();
        },
      })
    : null;

  // Populate when the Claims tab is first opened (lazy — avoids blocking
  // editor boot on the claims-metadata + clew-verify round-trip).
  let claimsLoaded = false;
  root
    .querySelector<HTMLElement>('.preview-tab[data-view="claims"]')
    ?.addEventListener("click", () => {
      if (!claimsLoaded && claimsTab) {
        claimsLoaded = true;
        void claimsTab.render();
      }
    });

  // After compile, invalidate so the next Claims-tab open re-fetches, and
  // refresh the manuscript-hints feed (the compile just rewrote it).
  compile?.onAfterCompile?.(() => {
    if (claimsLoaded) void claimsTab?.refresh();
    void details?.refreshHints();
  });

  // Initial load: discover doc types then load the first section of the first type
  let info: Awaited<ReturnType<typeof projectInfo>>;
  try {
    info = await projectInfo();
  } catch (err) {
    console.error("[writer] projectInfo failed", err);
    return;
  }
  const initialDocType = info.doc_types[0] || "manuscript";
  const docSelect = root.querySelector<HTMLSelectElement>("#doc-type-select");
  if (docSelect) docSelect.value = initialDocType;
  await sections?.load(initialDocType);
  await pdf?.load(initialDocType);

  async function loadSection(section: SectionEntry): Promise<void> {
    try {
      const file = await getFile(section.path);
      currentPath = section.path;
      isLoadingFile = true;
      try {
        editor.setValue(file.content);
      } finally {
        isLoadingFile = false;
      }
      updateWordCount();
      const currentFileEl = root?.querySelector<HTMLElement>("#current-file");
      if (currentFileEl) currentFileEl.textContent = file.name;
      toolbar.setSavedStatus("saved");
    } catch (err) {
      console.error("[writer] loadSection failed", err);
      toolbar.setSavedStatus("error");
    }
  }

  // Reveal a hint's source location: switch to the section that owns the file
  // (if it differs from the open one and can be resolved), then reveal the
  // line in Monaco. Reuses the same reveal path as the Claims-tab jump.
  async function jumpToSourceLocation(
    file: string,
    line: number,
  ): Promise<void> {
    const mEditor = editor.getEditor();
    if (!mEditor) return;
    const match = sections?.findByFile(file);
    if (match && match.path !== currentPath) {
      await loadSection(match);
      sections?.markActive(match);
    }
    mEditor.revealLineInCenter(line);
    mEditor.setPosition({ lineNumber: line, column: 1 });
    mEditor.focus();
  }

  function updateWordCount(): void {
    toolbar.setWordCount(countWords(editor.getValue()));
  }

  const mEditor = editor.getEditor();
  mEditor?.onDidChangeModelContent(() => {
    updateWordCount();
    // Showing a file's own content is not an edit; saving it back rewrote the file on every open.
    if (isLoadingFile) return;
    toolbar.setSavedStatus("saving");
    if (saveTimer) window.clearTimeout(saveTimer);
    saveTimer = window.setTimeout(flushSave, SAVE_DEBOUNCE_MS);
  });

  async function flushSave(): Promise<void> {
    if (!currentPath) return;
    try {
      await saveFile(currentPath, editor.getValue());
      toolbar.setSavedStatus("saved");
    } catch (err) {
      console.error("[writer] save failed", err);
      toolbar.setSavedStatus("error");
    }
  }

  window.addEventListener("keydown", (event) => {
    if ((event.ctrlKey || event.metaKey) && event.key === "s") {
      event.preventDefault();
      if (saveTimer) window.clearTimeout(saveTimer);
      void flushSave();
    }
  });

  // Shell sets body.no-transition to prevent FOUC jitter; it normally
  // strips the class after JS loads, but standalone mode doesn't run
  // that code path. Remove it on next paint so our curtain-slide
  // transitions (insert-panel, details-pane, theme icon rotate) can run.
  requestAnimationFrame(() => {
    requestAnimationFrame(() => {
      document.body.classList.remove("no-transition");
    });
  });
}

void bootstrap();
