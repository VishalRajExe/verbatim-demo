"use client";

import { History, MessagesSquare } from "lucide-react";
import { useRouter, useSearchParams } from "next/navigation";
import { useEffect, useMemo, useRef, useState } from "react";
import { mutate as globalMutate } from "swr";
import { ConfirmDialog } from "@/components/common/confirm-dialog";
import { EmptyState } from "@/components/common/empty-state";
import { ErrorState } from "@/components/common/error-state";
import { Dialog, DialogTitle, SheetContent } from "@/components/ui/dialog";
import { IconButton } from "@/components/ui/icon-button";
import { Skeleton } from "@/components/ui/skeleton";
import { useToast } from "@/components/ui/toast";
import { QuoteSheet } from "@/components/viewer/quote-sheet";
import {
  askQuestionWithId,
  deleteChat,
  isAbortError,
  type AskEvent,
} from "@/lib/api/client";
import { useChat, useChats, useDocuments } from "@/lib/api/hooks";
import { isReady, type Coverage, type Message, type Quote } from "@/lib/types";
import { ChatList } from "./chat-list";
import { Composer } from "./composer";
import { DocPicker, MAX_DOCS } from "./doc-picker";
import { AssistantMessage, UserMessage, type AssistantView } from "./message-view";

interface Live {
  chatId: string;
  question: string;
  stage: string | null;
  text: string;
  quotes: Quote[];
  coverage: Coverage[];
  kind: Message["kind"];
}

const SUGGESTIONS = ["What is the liability cap?", "How can either party terminate?", "When must the Customer pay?"];

function applyEvent(l: Live, ev: AskEvent): Live {
  switch (ev.type) {
    case "stage":
      return { ...l, stage: ev.label };
    case "quotes":
      return { ...l, quotes: ev.quotes, coverage: ev.coverage, kind: ev.kind };
    case "token":
      return { ...l, text: l.text + ev.text };
  }
}

