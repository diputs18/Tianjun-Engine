import { useMemo } from "react";
import { useTheme } from "./ThemeProvider.jsx";

export function useThemeTokens() {
  const { theme } = useTheme();

  return useMemo(() => {
    const style = getComputedStyle(document.documentElement);
    const get = (name) => style.getPropertyValue(name).trim();
    return {
      theme,
      bg: get("--tj-bg"),
      bgSoft: get("--tj-bg-soft"),
      surface: get("--tj-surface-solid"),
      surfaceMuted: get("--tj-surface-muted"),
      text: get("--tj-text"),
      textSecondary: get("--tj-text-secondary"),
      textMuted: get("--tj-text-muted"),
      line: get("--tj-line"),
      blue: get("--tj-blue"),
      green: get("--tj-green"),
      purple: get("--tj-purple"),
      red: get("--tj-red"),
      amber: get("--tj-amber"),
    };
  }, [theme]);
}
