/** Writer control copy follows the host's document language. */
const STRINGS = {
  en: {
    compileMode: "Compile mode", draft: "Draft (current section)", full: "Full (whole manuscript)",
    compilation: "Compilation", details: "Panel", status: "Status",
    draftHint: "Build the current section only, in draft mode. Fast iteration.",
    fullHint: "Build the whole manuscript, draft mode off. Slower, complete.",
    documentType: "Document type", section: "Section", hints: "Hints",
    importExport: "Import / Export", project: "Project Info", shortcuts: "Shortcuts",
  },
  ja: {
    compileMode: "コンパイルモード", draft: "ドラフト（現在の節のみ）", full: "完全（全文）",
    compilation: "コンパイル", details: "詳細", status: "状態",
    draftHint: "選択した文書をドラフトモードでコンパイルします。",
    fullHint: "選択した文書をドラフトモードを無効にしてコンパイルします。",
    documentType: "文書の種類", section: "節", hints: "ヒント",
    importExport: "インポート / エクスポート", project: "プロジェクト情報", shortcuts: "ショートカット",
  },
} as const;

export function controlsTranslate(key: keyof typeof STRINGS.en): string {
  return STRINGS[document.documentElement.lang.toLowerCase().startsWith("ja") ? "ja" : "en"][key];
}
