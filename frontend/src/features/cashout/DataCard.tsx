// frontend/src/features/cashout/DataCard.tsx

import { Banknote, CreditCard, HandCoins, Sigma } from "lucide-react";
import type { ReactNode } from "react";

import type { CashoutData } from "@/api/types";
import { Card } from "@/components/ui";

/** The reconciled result of a completed cashout (placeholder fields for now). */
export function DataCard({ data }: { data: CashoutData }) {
  const stats: { label: string; value: string | null; icon: ReactNode }[] = [
    {
      label: "Daily tipout",
      value: data.dailyTipout,
      icon: <HandCoins className="size-4" />,
    },
    {
      label: "Net total",
      value: data.netTotal,
      icon: <Sigma className="size-4" />,
    },
    {
      label: "Cash total",
      value: data.cashTotal,
      icon: <Banknote className="size-4" />,
    },
    {
      label: "Card total",
      value: data.cardTotal,
      icon: <CreditCard className="size-4" />,
    },
  ];

  return (
    <Card className="space-y-3">
      <h2 className="font-semibold">Cashout data</h2>
      <div className="grid grid-cols-2 gap-2 sm:grid-cols-4">
        {stats.map((stat) => (
          <div key={stat.label} className="bg-surface-2 rounded-lg p-3">
            <p className="text-ink-muted flex items-center gap-1.5 text-xs">
              {stat.icon}
              {stat.label}
            </p>
            <p className="mt-1 text-lg font-semibold tabular-nums">
              {stat.value != null ? `$${stat.value}` : "—"}
            </p>
          </div>
        ))}
      </div>
      <p className="text-ink-muted text-xs">
        Reconciled totals populate once the extraction schemas are finalized.
      </p>
    </Card>
  );
}
