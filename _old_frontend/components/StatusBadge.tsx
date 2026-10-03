import type { DocumentStatus } from "@/lib/types";

const STYLES: Record<DocumentStatus, string> = {
  pending: "bg-amber-100 text-amber-700 ring-amber-200",
  processing: "bg-blue-100 text-blue-700 ring-blue-200",
  ready: "bg-emerald-100 text-emerald-700 ring-emerald-200",
  error: "bg-red-100 text-red-700 ring-red-200",
};

const LABELS: Record<DocumentStatus, string> = {
  pending: "Queued",
  processing: "Processing",
  ready: "Ready",
  error: "Failed",
};

export function StatusBadge({ status }: { status: DocumentStatus }) {
  return (
    <span
      className={`inline-flex items-center gap-1.5 rounded-full px-2.5 py-0.5 text-xs font-medium ring-1 ring-inset ${STYLES[status]}`}
    >
      {(status === "pending" || status === "processing") && (
        <span className="h-1.5 w-1.5 animate-pulse rounded-full bg-current" />
      )}
      {LABELS[status]}
    </span>
  );
}
