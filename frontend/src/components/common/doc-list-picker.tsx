"use client";

import { Check, Search } from "lucide-react";
import { useId, useMemo, useRef, useState, type KeyboardEvent } from "react";
import { FileIcon } from "@/components/common/file-icon";
import { MiddleTruncate } from "@/components/common/middle-truncate";
import type { DocumentItem } from "@/lib/types";
import { cn } from "@/lib/utils";

/**
 * Searchable list of documents for popovers. Scales to hundreds of files:
 * type to filter, arrow keys to move, Enter or click to choose.
 * `multiple` shows checkboxes (with an optional cap); otherwise it is a single choice.
 */
export function DocListPicker({
  docs,
  selectedIds,
  onToggle,
  multiple = false,
  max,
  onClear,
  emptyHint = "No documents.",
}: {
  docs: DocumentItem[];
  selectedIds: string[];
  onToggle: (id: string) => void;
  multiple?: boolean;
  max?: number;
  onClear?: () => void;
  emptyHint?: string;
}) {
  const [query, setQuery] = useState("");
  const [active, setActive] = useState(0);
  const listRef = useRef<HTMLDivElement>(null);
  const uid = useId();

  const shown = useMemo(() => {
    const terms = query.toLowerCase().split(/\s+/).filter(Boolean);
    if (terms.length === 0) return docs;
    const phrase = terms.join(" ");
    const hits = docs.filter((d) => terms.every((t) => d.name.toLowerCase().includes(t)));
    // Exact phrase matches first ("vendor 3" before "Agreement 23 - Vendor 23"); sort is stable, so list order is kept within a rank.
    return hits.sort((a, b) => Number(b.name.toLowerCase().includes(phrase)) - Number(a.name.toLowerCase().includes(phrase)));
  }, [docs, query]);

  const atMax = multiple && max !== undefined && selectedIds.length >= max;
  const canToggle = (d: DocumentItem) => !(atMax && !selectedIds.includes(d.id));
  const idx = Math.min(active, Math.max(shown.length - 1, 0));
  const optionId = (i: number) => `${uid}-opt-${i}`;

  function move(next: number) {
    const clamped = Math.max(0, Math.min(shown.length - 1, next));
    setActive(clamped);
    requestAnimationFrame(() => document.getElementById(optionId(clamped))?.scrollIntoView({ block: "nearest" }));
  }

  function onKeyDown(e: KeyboardEvent<HTMLInputElement>) {
    if (e.key === "ArrowDown") (e.preventDefault(), move(idx + 1));
    else if (e.key === "ArrowUp") (e.preventDefault(), move(idx - 1));
    else if (e.key === "Home") (e.preventDefault(), move(0));
    else if (e.key === "End") (e.preventDefault(), move(shown.length - 1));
    else if (e.key === "Enter") {
      const d = shown[idx];
      if (d && canToggle(d)) (e.preventDefault(), onToggle(d.id));
    }
  }

  return (
    <div>
      <div className="relative border-b border-line">
        <Search className="pointer-events-none absolute left-3.5 top-1/2 size-4 -translate-y-1/2 text-ink-subtle" aria-hidden />
        <input
          autoFocus
          role="combobox"
          aria-expanded
          aria-controls={`${uid}-list`}
          aria-activedescendant={shown.length ? optionId(idx) : undefined}
          aria-label="Search documents"
          placeholder={`Search ${docs.length} document${docs.length === 1 ? "" : "s"}…`}
          value={query}
          onChange={(e) => (setQuery(e.target.value), setActive(0))}
          onKeyDown={onKeyDown}
          className="h-11 w-full bg-transparent pl-10 pr-3 text-sm text-ink placeholder:text-ink-subtle focus-visible:outline-none"
        />
      </div>

      <div
        ref={listRef}
        id={`${uid}-list`}
        role="listbox"
        aria-multiselectable={multiple || undefined}
        className="scroll-thin max-h-72 overflow-y-auto p-1.5"
      >
        {docs.length === 0 ? (
          <p className="px-3 py-6 text-center text-sm text-ink-subtle">{emptyHint}</p>
        ) : shown.length === 0 ? (
          <p className="px-3 py-6 text-center text-sm text-ink-subtle">No documents match “{query}”.</p>
        ) : (
          shown.map((d, i) => {
            const on = selectedIds.includes(d.id);
            const locked = !canToggle(d);
            return (
              <div
                key={d.id}
                id={optionId(i)}
                role="option"
                aria-selected={on}
                aria-disabled={locked || undefined}
                title={locked ? `Up to ${max} documents at once` : d.name}
                onMouseMove={() => i !== idx && setActive(i)}
                onClick={() => !locked && onToggle(d.id)}
                className={cn(
                  "flex cursor-pointer items-center gap-3 rounded-lg px-2.5 py-2",
                  i === idx && "bg-canvas",
                  locked && "cursor-not-allowed opacity-45",
                )}
              >
                {multiple ? (
                  <span
                    aria-hidden
                    className={cn(
                      "grid size-[18px] shrink-0 place-items-center rounded border",
                      on ? "border-brand bg-brand text-white" : "border-line-strong bg-surface",
                    )}
                  >
                    {on ? <Check className="size-3.5" strokeWidth={3} /> : null}
                  </span>
                ) : null}
                <FileIcon kind={d.kind} className="size-7" />
                <span className="min-w-0 flex-1">
                  <MiddleTruncate text={d.name} tail={16} className="text-sm font-medium text-ink" />
                  <span className="block text-xs text-ink-subtle tabular-nums">
                    {d.kind.toUpperCase()}
                    {d.pages ? ` · ${d.pages} page${d.pages === 1 ? "" : "s"}` : ""}
                  </span>
                </span>
                {!multiple && on ? <Check className="size-4 shrink-0 text-brand" strokeWidth={2.5} aria-label="Selected" /> : null}
              </div>
            );
          })
        )}
      </div>

      {multiple && max !== undefined ? (
        <div className="flex items-center justify-between border-t border-line px-3.5 py-2 text-xs text-ink-subtle">
          <span className="tabular-nums" aria-live="polite">
            {selectedIds.length} of {max} selected
          </span>
          {selectedIds.length > 0 && onClear ? (
            <button type="button" onClick={onClear} className="font-semibold text-brand hover:underline">
              Clear
            </button>
          ) : null}
        </div>
      ) : null}
    </div>
  );
}
