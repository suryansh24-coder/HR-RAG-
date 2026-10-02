import { useCallback, useEffect, useState } from "react";

export type Theme = "dark" | "light";

const STORAGE_KEY = "hr-nexus.theme";

/**
 * Theme preference.
 *
 * Only the *preference* is persisted (in `localStorage`); no credential or API
 * data is stored in the browser. The attribute is written to `<html>` so the CSS
 * custom properties in `index.css` can re-point the whole palette, and
 * `color-scheme` follows, which makes native scrollbars and form controls match.
 *
 * When nothing is stored the OS preference wins, and a user who has never
 * touched the toggle still gets the theme their system asks for.
 */
export function useTheme(): { theme: Theme; toggle: () => void } {
  const [theme, setTheme] = useState<Theme>(() => initial());

  useEffect(() => {
    document.documentElement.dataset.theme = theme;
    try {
      window.localStorage.setItem(STORAGE_KEY, theme);
    } catch {
      // Private browsing / storage disabled — the in-memory theme still works.
    }
  }, [theme]);

  const toggle = useCallback(() => {
    setTheme((current) => (current === "dark" ? "light" : "dark"));
  }, []);

  return { theme, toggle };
}

function initial(): Theme {
  try {
    const stored = window.localStorage.getItem(STORAGE_KEY);
    if (stored === "dark" || stored === "light") return stored;
  } catch {
    /* fall through to the OS preference */
  }
  return window.matchMedia?.("(prefers-color-scheme: light)").matches ? "light" : "dark";
}
