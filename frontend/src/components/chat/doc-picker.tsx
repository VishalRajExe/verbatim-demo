"use client";

import { Plus, X } from "lucide-react";
import Link from "next/link";
import { useMemo, useState } from "react";
import { DocListPicker } from "@/components/common/doc-list-picker";
import { MiddleTruncate } from "@/components/common/middle-truncate";
import { Icon } from "@/components/icons";
import { Popover, PopoverContent, PopoverTrigger } from "@/components/ui/popover";
import type { DocumentItem } from "@/lib/types";
import { cn, docDot } from "@/lib/utils";

export const MAX_DOCS = 5;

/**
 * Chosen documents show as removable chips; the rest live in a searchable popover.
 * The header stays one line no matter how many documents are uploaded.
 */
export function DocPicker({
  docs,
  loading,
  selectedIds,
  onToggle,
  onClear,
  disabled,
}: {
  docs: DocumentItem[];
  loading: boolean;
  selectedIds: string[];
  onToggle: (id: string) => void;
  onClear: () => void;
  disabled: boolean;
}) {
  const [open, setOpen] = useState(false);
  const byId = useMemo(() => new Map(docs.map((d) => [d.id, d])), [docs]);
  const chosen = selectedIds.map((id) => byId.get(id)).filter((d): d is DocumentItem => Boolean(d));
  const full = chosen.length >= MAX_DOCS;
  const many = chosen.length > 1;

  return (
    <div>
      <div className="mb-2 flex items-center gap-2 text-[11px] font-semibold uppercase tracking-wide text-ink-subtle">
        <Icon name="layers" className="size-3.5" />
        <span>Ask across documents</span>
        {!loading && docs.length > 0 ? (
          <span className="font-medium normal-case tracking-normal tabular-nums">· {docs.length} ready</span>
        ) : null}
        {chosen.length > 0 ? (
          <>
            <span className="rounded-full bg-brand-soft px-2 py-0.5 normal-case tracking-normal text-brand tabular-nums">
              {chosen.length}/{MAX_DOCS}
            </span>
            <button
              type="button"
              onClick={onClear}
              disabled={disabled}
              className="normal-case tracking-normal text-ink-subtle hover:text-ink disabled:opacity-50"
            >
              Clear
            </button>
          </>
        ) : null}
      </div>

      {loading ? (
        <div className="flex gap-2" aria-busy="true">
          {[150, 190].map((w, i) => (
            <div key={i} className="h-8 animate-pulse rounded-full bg-line/70" style={{ width: w }} />
          ))}
        </div>
      ) : docs.length === 0 ? (
        <p className="text-sm text-ink-subtle">
          No ready documents.{" "}
          <Link href="/documents" className="font-semibold text-brand hover:underline">
            Upload one
          </Link>
        </p>
      ) : (
        <div className="flex flex-wrap items-center gap-2">
          {chosen.map((d) => (
            <span
              key={d.id}
              title={d.name}
              className="inline-flex max-w-[12.5rem] items-center gap-1.5 rounded-full border border-brand/30 bg-brand-soft py-1 pl-2.5 pr-1 text-xs font-medium text-brand"
            >
              {many ? <span aria-hidden className={cn("size-2 shrink-0 rounded-full", docDot(d.id))} /> : null}
              <MiddleTruncate text={d.name} tail={14} className="min-w-0 flex-1" />
              <button
                type="button"
                aria-label={`Remove ${d.name}`}
                disabled={disabled}
                onClick={() => onToggle(d.id)}
                className="grid size-5 shrink-0 place-items-center rounded-full hover:bg-brand/10 disabled:opacity-50"
              >
                <X className="size-3" strokeWidth={2.5} />
              </button>
            </span>
          ))}

          <Popover open={open} onOpenChange={setOpen}>
            <PopoverTrigger asChild>
              <button
                type="button"
                disabled={disabled}
                className="inline-flex h-7 items-center gap-1.5 rounded-full border border-dashed border-line-strong bg-surface px-3 text-xs font-semibold text-ink-muted transition-colors hover:border-brand hover:text-brand disabled:opacity-50"
              >
                <Plus className="size-3.5" />
                {chosen.length === 0 ? "Choose documents" : full ? "Edit selection" : "Add document"}
              </button>
            </PopoverTrigger>
            <PopoverContent>
              <DocListPicker
                docs={docs}
                selectedIds={selectedIds}
                onToggle={onToggle}
                multiple
                max={MAX_DOCS}
                onClear={onClear}
              />
            </PopoverContent>
          </Popover>

          {chosen.length === 0 ? <span className="text-xs text-ink-subtle">Pick up to {MAX_DOCS} to ask about.</span> : null}
        </div>
      )}
    </div>
  );
}
