// 主题管理：在 <html> 上设 data-theme，配色由 styles.css 的 CSS 变量切换。
// 选择持久化到 localStorage，入口尽早应用避免首屏闪烁。

export type ThemeKey = "sepia" | "paper" | "dark" | "sepia-dark";

export const THEMES: { key: ThemeKey; label: string }[] = [
  { key: "sepia", label: "羊皮纸（默认）" },
  { key: "paper", label: "纸白" },
  { key: "dark", label: "暗夜" },
  { key: "sepia-dark", label: "夜读（深褐）" },
];

const STORAGE_KEY = "novel-theme";
const DEFAULT_THEME: ThemeKey = "sepia";

export function getTheme(): ThemeKey {
  const v = localStorage.getItem(STORAGE_KEY) as ThemeKey | null;
  return v && THEMES.some((t) => t.key === v) ? v : DEFAULT_THEME;
}

export function applyTheme(theme: ThemeKey): void {
  // sepia 是默认配色（:root 无 data-theme 也成立），但显式设上更直观
  document.documentElement.setAttribute("data-theme", theme);
  localStorage.setItem(STORAGE_KEY, theme);
}

// 入口调用：应用已保存主题（无则默认羊皮纸）
export function initTheme(): void {
  applyTheme(getTheme());
}
