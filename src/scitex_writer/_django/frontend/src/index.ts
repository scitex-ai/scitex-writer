/**
 * SciTeX Writer entry point — Monaco LaTeX editor with section navigation.
 * Bundled by Vite; output lands at `static/writer/assets/index.js` and is
 * loaded by `editor.html` as a module script.
 */

import {
  MonacoEditor,
  registerLatexLanguage,
  waitForMonaco,
} from "@scitex/sdk/ui/monaco-editor";

import { PROJECT_DIR, getFile, saveFile, projectInfo } from "./api";
import type { SectionEntry } from "./api";
import { SectionTabs, humanize } from "./sections";
import { countWords, mountToolbar } from "./toolbar";
import { wireHostThemeToggle } from "./host-theme-fallback";
import { MobileLayout, isMobileViewport } from "./mobile";
import { PDFViewer } from "./pdf-viewer";
import { type AnnotationUIHandle, mountAnnotationUI } from "./annotation-ui";
import { CompileController } from "./compile";
import { InsertPanel, type InsertPaneId } from "./insert-panel";
import { DetailsPanel } from "./details-panel";
import { controlsTranslate } from "./controls-i18n";
import { registerCiteProviders } from "./cite-completion";
import { ClaimsTab } from "./claims-tab";
import { mountPdfMenu } from "./pdf-menu";
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
  const documentType = root.querySelector<HTMLSelectElement>("#doc-type-select");
  if (documentType) {
    documentType.title = controlsTranslate("documentType");
    documentType.setAttribute("aria-label", controlsTranslate("documentType"));
  }

  // Host-injected theme row (hub global header on hub-served leaf pages):
  // wire it when the host bundle that owns it is absent, otherwise the row
  // is a dead button. No-op on standalone deployments (no such element).
  wireHostThemeToggle();

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

  // Operator 2026-10-23: writer-scoped Monaco themes matching the shell
  // chrome (cool GitHub-dark neutrals; paper-white light). Token rules
  // mirror the shared scitex-* LaTeX rules so highlighting stays
  // identical — only the editor/gutter surfaces move. (The SDK module
  // does not export its rule lists, hence the local copy; if the SDK
  // lane adopts these surfaces fleet-wide, this block goes away.)
  // Registered after the SDK observer, so this wins each data-theme
  // toggle deterministically.
  const monacoNs = editor.getMonaco?.();
  if (monacoNs) {
    monacoNs.editor.defineTheme("writer-dark", {
      base: "vs-dark",
      inherit: true,
      rules: [
        { token: "comment.latex", foreground: "6A9955", fontStyle: "italic" },
        { token: "keyword.latex", foreground: "569CD6" },
        { token: "keyword.control.latex", foreground: "C586C0" },
        { token: "keyword.section.latex", foreground: "DCDCAA", fontStyle: "bold" },
        { token: "keyword.math.latex", foreground: "9CDCFE" },
        { token: "string.math.latex", foreground: "CE9178" },
        { token: "type.identifier.latex", foreground: "4EC9B0" },
        { token: "delimiter.curly.latex", foreground: "FFD700" },
        { token: "delimiter.square.latex", foreground: "DA70D6" },
        { token: "number.latex", foreground: "B5CEA8" },
        { token: "operator.latex", foreground: "D4D4D4" },
      ],
      colors: {
        // Operator 2026-10-23: match the app's bluish-gray surface
        // (--bg-secondary / --toolbar-bg, #161b22) instead of the
        // neutral-black #0d1117, so the editor sits flat against the
        // toolbar + preview chrome with no black-box seam. Monaco
        // needs a literal hex — keep in sync with editor.css.
        "editor.background": "#161b22",
        "editorGutter.background": "#161b22",
      },
    });
    monacoNs.editor.defineTheme("writer-light", {
      base: "vs",
      inherit: true,
      rules: [
        { token: "comment.latex", foreground: "008000", fontStyle: "italic" },
        { token: "keyword.latex", foreground: "3366aa" },
        { token: "keyword.control.latex", foreground: "7744aa" },
        { token: "keyword.section.latex", foreground: "795E26", fontStyle: "bold" },
        { token: "keyword.math.latex", foreground: "001080" },
        { token: "string.math.latex", foreground: "A31515" },
        { token: "type.identifier.latex", foreground: "267F99" },
        { token: "delimiter.curly.latex", foreground: "B8860B" },
        { token: "delimiter.square.latex", foreground: "800080" },
        { token: "number.latex", foreground: "098658" },
        { token: "operator.latex", foreground: "333333" },
      ],
      colors: {
        "editor.background": "#ffffff",
        "editorGutter.background": "#f8f7f5",
      },
    });
    const applyWriterTheme = (): void => {
      const dark =
        document.documentElement.getAttribute("data-theme") === "dark";
      editor.getEditor()?.updateOptions({
        theme: dark ? "writer-dark" : "writer-light",
      });
    };
    applyWriterTheme();
    new MutationObserver(applyWriterTheme).observe(document.documentElement, {
      attributes: true,
      attributeFilter: ["data-theme"],
    });
  }

  // Operator 2026-10-23: ctrl+wheel (or the middle button held while
  // wheeling) steps the editor font through the toolbar select's own
  // sizes (desktop IDE behavior). Reusing the select keeps the control
  // and the editor in sync with no new state. Middle-drag scrolling (no
  // button held) is untouched — only an explicit hold zooms.
  const fontSizeEl = root.querySelector<HTMLSelectElement>(
    "#font-size-select",
  );
  let middleZoomHeld = false;
  editorContainer.addEventListener("mousedown", (event: MouseEvent) => {
    if (event.button === 1) {
      middleZoomHeld = true;
      event.preventDefault();
    }
  });
  window.addEventListener("mouseup", (event: MouseEvent) => {
    if (event.button === 1) middleZoomHeld = false;
  });
  editorContainer.addEventListener(
    "wheel",
    (event: WheelEvent) => {
      if (
        (!event.ctrlKey && !middleZoomHeld) ||
        !fontSizeEl ||
        fontSizeEl.options.length === 0
      )
        return;
      event.preventDefault();
      event.stopPropagation();
      const step = event.deltaY < 0 ? 1 : -1;
      const next = Math.min(
        fontSizeEl.options.length - 1,
        Math.max(0, fontSizeEl.selectedIndex + step),
      );
      if (next !== fontSizeEl.selectedIndex) {
        fontSizeEl.selectedIndex = next;
        fontSizeEl.dispatchEvent(new Event("change"));
      }
    },
    // Monaco consumes bubbling wheel events; capture the explicit font
    // gesture before its scroll layer so the select and editor stay in sync.
    { passive: false, capture: true },
  );

  // Toolbar wiring
  const tabsEl = root.querySelector<HTMLElement>("#section-tabs");
  const mobileListEl = root.querySelector<HTMLElement>(
    "#writer-mobile-section-list",
  );
  const sections = tabsEl
    ? new SectionTabs(
        tabsEl,
        (section) => {
          void loadSection(section);
          // Tapping a file on a phone means "open it": the pane the writer
          // wanted is the editor, not the list they picked from.
          if (isMobileViewport()) mobile.setPane("editor");
        },
        { listContainer: mobileListEl ?? undefined },
      )
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
      menu: {
        button: root.querySelector<HTMLButtonElement>("#btn-pdf-menu")!,
        list: root.querySelector<HTMLElement>("#pdf-menu-list")!,
      },
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
        logTitle: root.querySelector<HTMLElement>("#log-title"),
        diagnosticsContent: root.querySelector<HTMLElement>("#log-diagnostics"),
        fullLogToggleBtn: root.querySelector<HTMLElement>("#btn-toggle-full-log"),
        onJumpToLocation: (file, line) => {
          void jumpToSourceLocation(file, line);
        },
        toggleLogBtn: root.querySelector<HTMLElement>("#btn-toggle-log"),
        closeLogBtn: root.querySelector<HTMLElement>("#btn-close-log"),
        compileBtn: root.querySelector<HTMLElement>("#btn-compile"),
        modeToggleBtn: root.querySelector<HTMLElement>("#btn-compile-mode"),
        modeButtons: Array.from(root.querySelectorAll<HTMLButtonElement>("[data-compile-mode]")),
        modeSelect: root.querySelector<HTMLSelectElement>("#compile-mode-select"),
        pdf,
        getSection: () => currentPath ? { path: currentPath, content: editor.getValue() } : null,
        getDocType: () =>
          root.querySelector<HTMLSelectElement>("#doc-type-select")?.value ||
          "manuscript",
        onStatusChange: (mode, status) => {
          details?.setCompileStatus(mode, status);
        },
      })
    : null;

  // Keyboard shortcut icon → reveal the panel, expand the Shortcuts section
  root
    .querySelector<HTMLElement>("#btn-show-shortcuts")
    ?.addEventListener("click", () => {
      detailsEl?.classList.remove("writer-panel-hidden");
      details?.openSection("shortcuts");
    });

  // Side panel toggle (manuscript/abstract toolbar row): the pane is dropped
  // by default — this button brings it back. Revealing also refreshes the
  // hints feed so a reopened panel never shows stale quiet.
  root
    .querySelector<HTMLElement>("#btn-toggle-panel")
    ?.addEventListener("click", () => {
      const hidden = detailsEl?.classList.toggle("writer-panel-hidden") ?? true;
      if (!hidden) void details?.refreshHints();
    });

  // Phone layout (<=768px): Files / Editor / PDF, one at a time. Built after
  // the viewer and the compile controller so a pane change can re-lay out
  // what they own. No bottom action bar: Save/Log/Compile live in the
  // toolbar row on every viewport, so there is nothing to forward here.
  const mobile = new MobileLayout(root, {
    onPaneChange: (pane) => {
      if (!isMobileViewport()) return;
      if (pane === "editor") {
        compactPhoneEditor();
        editor.getEditor()?.layout();
      }
      if (pane === "preview") pdf?.setFitWidth();
    },
  });

  // Download PDF
  root
    .querySelector<HTMLElement>("#btn-pdf-download")
    ?.addEventListener("click", () => {
      const docType =
        root.querySelector<HTMLSelectElement>("#doc-type-select")?.value ||
        "manuscript";
      const a = document.createElement("a");
      if (!pdf?.downloadUrl) return;
      a.href = pdf.downloadUrl;
      a.download = compile?.isSectionPreview
        ? `${currentPath?.split("/").pop()?.replace(/\.tex$/, "") || "section"}.pdf`
        : `${docType}.pdf`;
      document.body.appendChild(a);
      a.click();
      a.remove();
    });

  const toolbar = mountToolbar(root, {
    onDocType: async (docType) => {
      await sections?.load(docType);
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
      await compile?.sectionChanged();
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
      pdfThemeBtn.setAttribute("title", `${pdfThemeLabel(mode)} (Alt+T)`);
    };
    syncBtn();
    pdfThemeBtn.addEventListener("click", () => {
      cyclePdfThemeMode();
      syncBtn();
    });
  }

  // CCT4485: PDF ops live in the hamburger menu; shortcuts work globally.
  mountPdfMenu(root);

  // silence unused warnings until richer use later
  void compile;

  // Insert panel (cite/fig/table/history icon bar)
  const insertBar = root.querySelector<HTMLElement>("#insert-bar");
  const insertPanel = root.querySelector<HTMLElement>("#insert-panel");

  // Operator 2026-10-23: one switched large pane. The rail is the ONE
  // selector — PDF/Cite/Fig/Table/Collab/History all switch through
  // showPreviewView (PDF renders in #pdf-view, the rest in #insert-view;
  // no expand beside the editor). Claims stays as a secondary tab until
  // the live-paper example project lands. Re-clicking any active rail
  // icon returns to PDF.
  type PreviewView = "pdf" | "claims" | InsertPaneId;
  let previewView: PreviewView = "pdf";
  const previewViewId: Record<PreviewView, string> = {
    pdf: "pdf-view",
    claims: "claims-view",
    cite: "insert-view",
    fig: "insert-view",
    table: "insert-view",
    collab: "insert-view",
    history: "insert-view",
  };
  // Claims lazy-load state, assigned next to the ClaimsTab construction
  // below (single `let` pair — showPreviewView only *runs* on user clicks,
  // after full bootstrap, so no TDZ issue at runtime).
  let claimsLoaded = false;
  let claimsTab: ClaimsTab | null = null;
  function showPreviewView(view: PreviewView): void {
    previewView = view;
    // Claims lazy-load lives on the single choke point, not on a tab
    // element — the rail is the selector now. First open of the claims
    // view renders; later opens refresh only after a compile.
    if (view === "claims" && !claimsLoaded && claimsTab) {
      claimsLoaded = true;
      void claimsTab.render();
    }
    // Operator 2026-10-24: close FIRST. InsertPanel.close() strips .active
    // from every rail button, so running it after the toggles below wiped
    // the PDF highlight (pdf/claims never looked selected). Closing before
    // the toggles lets the .active assignment stick.
    if (view === "pdf" || view === "claims") insert?.close();
    root
      ?.querySelectorAll<HTMLElement>(".preview-view")
      .forEach((v) =>
        v.classList.toggle("active", v.id === previewViewId[view]),
      );
    root
      ?.querySelectorAll<HTMLElement>(".preview-tab")
      .forEach((t) =>
        t.classList.toggle(
          "active",
          (t as HTMLElement).dataset.view === view,
        ),
      );
    root
      ?.querySelectorAll<HTMLElement>(".insert-bar-btn")
      .forEach((b) =>
        b.classList.toggle("active", (b as HTMLElement).dataset.pane === view),
      );
  }
  let insert: InsertPanel | null = null;
  if (insertBar && insertPanel) {
    const panel = new InsertPanel({
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
          onSelect: (pane) => {
            if (previewView === pane) {
              insert?.close();
              showPreviewView("pdf");
            } else {
              insert?.open(pane);
              showPreviewView(pane);
            }
          },
        });
    insert = panel;
    showPreviewView("pdf");
  }
  root
    ?.querySelectorAll<HTMLElement>('.preview-tab[data-view="claims"]')
    .forEach((t) =>
      t.addEventListener("click", () => showPreviewView("claims")),
    );

  // Insert drop: drag a card/item into the Monaco host → insert at drop
  // position. Only accept our own custom MIME type so arbitrary text
  // drops (e.g. a paragraph from another tab) don't go through this path.
  // Cite cards carry \cite{...}; figure/table items carry \ref{...}.
  const INSERT_MIME = "application/x-scitex-insert";
  const CITE_MIME = "application/x-scitex-cite"; // legacy, kept reading
  host.addEventListener("dragover", (e) => {
    if (
      e.dataTransfer?.types.includes(INSERT_MIME) ||
      e.dataTransfer?.types.includes(CITE_MIME)
    ) {
      e.preventDefault();
      e.dataTransfer.dropEffect = "copy";
    }
  });
  host.addEventListener("drop", (e) => {
    const types = e.dataTransfer?.types ?? [];
    const mime = types.includes(INSERT_MIME)
      ? INSERT_MIME
      : types.includes(CITE_MIME)
        ? CITE_MIME
        : null;
    if (!mime) return;
    const payload = e.dataTransfer!.getData(mime);
    if (
      !payload ||
      !(payload.startsWith("\\cite") || payload.startsWith("\\ref"))
    )
      return;
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
  let sectionLoadSequence = 0;
  let saveTimer: number | null = null;
  let isLoadingFile = false;

  // Claims tab (Living Paper #133): render claim cards with verification
  // badges + DAG; clicking "Find in source" searches the current file for
  // \vclaim{<id>} and reveals that Monaco line. Assigned into the pair
  // declared next to showPreviewView above (single choke point).
  const claimsMount = root.querySelector<HTMLElement>("#claims-list");
  claimsTab = claimsMount
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

  // After compile, invalidate so the next claims-view open re-fetches, and
  // refresh the manuscript-hints feed (the compile just rewrote it).
  compile?.onAfterCompile?.(() => {
    if (claimsLoaded) void claimsTab?.refresh();
    void details?.refreshHints();
  });

  // Initial load: discover doc types then load the first section of the first type.
  // The shell declares data-project-dir="" when no project resolved (editor_page
  // renders project_dir only for a resolved project; api.ts PROJECT_DIR reads
  // the same dataset, default ""). With no declared project, initialize the
  // empty editor state WITHOUT asking project-info: the API genuinely 400s
  // there, and that outcome is expected, not an error. Only the automatic
  // project-dependent loads are gated; every handler below keeps running.
  // A declared project keeps the exact previous behavior, including the
  // console error on genuine failure.
  if (!PROJECT_DIR) {
    editor.setValue("");
  } else {
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
  // The selected section loads its own isolated preview through loadSection.
  }

  /* Operator 2026-10-23: the Draft option names the open section
   * (e.g. "Abstract") and Full names the document (e.g. "Manuscript")
   * instead of the generic static labels. Runs on every section load,
   * so tab switches, hint jumps and doc-type reloads all stay current. */
  function updateCompileModeLabels(section: SectionEntry): void {
    const modeSelect = root?.querySelector<HTMLSelectElement>(
      "#compile-mode-select",
    );
    const docLabel =
      root
        ?.querySelector<HTMLSelectElement>("#doc-type-select")
        ?.selectedOptions[0]?.textContent?.trim() || "Manuscript";
    const preview = modeSelect?.querySelector<HTMLOptionElement>(
      'option[value="preview"]',
    );
    const full = modeSelect?.querySelector<HTMLOptionElement>(
      'option[value="full"]',
    );
    if (preview) preview.textContent = humanize(section.name);
    if (full) full.textContent = docLabel;
  }

  async function loadSection(section: SectionEntry): Promise<void> {
    const sequence = ++sectionLoadSequence;
    if (saveTimer) {
      window.clearTimeout(saveTimer);
      saveTimer = null;
      await flushSave();
      if (sequence !== sectionLoadSequence) return;
    }
    currentPath = null;
    compile?.sectionPending();
    updateCompileModeLabels(section);
    try {
      const file = await getFile(section.path);
      if (sequence !== sectionLoadSequence) return;
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
      void compile?.sectionChanged();
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

  /**
   * Monaco's desktop chrome costs a 390px viewport real code width: the gutter,
   * the glyph margin (~20px of breakpoint dots), the folding arrows and the
   * minimap together leave roughly half the width for the manuscript. Applied
   * whenever the phone layout is entered, with the numbers still readable
   * (3 line-number chars covers a 3-digit LaTeX file).
   */
  function compactPhoneEditor(): void {
    if (!isMobileViewport()) return;
    editor.getEditor()?.updateOptions({
      minimap: { enabled: false },
      glyphMargin: false,
      folding: false,
      lineDecorationsWidth: 2,
      lineNumbersMinChars: 3,
      scrollBeyondLastLine: false,
    });
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
    saveTimer = null;
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
