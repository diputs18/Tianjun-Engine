import { createContext, useContext, useEffect, useMemo, useState } from "react";

const STORAGE_KEY = "tianjun:theme";
const ThemeContext = createContext(null);

function getSystemTheme() {
  if (typeof window === "undefined") return "light";
  return window.matchMedia?.("(prefers-color-scheme: dark)").matches ? "dark" : "light";
}

function resolveTheme(mode) {
  return mode === "system" ? getSystemTheme() : mode;
}

function applyTheme(mode) {
  const resolved = resolveTheme(mode);
  const root = document.documentElement;
  root.dataset.theme = resolved;
  root.dataset.themeMode = mode;
  root.style.colorScheme = resolved;
  document.body?.setAttribute("arco-theme", resolved === "dark" ? "dark" : "light");
}

export function ThemeProvider({ children }) {
  const [mode, setMode] = useState(() => localStorage.getItem(STORAGE_KEY) || "light");
  const resolvedTheme = useMemo(() => resolveTheme(mode), [mode]);

  useEffect(() => {
    localStorage.setItem(STORAGE_KEY, mode);
    applyTheme(mode);
  }, [mode]);

  useEffect(() => {
    if (mode !== "system") return undefined;
    const media = window.matchMedia?.("(prefers-color-scheme: dark)");
    if (!media) return undefined;
    const listener = () => applyTheme("system");
    media.addEventListener?.("change", listener);
    return () => media.removeEventListener?.("change", listener);
  }, [mode]);

  const value = useMemo(
    () => ({ mode, theme: resolvedTheme, isDark: resolvedTheme === "dark", setMode }),
    [mode, resolvedTheme],
  );

  return <ThemeContext.Provider value={value}>{children}</ThemeContext.Provider>;
}

export function useTheme() {
  const context = useContext(ThemeContext);
  if (!context) throw new Error("useTheme must be used inside ThemeProvider");
  return context;
}