export function ChatWorkspace() {
  const sp = useSearchParams();
  const router = useRouter();
  const { toast } = useToast();
  const chatId = sp.get("c");

  const docsQ = useDocuments();
  const chatsQ = useChats();
  const chatQ = useChat(chatId);
  const readyDocs = useMemo(() => (docsQ.data ?? []).filter(isReady), [docsQ.data]);

  const [selected, setSelected] = useState<string[]>(() => sp.getAll("doc"));
  const [draft, setDraft] = useState("");
  const [focusSignal, setFocusSignal] = useState(0);
  const [live, setLive] = useState<Live | null>(null);
  const [openQuote, setOpenQuote] = useState<Quote | null>(null);
  const [historyOpen, setHistoryOpen] = useState(false);
  const [deleteId, setDeleteId] = useState<string | null>(null);
  const [deleting, setDeleting] = useState(false);

  const liveRef = useRef<Live | null>(null);
  const abortRef = useRef<AbortController | null>(null);
  const scrollRef = useRef<HTMLDivElement>(null);
  // Track actual conversation ID (resolved from stream meta event)
  const resolvedConvId = useRef<string | null>(chatId);

  // Opening a past chat restores the documents it was asked about.
  const loadedId = chatQ.data?.id;
  const loadedDocs = chatQ.data?.documentIds;
  useEffect(() => {
    if (loadedDocs && loadedDocs.length > 0) setSelected(loadedDocs);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [loadedId]);

  const showLive = live !== null && live.chatId === (resolvedConvId.current ?? chatId ?? "live");
  const base = chatQ.data?.messages ?? [];
  const shown = showLive && base[base.length - 1]?.role === "user" ? base.slice(0, -1) : base;

  // Keep the newest content in view, unless the reader scrolled up.
  useEffect(() => {
    const el = scrollRef.current;
    if (!el) return;
    if (el.scrollHeight - el.scrollTop - el.clientHeight < 180) el.scrollTop = el.scrollHeight;
  }, [shown.length, live?.text, live?.stage]);

  useEffect(() => {
    const id = requestAnimationFrame(() => {
      const el = scrollRef.current;
      if (el) el.scrollTop = el.scrollHeight;
    });
    return () => cancelAnimationFrame(id);
  }, [loadedId]);

  function updateLive(fn: (l: Live) => Live) {
    const cur = liveRef.current;
    if (!cur) return;
    const next = fn(cur);
    liveRef.current = next;
    setLive(next);
  }

  async function send(text: string) {
    const question = text.trim();
    if (!question || liveRef.current || selected.length === 0) return;
    setDraft("");

    // We use the current chatId or null (backend will create a new one)
    const existingId = chatId && chatId !== "__pending__" ? chatId : null;
    const tempId = existingId ?? "live";

    const controller = new AbortController();
    abortRef.current = controller;
    const initial: Live = {
      chatId: tempId,
      question,
      stage: "Starting",
      text: "",
      quotes: [],
      coverage: [],
      kind: "answer",
    };
    liveRef.current = initial;
    setLive(initial);

    let failure: string | null = null;
    let newConvId: string | null = existingId;

    try {
      newConvId = await askQuestionWithId(
        {
          question,
          documentIds: selected,
          signal: controller.signal,
          conversationId: existingId ?? undefined,
        },
        (ev) => updateLive((l) => applyEvent(l, ev)),
      );
    } catch (err) {
      if (isAbortError(err)) {
        // stopped — keep partial answer
      } else {
        failure = err instanceof Error ? err.message : "Something went wrong.";
      }
    }

    // Navigate to the real conversation once we have the ID
    if (newConvId && newConvId !== existingId) {
      resolvedConvId.current = newConvId;
      router.replace(`/chats?c=${newConvId}`, { scroll: false });
    }

    liveRef.current = null;
    abortRef.current = null;
    setLive(null);

    const finalId = newConvId ?? existingId;
    if (finalId && finalId !== "__pending__") {
      await Promise.all([globalMutate(`chat:${finalId}`), chatsQ.mutate()]);
    }

    if (failure) {
      toast(failure, "error");
    }
  }

  async function retry() {
    if (!chatId || liveRef.current) return;
    // Re-fetch chat to find the last user message
    try {
      const chat = await (await import("@/lib/api/client")).getChat(chatId);
      const lastUser = [...chat.messages].reverse().find((m) => m.role === "user");
      if (lastUser) {
        await globalMutate(`chat:${chatId}`);
        await send(lastUser.content);
      }
    } catch {
      toast("Couldn't retry. Try again.", "error");
    }
  }

  function newChat() {
    setSelected([]);
    setDraft("");
    resolvedConvId.current = null;
    router.push("/chats", { scroll: false });
  }

  async function confirmDelete() {
    if (!deleteId) return;
    setDeleting(true);
    try {
      await deleteChat(deleteId);
      if (deleteId === chatId) router.replace("/chats", { scroll: false });
      await chatsQ.mutate();
      toast("Chat deleted", "success");
      setDeleteId(null);
    } catch {
      toast("Couldn't delete. Try again.", "error");
    } finally {
      setDeleting(false);
    }
  }

  const copy = (text: string) => {
    void navigator.clipboard?.writeText(text.replace(/\s?\[Q\d+\]/g, ""));
    toast("Answer copied", "success");
  };

  const toggleDoc = (id: string) =>
    setSelected((prev) => (prev.includes(id) ? prev.filter((x) => x !== id) : prev.length >= MAX_DOCS ? prev : [...prev, id]));

  const list = (onNavigate?: () => void) => (
    <ChatList
      chats={chatsQ.data}
      loading={chatsQ.isLoading}
      error={chatsQ.error}
      onRetry={() => void chatsQ.mutate()}
      activeId={chatId}
      onNew={newChat}
      onDelete={setDeleteId}
      onNavigate={onNavigate}
    />
  );

  const streaming = live !== null;
  const blocked = selected.length === 0 ? "Select at least one document" : null;
  const threadLoading = Boolean(chatId) && chatId !== "__pending__" && chatQ.isLoading && !showLive;

  return (
    <div className="flex h-full min-h-0">
      <aside className="hidden w-64 shrink-0 border-r border-line bg-surface lg:block xl:w-72" aria-label="Chat history">
        {list()}
      </aside>

      <section className="flex min-w-0 flex-1 flex-col">
        <header className="flex items-start gap-2 border-b border-line bg-surface px-4 py-3 sm:px-5">
          <IconButton label="Chat history" icon={History} className="lg:hidden" onClick={() => setHistoryOpen(true)} />
          <div className="min-w-0 flex-1">
            <DocPicker
              docs={readyDocs}
              loading={docsQ.isLoading}
              selectedIds={selected}
              onToggle={toggleDoc}
              onClear={() => setSelected([])}
              disabled={streaming}
            />
          </div>
        </header>

        <div ref={scrollRef} className="scroll-thin min-h-0 flex-1 overflow-y-auto bg-canvas">
          <div className="mx-auto w-full max-w-3xl space-y-7 px-4 py-6 sm:px-5">
            {threadLoading ? (
              <div className="space-y-3" aria-busy="true" aria-label="Loading chat">
                <Skeleton className="h-4 w-2/5" />
                <Skeleton className="h-4 w-full" />
                <Skeleton className="h-4 w-4/5" />
              </div>
            ) : chatId && chatQ.error ? (
              <ErrorState title="Couldn't open this chat" message={chatQ.error.message} onRetry={() => void chatQ.mutate()} />
            ) : shown.length === 0 && !showLive ? (
              <EmptyState
                icon={MessagesSquare}
                title="Ask about your contracts"
                hint="Pick one or more documents above, then ask."
                action={SUGGESTIONS.map((s) => (
                  <button
                    key={s}
                    type="button"
                    onClick={() => {
                      setDraft(s);
                      setFocusSignal((n) => n + 1);
                    }}
                    className="rounded-full border border-line-strong bg-surface px-3 py-1.5 text-xs font-medium text-ink-muted hover:bg-canvas"
                  >
                    {s}
                  </button>
                ))}
              />
            ) : (
              <>
                {shown.map((m, i) =>
                  m.role === "user" ? (
                    <UserMessage key={m.id} text={m.content} />
                  ) : (
                    <AssistantMessage
                      key={m.id}
                      m={{ ...m, stage: null }}
                      onOpenQuote={setOpenQuote}
                      onCopy={copy}
                      onRetry={m.status === "error" && i === shown.length - 1 ? () => void retry() : undefined}
                    />
                  ),
                )}
                {showLive && live ? (
                  <>
                    <UserMessage text={live.question} />
                    <AssistantMessage
                      m={toView(live)}
                      onOpenQuote={setOpenQuote}
                      onCopy={copy}
                    />
                  </>
                ) : null}
              </>
            )}
          </div>
        </div>

        <Composer
          value={draft}
          onChange={setDraft}
          onSend={() => void send(draft)}
          onStop={() => abortRef.current?.abort()}
          streaming={streaming}
          blockedReason={blocked}
          focusSignal={focusSignal}
        />
      </section>

      <QuoteSheet quote={openQuote} onClose={() => setOpenQuote(null)} />

      <Dialog open={historyOpen} onOpenChange={setHistoryOpen}>
        <SheetContent side="left" aria-describedby={undefined}>
          <DialogTitle className="sr-only">Chat history</DialogTitle>
          {list(() => setHistoryOpen(false))}
        </SheetContent>
      </Dialog>

      <ConfirmDialog
        open={deleteId !== null}
        onOpenChange={(o) => (o ? undefined : setDeleteId(null))}
        title="Delete this chat?"
        description="The conversation and its quotes will be removed."
        busy={deleting}
        onConfirm={() => void confirmDelete()}
      />
    </div>
  );
}

function toView(l: Live): AssistantView {
  return {
    id: "live",
    content: l.text,
    status: "streaming",
    kind: l.kind,
    quotes: l.quotes,
    coverage: l.coverage,
    errorMessage: null,
    stage: l.stage,
  };
}
