// frontend/src/layout/AppLayout.tsx

import {
  ClipboardList,
  Database,
  LogOut,
  Monitor,
  Moon,
  ReceiptText,
  Sun,
  UsersRound,
  type LucideIcon,
} from "lucide-react";
import { NavLink, Outlet, useNavigate } from "react-router-dom";

import { isAdminRole } from "@/api/types";
import { useAuth } from "@/auth/useAuth";
import { cx } from "@/lib/cx";
import { initials } from "@/lib/format";
import { useTheme, type Theme } from "@/lib/useTheme";

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
    "flex flex-1 flex-col items-center gap-0.5 rounded-lg px-3 py-1.5 text-[11px] font-medium transition-colors",
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
    ...(user && isAdminRole(user.role)
      ? [
          {
            to: "/admin/submissions",
            label: "Submissions",
            icon: ClipboardList,
          },
          { to: "/admin/data", label: "Data", icon: Database },
          { to: "/admin/users", label: "Users", icon: UsersRound },
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

  const userInitials = user ? initials(user.fullName) : "";

  // min-w-80 (320px) − px-4 gutters = the cards' 288px min-width: smaller
  // viewports scroll horizontally as one unit instead of crushing.
  return (
    <div className="min-h-dvh min-w-80 pb-24 md:pb-0 print:pb-0">
      <header className="border-line bg-surface/90 sticky top-0 z-10 border-b backdrop-blur print:hidden">
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
              className="hover:bg-surface-2 text-ink-muted hover:text-ink grid size-10 place-items-center rounded-lg transition-colors"
            >
              <ThemeIcon className="size-4.5" />
            </button>

            <span
              title={user?.fullName}
              className="bg-accent/15 text-accent-strong grid size-8 place-items-center rounded-full text-xs font-semibold"
            >
              {userInitials}
            </span>

            <button
              onClick={() => void onLogout()}
              title="Log out"
              aria-label="Log out"
              className="hover:bg-surface-2 text-ink-muted hover:text-ink grid size-10 place-items-center rounded-lg transition-colors"
            >
              <LogOut className="size-4.5" />
            </button>
          </div>
        </div>
      </header>

      <main className="mx-auto max-w-5xl px-4 py-4 md:py-6 print:max-w-none print:px-0 print:py-0">
        <Outlet />
      </main>

      <nav className="border-line bg-surface/95 fixed inset-x-0 bottom-0 z-10 flex border-t px-2 py-1.5 pb-[max(0.375rem,env(safe-area-inset-bottom))] backdrop-blur md:hidden print:hidden">
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
