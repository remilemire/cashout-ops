// frontend/src/lib/theme.tsx

import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useState,
  type ReactNode,
} from "react";

export type Theme = "light" | "dark" | "system";

interface ThemeContextValue {
  theme: Theme;
  /** The mode actually applied right now. */
  resolved: "light" | "dark";
  setTheme: (theme: Theme) => void;
}

const ThemeContext = createContext<ThemeContextValue | null>(null);

const query = () => matchMedia("(prefers-color-scheme: dark)");

function resolve(theme: Theme): "light" | "dark" {
  return theme === "system" ? (query().matches ? "dark" : "light") : theme;
}

function apply(theme: Theme) {
  document.documentElement.classList.toggle("dark", resolve(theme) === "dark");
}

export function ThemeProvider({ children }: { children: ReactNode }) {
  const [theme, setThemeState] = useState<Theme>(
    () => (localStorage.getItem("theme") as Theme | null) ?? "system",
  );

  const setTheme = useCallback((next: Theme) => {
    setThemeState(next);
    localStorage.setItem("theme", next);
    apply(next);
  }, []);

  // Track OS changes while in system mode.
  useEffect(() => {
    if (theme !== "system") return;
    const media = query();
    const onChange = () => apply("system");
    media.addEventListener("change", onChange);
    return () => media.removeEventListener("change", onChange);
  }, [theme]);

  return (
    <ThemeContext.Provider
      value={{ theme, resolved: resolve(theme), setTheme }}
    >
      {children}
    </ThemeContext.Provider>
  );
}

export function useTheme(): ThemeContextValue {
  const ctx = useContext(ThemeContext);
  if (!ctx) throw new Error("useTheme must be used within ThemeProvider");
  return ctx;
}
