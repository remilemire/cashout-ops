// frontend/src/auth/AuthShell.tsx

import { GlassWater } from "lucide-react";
import type { ReactNode } from "react";

/** Centered brand frame shared by the sign-in screens. */
export function AuthShell({ children }: { children: ReactNode }) {
  return (
    <div className="flex min-h-dvh items-center justify-center px-4 py-8">
      <div className="w-full max-w-sm">
        <div className="mb-5 text-center">
          <span className="bg-accent/15 text-accent-strong mx-auto mb-2 grid size-12 place-items-center rounded-2xl">
            <GlassWater className="size-6" />
          </span>
          <p className="font-semibold">
            <span className="text-accent-strong">Whiskey District</span>{" "}
            Cashouts
          </p>
        </div>
        {children}
      </div>
    </div>
  );
}
