// frontend/src/layout/AppLayout.tsx

import {
  ClipboardList,
  Database,
  LogOut,
  Monitor,
  Moon,
  ReceiptText,
  Sun,
  type LucideIcon,
} from "lucide-react";
import { NavLink, Outlet, useNavigate } from "react-router-dom";

import { useAuth } from "@/auth/AuthProvider";
import { cx } from "@/components/ui";
import { useTheme, type Theme } from "@/lib/theme";

const THEME_ORDER: Theme[] = ["system", "light", "dark"];
const THEME_ICONS: Record<Theme, LucideIcon> = {
  system: Monitor,
  light: Sun,
  dark: Moon,
};

interface NavItem {
  to: string;
  label: string;
  icon: LucideIcon;
}

function navLinkClass({ isActive }: { isActive: boolean }) {
  return cx(
    "flex flex-1 flex-col items-center gap-0.5 rounded-lg px-3 py-1.5 text-[11px] font-medium",
    "md:flex-none md:flex-row md:gap-2 md:py-2 md:text-sm",
    isActive
      ? "text-accent-strong md:bg-accent/10"
      : "text-ink-muted hover:text-ink",
  );
}

export function AppLayout() {
  const { user, logout } = useAuth();
  const { theme, setTheme } = useTheme();
  const navigate = useNavigate();

  const links: NavItem[] = [
    { to: "/cashouts", label: "My cashouts", icon: ReceiptText },
    ...(user?.role === "ADMIN"
      ? [
          {
            to: "/admin/submissions",
            label: "Submissions",
            icon: ClipboardList,
          },
          { to: "/admin/data", label: "Data", icon: Database },
        ]
      : []),
  ];

  const ThemeIcon = THEME_ICONS[theme];
  const cycleTheme = () => {
    const next =
      THEME_ORDER[(THEME_ORDER.indexOf(theme) + 1) % THEME_ORDER.length] ??
      "system";
    setTheme(next);
  };

  const onLogout = async () => {
    await logout();
    navigate("/login");
  };

  const initials = user
    ? `${user.firstName.charAt(0)}${user.lastName.charAt(0)}`.toUpperCase()
    : "";

  return (
    <div className="min-h-dvh pb-24 md:pb-0">
      <header className="border-line bg-surface/90 sticky top-0 z-10 border-b backdrop-blur">
        <div className="mx-auto flex h-14 max-w-5xl items-center gap-4 px-4">
          <span className="truncate font-semibold tracking-tight">
            <span className="text-accent-strong">Whiskey District</span>{" "}
            <span className="hidden sm:inline">Cashouts</span>
          </span>

          {/* Desktop nav; mobile uses the bottom bar. */}
          <nav className="hidden gap-1 md:flex">
            {links.map((link) => (
              <NavLink key={link.to} to={link.to} className={navLinkClass}>
                <link.icon className="size-4" />
                {link.label}
              </NavLink>
            ))}
          </nav>

          <div className="ml-auto flex items-center gap-1.5">
            <button
              onClick={cycleTheme}
              title={`Theme: ${theme}`}
              aria-label={`Theme: ${theme}`}
              className="hover:bg-surface-2 text-ink-muted hover:text-ink grid size-10 place-items-center rounded-lg"
            >
              <ThemeIcon className="size-4.5" />
            </button>

            <span
              title={user ? `${user.firstName} ${user.lastName}` : undefined}
              className="bg-accent/15 text-accent-strong grid size-8 place-items-center rounded-full text-xs font-semibold"
            >
              {initials}
            </span>

            <button
              onClick={() => void onLogout()}
              title="Log out"
              aria-label="Log out"
              className="hover:bg-surface-2 text-ink-muted hover:text-ink grid size-10 place-items-center rounded-lg"
            >
              <LogOut className="size-4.5" />
            </button>
          </div>
        </div>
      </header>

      <main className="mx-auto max-w-5xl px-4 py-4 md:py-6">
        <Outlet />
      </main>

      <nav className="border-line bg-surface/95 fixed inset-x-0 bottom-0 z-10 flex border-t px-2 py-1.5 pb-[max(0.375rem,env(safe-area-inset-bottom))] backdrop-blur md:hidden">
        {links.map((link) => (
          <NavLink key={link.to} to={link.to} className={navLinkClass}>
            <link.icon className="size-5" />
            {link.label}
          </NavLink>
        ))}
      </nav>
    </div>
  );
}
