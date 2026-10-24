import type { LedgerEntry } from "@/lib/types";

function number(value: unknown, digits = 4): string {
  return typeof value === "number" ? value.toFixed(digits) : "-";
}

function pValue(value: unknown): string {
  if (typeof value !== "number") {
    return "-";
  }
  return value < 0.001 ? value.toExponential(2) : value.toFixed(4);
}

export function describeEntry(entry: LedgerEntry): string {
  switch (entry.kind) {
    case "dataset":
      return `${String(entry.source)}, ${number(entry.samples, 0)} rows, ${number(entry.features, 0)} features, ${number(entry.seconds, 0)} s, script ${String(entry.script_sha256).slice(0, 8)}`;
    case "failure":
      return `${String(entry.attempts)} attempts: ${String(entry.error)}`;
    case "claim":
      return `${String(entry.verdict)}: ${String(entry.wins)} of ${String(entry.datasets)} datasets, median difference ${number(entry.median_difference)}, adjusted p ${pValue(entry.adjusted_p_value)}`;
    case "friedman":
      return entry.testable ? `chi-square ${number(entry.statistic, 2)}, p ${pValue(entry.p_value)}` : "not run";
    case "pairwise":
      return `${String(entry.a)} vs ${String(entry.b)}: ${String(entry.wins)} wins, ${String(entry.losses)} losses, adjusted p ${pValue(entry.adjusted_p_value)}`;
    case "effect":
      return `median difference ${number(entry.median_difference)}, adjusted p ${pValue(entry.adjusted_p_value)}`;
    default:
      return "";
  }
}
