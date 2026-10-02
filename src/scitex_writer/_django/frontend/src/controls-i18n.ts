/** Writer control copy follows the host's document language. */
const STRINGS = {
  en: {
    compileMode: "Compile mode", draft: "Draft", full: "Full",
    compilation: "Compilation", details: "Details", status: "Status",
    draftHint: "Build the selected document in draft mode.",
    fullHint: "Build the selected document with draft mode off.",
    documentType: "Document type", section: "Section", hints: "Hints",
    importExport: "Import / Export", project: "Project Info", shortcuts: "Shortcuts",
  },
  ja: {
    compileMode: "コンパイルモード", draft: "ドラフト", full: "完全",
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
