/**
 * Compile diagnostics list — one row per error/warning the server's LaTeX log
 * analyser found: severity, clickable file:line, message, excerpt, next step.
 */

import { diagnosticsTranslate as t } from "./compile-diagnostics-i18n";

export type DiagnosticSeverity = "error" | "warning";

export interface DiagnosticItem {
  cause: string;
  severity: DiagnosticSeverity;
  message: string;
  hint: string;
  context: string;
  file: string | null;
  line: number | null;
}

export interface CompileDiagnostics {
  status: { kind: string; code: number | string; message: string };
  report: {
    package: string;
    ok: boolean | null;
    checks: Array<{
      name: string;
      ok: boolean | null;
      detail: string;
      hint: string | null;
    }>;
    summary: string;
  };
  items: DiagnosticItem[];
  log_path: string | null;
}

export type JumpToLocation = (file: string, line: number) => void;

function element<K extends keyof HTMLElementTagNameMap>(
  tag: K,
  className: string,
  text?: string,
): HTMLElementTagNameMap[K] {
  const node = document.createElement(tag);
  node.className = className;
  if (text !== undefined) node.textContent = text;
  return node;
}

function renderLocation(
  item: DiagnosticItem,
  onJump: JumpToLocation | undefined,
): HTMLElement | null {
  if (!item.file) return null;
  const location = item.line ? `${item.file}:${item.line}` : item.file;
  if (!item.line || !onJump) {
    return element("span", "compile-diag-location", location);
  }
  const link = element("a", "compile-diag-location compile-diag-jump", location);
  link.href = "#";
  link.title = t("jumpTo", { location });
  link.dataset.jumpFile = item.file;
  link.dataset.jumpLine = String(item.line);
  const line = item.line;
  const file = item.file;
  link.addEventListener("click", (event) => {
    event.preventDefault();
    onJump(file, line);
  });
  return link;
}

function renderItem(
  item: DiagnosticItem,
  onJump: JumpToLocation | undefined,
): HTMLElement {
  const row = element("li", `compile-diag-item compile-diag-${item.severity}`);
  row.dataset.cause = item.cause;

  const head = element("div", "compile-diag-head");
  head.appendChild(
    element(
      "span",
      "compile-diag-badge",
      item.severity === "error" ? t("error") : t("warning"),
    ),
  );
  const location = renderLocation(item, onJump);
  if (location) head.appendChild(location);
  head.appendChild(element("span", "compile-diag-cause", item.cause));
  row.appendChild(head);

  row.appendChild(element("div", "compile-diag-message", item.message));
  if (item.context) {
    row.appendChild(element("pre", "compile-diag-context", item.context));
  }
  const hint = element("div", "compile-diag-hint");
  hint.appendChild(element("span", "compile-diag-hint-label", `${t("hint")}: `));
  hint.appendChild(document.createTextNode(item.hint));
  row.appendChild(hint);
  return row;
}

/**
 * Replace `container`'s content with the diagnostics summary and list.
 * Returns the number of rendered items (0 when there is nothing to show).
 */
export function renderCompileDiagnostics(
  container: HTMLElement,
  diagnostics: CompileDiagnostics | null | undefined,
  options: { success: boolean; onJump?: JumpToLocation },
): number {
  container.replaceChildren();
  const items = diagnostics?.items ?? [];
  if (items.length === 0) {
    if (!options.success) {
      container.appendChild(
        element("div", "compile-diag-summary compile-diag-error", t("noDetails")),
      );
      return 1;
    }
    return 0;
  }

  const errors = items.filter((item) => item.severity === "error").length;
  const warnings = items.length - errors;
  const counts = [
    errors ? t("errorCount", { n: errors }) : "",
    warnings ? t("warningCount", { n: warnings }) : "",
  ].filter(Boolean);
  const title = !options.success
    ? t("compileFailed")
    : errors
      ? t("compiledWithErrors")
      : t("compiledWithWarnings");
  const tone = !options.success || errors ? "error" : "warning";
  container.appendChild(
    element(
      "div",
      `compile-diag-summary compile-diag-${tone}`,
      `${title} — ${counts.join(", ")}`,
    ),
  );

  const list = element("ul", "compile-diag-list");
  for (const item of items) list.appendChild(renderItem(item, options.onJump));
  container.appendChild(list);
  return items.length;
}
