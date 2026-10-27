import { describeEntry } from "@/lib/ledger";
import type { LedgerEntry } from "@/lib/types";

type LedgerTableProps = {
  ledger: LedgerEntry[];
};

export function LedgerTable({ ledger }: LedgerTableProps) {
  return (
    <div className="overflow-x-auto">
      <table className="w-full min-w-[640px] border-collapse text-left text-sm">
        <thead>
          <tr className="border-b border-line text-xs tracking-[0.12em] text-faint uppercase">
            <th className="py-2 pr-4">Id</th>
            <th className="py-2 pr-4">Kind</th>
            <th className="py-2 pr-4">Key</th>
            <th className="py-2">Detail</th>
          </tr>
        </thead>
        <tbody>
          {ledger.map((entry) => (
            <tr key={entry.id} id={entry.id} className="border-b border-line-soft align-top">
              <td className="py-2 pr-4 font-semibold text-accent">{entry.id}</td>
              <td className="py-2 pr-4 text-muted">{entry.kind}</td>
              <td className="py-2 pr-4 text-ink">{entry.key}</td>
              <td className="py-2 text-muted">{describeEntry(entry)}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
