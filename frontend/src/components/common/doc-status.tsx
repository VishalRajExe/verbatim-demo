import { Check, Clock, LoaderCircle, TriangleAlert } from "lucide-react";
import { Badge } from "@/components/ui/badge";
import { Progress } from "@/components/ui/progress";
import type { DocumentItem } from "@/lib/types";

export function DocStatusPill({ doc }: { doc: DocumentItem }) {
  switch (doc.status) {
    case "ready":
      return (
        <Badge tone="ok">
          <Check /> Ready
        </Badge>
      );
    case "failed":
      return (
        <Badge tone="danger">
          <TriangleAlert /> Can&apos;t read
        </Badge>
      );
    case "queued":
      return (
        <Badge>
          <Clock /> Queued
        </Badge>
      );
    default:
      return (
        <Badge tone="brand">
          <LoaderCircle className="animate-spin" /> Processing
        </Badge>
      );
  }
}

/** Pill plus a live progress bar while the document is still being processed. */
export function DocStatusCell({ doc }: { doc: DocumentItem }) {
  const working = doc.status !== "ready" && doc.status !== "failed";
  return (
    <div className="flex min-w-[120px] flex-col items-start gap-1.5">
      <DocStatusPill doc={doc} />
      {working ? (
        <div className="w-full max-w-[150px]" aria-live="polite">
          <Progress value={doc.progress} label={`Processing ${doc.name}`} />
          <p className="mt-1 truncate text-[11px] text-ink-subtle">{doc.stage ?? "Working"}</p>
        </div>
      ) : null}
    </div>
  );
}
