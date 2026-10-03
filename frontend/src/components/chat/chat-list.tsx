"use client";

import { MessagesSquare, Plus, Trash2 } from "lucide-react";
import Link from "next/link";
import { EmptyState } from "@/components/common/empty-state";
import { ErrorState } from "@/components/common/error-state";
import { Button } from "@/components/ui/button";
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
  onDelete,
  onNavigate,
}: {
  chats: ChatSummary[] | undefined;
  loading: boolean;
  error: Error | undefined;
  onRetry: () => void;
  activeId: string | null;
  onNew: () => void;
  onDelete: (id: string) => void;
  onNavigate?: () => void;
}) {
  return (
    <div className="flex h-full min-h-0 flex-col">
      <div className="flex items-center justify-between gap-2 px-4 py-3.5">
        <h2 className="text-sm font-semibold text-ink">Recent chats</h2>
        <Button size="sm" onClick={() => { onNew(); onNavigate?.(); }}>
          <Plus /> New chat
        </Button>
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
                    onClick={() => onDelete(c.id)}
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
