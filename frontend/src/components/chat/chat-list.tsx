"use client";

import { Check, CheckSquare, MessagesSquare, Plus, Trash2, X } from "lucide-react";
import Link from "next/link";
import { useEffect, useMemo, useState } from "react";
import { EmptyState } from "@/components/common/empty-state";
import { ErrorState } from "@/components/common/error-state";
import { Button } from "@/components/ui/button";
import { Checkbox } from "@/components/ui/checkbox";
import { IconButton } from "@/components/ui/icon-button";
import { Skeleton } from "@/components/ui/skeleton";
import type { ChatSummary } from "@/lib/types";
import { cn } from "@/lib/utils";

export function ChatList({
  chats,
  loading,
  error,
  onRetry,
  activeId,
  onNew,
  onDeleteIds,
  onNavigate,
}: {
  chats: ChatSummary[] | undefined;
  loading: boolean;
  error: Error | undefined;
  onRetry: () => void;
  activeId: string | null;
  onNew: () => void;
  /** Receives the ids to remove; used for both single-row and batch deletes. */
  onDeleteIds: (ids: string[]) => void;
  onNavigate?: () => void;
}) {
  const ids = useMemo(() => (chats ?? []).map((c) => c.id), [chats]);
  const [selecting, setSelecting] = useState(false);
  const [selected, setSelected] = useState<Set<string>>(new Set());

  // Prune selections that vanished (after a delete/reload) and leave select mode
  // once nothing remains, so the toolbar never shows a stale "0 selected".
  useEffect(() => {
    setSelected((prev) => {
      const next = new Set([...prev].filter((id) => ids.includes(id)));
      return next.size === prev.size ? prev : next;
    });
    if (ids.length === 0) setSelecting(false);
  }, [ids]);

  const allSelected = ids.length > 0 && selected.size === ids.length;
  const someSelected = selected.size > 0 && !allSelected;

  function toggle(id: string) {
    setSelected((prev) => {
      const next = new Set(prev);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });
  }
  function toggleAll() {
    setSelected(allSelected ? new Set() : new Set(ids));
  }
  function exitSelect() {
    setSelecting(false);
    setSelected(new Set());
  }
  function removeSelected() {
    if (selected.size === 0) return;
    // Hand off to the parent's confirm dialog. We intentionally keep the current
    // selection so cancelling preserves it; on success the rows disappear and the
    // pruning effect clears them automatically.
    onDeleteIds([...selected]);
  }

  return (
    <div className="flex h-full min-h-0 flex-col">
      <div className="flex flex-wrap items-center justify-between gap-x-2 gap-y-2 px-4 py-3.5">
        {selecting ? (
          <>
            <label className="flex shrink-0 items-center gap-2 text-sm font-semibold text-ink">
              <Checkbox
                checked={allSelected ? true : someSelected ? "indeterminate" : false}
                onCheckedChange={toggleAll}
                aria-label="Select all chats"
              />
              <span className="whitespace-nowrap tabular-nums">
                {selected.size > 0 ? `${selected.size} selected` : "Select all"}
              </span>
            </label>
            <div className="ml-auto flex shrink-0 items-center gap-1">
              <Button size="sm" variant="dangerSolid" onClick={removeSelected} disabled={selected.size === 0}>
                <Trash2 /> Delete
              </Button>
              <IconButton label="Done selecting" icon={X} onClick={exitSelect} />
            </div>
          </>
        ) : (
          <>
            <h2 className="text-sm font-semibold text-ink">Recent chats</h2>
            <div className="flex items-center gap-1">
              {ids.length > 0 ? (
                <IconButton label="Select chats" icon={CheckSquare} onClick={() => setSelecting(true)} />
              ) : null}
              <Button size="sm" onClick={() => { onNew(); onNavigate?.(); }}>
                <Plus /> New chat
              </Button>
            </div>
          </>
        )}
      </div>
      <div className="scroll-thin min-h-0 flex-1 overflow-y-auto px-2 pb-3">
        {loading ? (
          <div className="space-y-2 px-2" aria-busy="true" aria-label="Loading chats">
            {Array.from({ length: 7 }).map((_, i) => (
              <Skeleton key={i} className="h-8 w-full" />
            ))}
          </div>
        ) : error ? (
          <ErrorState className="py-8" title="Couldn't load chats" onRetry={onRetry} />
        ) : !chats || chats.length === 0 ? (
          <EmptyState className="py-8" icon={MessagesSquare} title="No chats yet" hint="Your questions show up here." />
        ) : (
          <ul className="space-y-0.5">
            {chats.map((c) => {
              const active = c.id === activeId;
              if (selecting) {
                const on = selected.has(c.id);
                return (
                  <li key={c.id}>
                    <button
                      type="button"
                      onClick={() => toggle(c.id)}
                      aria-pressed={on}
                      title={c.title}
                      className={cn(
                        "flex w-full items-center gap-2.5 rounded-control py-2 pl-2 pr-3 text-sm transition-colors",
                        on ? "bg-brand-soft font-semibold text-brand" : "text-ink-muted hover:bg-canvas hover:text-ink",
                      )}
                    >
                      <span
                        aria-hidden
                        className={cn(
                          "grid size-[18px] shrink-0 place-items-center rounded border",
                          on ? "border-brand bg-brand text-white" : "border-line-strong bg-surface",
                        )}
                      >
                        {on ? <Check className="size-3.5" strokeWidth={3} /> : null}
                      </span>
                      <span className="truncate">{c.title}</span>
                    </button>
                  </li>
                );
              }
              return (
                <li key={c.id} className="group relative">
                  <Link
                    href={`/chats?c=${c.id}`}
                    scroll={false}
                    onClick={onNavigate}
                    aria-current={active ? "page" : undefined}
                    title={c.title}
                    className={cn(
                      "block truncate rounded-control py-2 pl-3 pr-9 text-sm transition-colors",
                      active ? "bg-brand-soft font-semibold text-brand" : "text-ink-muted hover:bg-canvas hover:text-ink",
                    )}
                  >
                    {c.title}
                  </Link>
                  <button
                    type="button"
                    aria-label={`Delete chat: ${c.title}`}
                    onClick={() => onDeleteIds([c.id])}
                    className="absolute right-1.5 top-1/2 grid size-7 -translate-y-1/2 place-items-center rounded-md text-ink-subtle opacity-0 hover:bg-danger-soft hover:text-danger focus-visible:opacity-100 group-hover:opacity-100"
                  >
                    <Trash2 className="size-3.5" />
                  </button>
                </li>
              );
            })}
          </ul>
        )}
      </div>
    </div>
  );
}
