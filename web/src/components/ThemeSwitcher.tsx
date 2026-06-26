// 主页主题切换：点击展开主题列表，选中即时生效并持久化。
import { useEffect, useRef, useState } from "react";
import { THEMES, getTheme, applyTheme, type ThemeKey } from "../theme";

export function ThemeSwitcher() {
  const [open, setOpen] = useState(false);
  const [theme, setTheme] = useState<ThemeKey>(getTheme());
  const ref = useRef<HTMLDivElement>(null);

  // 点击外部关闭下拉
  useEffect(() => {
    if (!open) return;
    const onClick = (e: MouseEvent) => {
      if (ref.current && !ref.current.contains(e.target as Node)) {
        setOpen(false);
      }
    };
    document.addEventListener("mousedown", onClick);
    return () => document.removeEventListener("mousedown", onClick);
  }, [open]);

  const pick = (t: ThemeKey) => {
    applyTheme(t);
    setTheme(t);
    setOpen(false);
  };

  return (
    <div ref={ref} style={{ position: "relative" }}>
      <button onClick={() => setOpen((v) => !v)}>🎨 背景</button>
      {open && (
        <div
          className="card"
          style={{
            position: "absolute",
            right: 0,
            top: "calc(100% + 6px)",
            zIndex: 50,
            padding: 6,
            minWidth: 160,
          }}
        >
          {THEMES.map((t) => (
            <div
              key={t.key}
              className={`nav-item ${theme === t.key ? "active" : ""}`}
              onClick={() => pick(t.key)}
              style={{ fontSize: 13 }}
            >
              {t.label}
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
