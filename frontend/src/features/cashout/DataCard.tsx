// frontend/src/features/cashout/DataCard.tsx

import { Banknote, CreditCard, HandCoins, Sigma } from "lucide-react";
import type { ReactNode } from "react";

import type { CashoutData, TipoutDepartment } from "@/api/types";
import { Badge, Card } from "@/components/ui";

const DEPARTMENT_LABELS: Record<TipoutDepartment, string> = {
  bar: "Bar",
  kitchen: "Kitchen",
  expo: "Expo",
  host: "Host",
};

/** The reconciled result of a completed cashout. */
export function DataCard({ data }: { data: CashoutData }) {
  const stats: { label: string; value: string | null; icon: ReactNode }[] = [
    {
      label: "Net sales",
      value: data.totalNetSales,
      icon: <Sigma className="size-4" />,
    },
    {
      label: "Cash payments",
      value: data.cashPaymentTotal,
      icon: <Banknote className="size-4" />,
    },
    {
      label: "Card payments",
      value: data.cardPaymentTotal,
      icon: <CreditCard className="size-4" />,
    },
    {
      label: "Card tips",
      value: data.cardTipTotal,
      icon: <HandCoins className="size-4" />,
    },
  ];

  // Only the departments actually tipped out to; the rest are null by design.
  const tipouts: { label: string; value: string | null }[] = [
    { label: "Bar", value: data.barTipout },
    { label: "Kitchen", value: data.kitchenTipout },
    { label: "Expo", value: data.expoTipout },
    { label: "Host", value: data.hostTipout },
  ].filter((tipout) => tipout.value != null);

  // At most one side is set: whichever way the cash/card-tip balance fell.
  const balance =
    data.cashOwedToHouse != null
      ? { label: "Cash owed to house", value: data.cashOwedToHouse }
      : data.cashOwedToEmployee != null
        ? { label: "Cash owed to employee", value: data.cashOwedToEmployee }
        : null;

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

      <div className="space-y-1.5">
        <p className="text-ink-muted text-xs">Tipped out to</p>
        {data.tipoutDepartments.length === 0 ? (
          <p className="text-sm">No departments tipped out.</p>
        ) : (
          <div className="flex flex-wrap gap-1.5">
            {data.tipoutDepartments.map((department) => (
              <Badge key={department}>{DEPARTMENT_LABELS[department]}</Badge>
            ))}
          </div>
        )}
      </div>

      {tipouts.length > 0 && (
        <dl className="divide-line divide-y text-sm">
          {tipouts.map((tipout) => (
            <div key={tipout.label} className="flex justify-between py-1.5">
              <dt className="text-ink-muted">{tipout.label} tipout</dt>
              <dd className="font-medium tabular-nums">${tipout.value}</dd>
            </div>
          ))}
        </dl>
      )}

      {balance != null && (
        <div className="bg-surface-2 flex justify-between rounded-lg p-3 text-sm">
          <span className="text-ink-muted">{balance.label}</span>
          <span className="font-semibold tabular-nums">${balance.value}</span>
        </div>
      )}

      {data.totalNetSales == null && (
        <p className="text-ink-muted text-xs">
          Amounts populate once reconciliation is implemented.
        </p>
      )}
    </Card>
  );
}
