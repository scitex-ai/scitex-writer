/**
 * EN/JA strings for the compile diagnostics panel.
 *
 * Same contract as scitex-ui's client i18n (`ts/_base/i18n.ts`): English is
 * the default column, Japanese is complete, and the column is chosen from the
 * document's `<html lang>`, which the shell renders from the host language.
 */

export const DIAGNOSTICS_LANGUAGES = ["en", "ja"] as const;
export type DiagnosticsLanguage = (typeof DIAGNOSTICS_LANGUAGES)[number];

export const DIAGNOSTICS_STRINGS = {
  en: {
    panelTitle: "Compilation Log",
    compileFailed: "Compilation failed",
    compiledWithWarnings: "Compiled with warnings",
    compiledWithErrors: "PDF produced, but LaTeX reported errors",
    errorCount: "{n} error(s)",
    warningCount: "{n} warning(s)",
    error: "Error",
    warning: "Warning",
    jumpTo: "Jump to {location}",
    hint: "Next step",
    showFullLog: "Show full log",
    hideFullLog: "Hide full log",
    noDetails:
      "The compile failed and no log was returned. Open the full log or try again.",
    requestFailed: "The compile request failed: {error}",
    requestFailedHint:
      "The server did not accept or answer the request: reload the page (your session may have expired) and compile again",
  },
  ja: {
    panelTitle: "コンパイルログ",
    compileFailed: "コンパイルに失敗しました",
    compiledWithWarnings: "警告付きでコンパイルしました",
    compiledWithErrors: "PDF は生成されましたが、LaTeX がエラーを報告しました",
    errorCount: "エラー {n} 件",
    warningCount: "警告 {n} 件",
    error: "エラー",
    warning: "警告",
    jumpTo: "{location} へ移動",
    hint: "対処",
    showFullLog: "ログ全体を表示",
    hideFullLog: "ログ全体を隠す",
    noDetails:
      "コンパイルに失敗しましたが、ログが返されませんでした。ログ全体を確認するか、もう一度お試しください。",
    requestFailed: "コンパイル要求が失敗しました: {error}",
    requestFailedHint:
      "サーバーが要求を受け付けないか応答しませんでした。ページを再読み込みして（セッション切れの可能性があります）もう一度コンパイルしてください",
  },
} as const;

export type DiagnosticsStringKey = keyof (typeof DIAGNOSTICS_STRINGS)["en"];

function normalize(lang: string | null | undefined): DiagnosticsLanguage {
  const code = (lang || "").trim().toLowerCase();
  return code === "ja" || code.startsWith("ja-") ? "ja" : "en";
}

export function diagnosticsTranslate(
  key: DiagnosticsStringKey,
  params: Record<string, string | number> = {},
  doc: { documentElement?: { lang?: string } } = document,
): string {
  const lang = normalize(doc?.documentElement?.lang);
  const template: string =
    DIAGNOSTICS_STRINGS[lang][key] ?? DIAGNOSTICS_STRINGS.en[key];
  return template.replace(/\{(\w+)\}/g, (whole, name: string) =>
    name in params ? String(params[name]) : whole,
  );
}
