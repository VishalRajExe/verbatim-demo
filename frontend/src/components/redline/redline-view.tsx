"use client";

import { Check, ChevronDown, ChevronLeft, ChevronRight, ChevronsUpDown, CircleAlert, CircleX, FileText, LoaderCircle, Minus, Plus, RefreshCw, SearchX, Trash2 } from "lucide-react";
import Link from "next/link";
import { useMemo, useState } from "react";
import { mutate as globalMutate } from "swr";
import { ConfirmDialog } from "@/components/common/confirm-dialog";
import { DocListPicker } from "@/components/common/doc-list-picker";
import { EmptyState } from "@/components/common/empty-state";
import { ErrorState } from "@/components/common/error-state";
import { FileIcon } from "@/components/common/file-icon";
import { MiddleTruncate } from "@/components/common/middle-truncate";
import { PageShell } from "@/components/common/page-shell";
import { Icon } from "@/components/icons";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { IconButton } from "@/components/ui/icon-button";
import { Input } from "@/components/ui/input";
import { Popover, PopoverContent, PopoverTrigger } from "@/components/ui/popover";
import { Skeleton } from "@/components/ui/skeleton";
import { Tabs, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { Textarea } from "@/components/ui/textarea";
import { useToast } from "@/components/ui/toast";
import { API_BASE, applyRedline, deleteRedline, proposeRedline, redlineDownloadUrl, type ProposeInput } from "@/lib/api/client";
import { useDocuments, useRedlines } from "@/lib/api/hooks";
import {
  InstructionSchema,
  isReady,
  ManualEditSchema,
  sessionStatus,
  type RedlineEdit,
  type RedlineSession,
} from "@/lib/types";
import { cn, formatDateTime } from "@/lib/utils";
import { EditRow } from "./edit-row";

type Mode = "plain" | "manual";
interface Row {
  id: number;
  target: string;
  replacement: string;
}
type Phase =
  | { kind: "idle" }
  | { kind: "proposing"; label: string }
  | { kind: "review"; edits: RedlineEdit[]; include: Set<string>; label: string }
  | { kind: "applied"; session: RedlineSession; label: string }
  | { kind: "error"; message: string; label: string };

function DownloadGlyph({ className }: { className?: string }) {
  return <Icon name="download" className={className} />;
}

const SECTION_LABEL = "text-[11px] font-semibold uppercase tracking-[0.08em] text-ink";
const SESSIONS_PER_PAGE = 8;

export function RedlineView() {
  const { toast } = useToast();
  const docsQ = useDocuments();
  const sessionsQ = useRedlines();
  const docxDocs = useMemo(() => (docsQ.data ?? []).filter((d) => d.kind === "docx" && isReady(d)), [docsQ.data]);

  const [docId, setDocId] = useState("");
  const [docOpen, setDocOpen] = useState(false);
  const [author, setAuthor] = useState("Verbatim AI");
  const [mode, setMode] = useState<Mode>("plain");
  const [instruction, setInstruction] = useState("");
  const [rows, setRows] = useState<Row[]>([{ id: 1, target: "", replacement: "" }]);
  const [formError, setFormError] = useState<string | null>(null);
  const [phase, setPhase] = useState<Phase>({ kind: "idle" });
  const [draftId, setDraftId] = useState<string | null>(null);
  const [applying, setApplying] = useState(false);
  const [expanded, setExpanded] = useState<string | null>(null);
  const [sessionPage, setSessionPage] = useState(0);
  const [deleteId, setDeleteId] = useState<string | null>(null);
  const [deleting, setDeleting] = useState(false);

  const busy = phase.kind === "proposing" || applying;
  const doc = docxDocs.find((d) => d.id === docId) ?? null;
  const sessions = sessionsQ.data ?? [];
  const sessionPages = Math.max(1, Math.ceil(sessions.length / SESSIONS_PER_PAGE));
  const safeSessionPage = Math.min(sessionPage, sessionPages - 1);
  const pageSessions = sessions.slice(safeSessionPage * SESSIONS_PER_PAGE, safeSessionPage * SESSIONS_PER_PAGE + SESSIONS_PER_PAGE);
  const shownAuthor = author.trim() || "Verbatim AI";

  async function propose() {
    setFormError(null);
    if (!docId) return setFormError("Choose a DOCX document.");

    let input: ProposeInput;
    let label: string;
    if (mode === "plain") {
      const parsed = InstructionSchema.safeParse(instruction);
      if (!parsed.success) return setFormError(parsed.error.issues[0]?.message ?? "Describe the change.");
      // Pass docId on the input so the real API client can use it
      input = { mode: "plain", instruction: parsed.data, docId } as ProposeInput & { docId: string };
      label = parsed.data;
    } else {
      const filled = rows.filter((r) => r.target.trim() || r.replacement.trim());
      if (filled.length === 0) return setFormError("Add at least one edit.");
      for (const r of filled) {
        const parsed = ManualEditSchema.safeParse(r);
        if (!parsed.success) return setFormError(parsed.error.issues[0]?.message ?? "Check the edits.");
      }
      input = { mode: "manual", rows: filled.map((r) => ({ target: r.target.trim(), replacement: r.replacement.trim() })) };
      label = `${filled.length} manual edit${filled.length === 1 ? "" : "s"}`;
    }

    setDraftId(Math.random().toString(36).slice(2, 8));
    setPhase({ kind: "proposing", label });
    try {
      const edits = await proposeRedline(input);
      setPhase({
        kind: "review",
        edits,
        include: new Set(edits.filter((e) => e.check === "verified").map((e) => e.id)),
        label,
      });
    } catch (e) {
      setPhase({ kind: "error", message: e instanceof Error ? e.message : "Couldn't draft edits.", label });
    }
  }

  async function apply() {
    if (phase.kind !== "review") return;
    setApplying(true);
    try {
      const session = await applyRedline({
        documentId: docId,
        mode,
        instruction: phase.label,
        author: shownAuthor,
        edits: phase.edits,
        includeIds: [...phase.include],
      });
      setPhase({ kind: "applied", session, label: phase.label });
      void sessionsQ.mutate();
      toast("Tracked changes ready", "success");
    } catch {
      toast("Couldn't apply the edits. Try again.", "error");
    } finally {
      setApplying(false);
    }
  }

  async function confirmDelete() {
    if (!deleteId) return;
    setDeleting(true);
    try {
      await deleteRedline(deleteId);
      await sessionsQ.mutate();
      void globalMutate("redlines");
      toast("Session deleted", "success");
      setDeleteId(null);
    } catch {
      toast("Couldn't delete. Try again.", "error");
    } finally {
      setDeleting(false);
    }
  }

  const activeLabel = phase.kind === "idle" ? null : phase.label;
  const readyCount = phase.kind === "review" ? phase.edits.filter((e) => e.check === "verified").length : 0;

  return (
    <PageShell className="pb-16">
      {/* Title */}
      <header className="flex flex-wrap items-start justify-between gap-4">
        <div className="flex min-w-0 items-start gap-3.5">
          <span className="grid size-11 shrink-0 place-items-center rounded-xl border border-line bg-surface text-navy shadow-card">
            <Icon name="docPen" className="size-6" />
          </span>
          <div className="min-w-0">
            <h1 className="font-serif text-[28px] font-semibold leading-tight tracking-tight text-ink">Tracked-Change Redlining</h1>
            <p className="mt-1 max-w-2xl text-sm leading-6 text-ink-subtle">
              Convert plain-language instructions into real Word revisions (
              <code className="font-mono text-[12px] text-ink-muted">w:ins</code> /{" "}
              <code className="font-mono text-[12px] text-ink-muted">w:del</code>) with author{" "}
              <strong className="font-semibold text-ink">{shownAuthor}</strong>.
            </p>
          </div>
        </div>
        <Button asChild>
          <a href="#sessions">
            <Icon name="clock" />
            {sessionsQ.isLoading ? "Sessions" : `${sessions.length} session${sessions.length === 1 ? "" : "s"}`}
          </a>
        </Button>
      </header>

      {/* Document bar */}
      <div className="mt-5 flex flex-wrap items-center gap-2 border-y border-line py-3">
        <span className="mr-1 text-[11px] font-semibold uppercase tracking-[0.08em] text-ink-subtle">Document:</span>
        <Popover open={docOpen} onOpenChange={setDocOpen}>
          <PopoverTrigger asChild>
            <Button disabled={busy || docsQ.isLoading || docxDocs.length === 0} aria-label="Choose document" className="max-w-[14.5rem] justify-between px-3">
              {doc ? <FileIcon kind="docx" className="size-5" /> : null}
              {doc ? <MiddleTruncate text={doc.name} tail={15} className="min-w-0 flex-1 text-left" /> : <span className="truncate">{docsQ.isLoading ? "Loading…" : "Select a DOCX"}</span>}
              <ChevronsUpDown className="text-ink-subtle" />
            </Button>
          </PopoverTrigger>
          <PopoverContent>
            <DocListPicker
              docs={docxDocs}
              selectedIds={docId ? [docId] : []}
              onToggle={(id) => {
                setDocId(id);
                setDocOpen(false);
              }}
              emptyHint="No ready DOCX documents."
            />
          </PopoverContent>
        </Popover>

        {doc ? (
          <Button asChild>
            <Link href={`/documents/${doc.id}`}>
              <Icon name="eye" /> View Word
            </Link>
          </Button>
        ) : (
          <Button disabled>
            <Icon name="eye" /> View Word
          </Button>
        )}
        {doc ? (
          <Button asChild>
            <a href={`${API_BASE}/api/documents/${doc.id}/file`} target="_blank" rel="noopener noreferrer">
              <Icon name="docLines" /> View PDF
            </a>
          </Button>
        ) : (
          <Button disabled>
            <Icon name="docLines" /> View PDF
          </Button>
        )}
        {doc ? (
          <Button asChild>
            <a href={`${API_BASE}/api/documents/${doc.id}/file`} download={doc.name}>
              <Icon name="download" /> Download Original
            </a>
          </Button>
        ) : (
          <Button disabled>
            <Icon name="download" /> Download Original
          </Button>
        )}
        <span className="ml-auto font-mono text-[11px] text-ink-subtle">{draftId ? `Session #${draftId}` : "New session"}</span>
      </div>
      {!docsQ.isLoading && docxDocs.length === 0 ? (
        <p className="mt-2 flex items-center gap-1.5 text-xs text-ink-subtle">
          <CircleAlert className="size-4" aria-hidden /> No ready DOCX documents.{" "}
          <Link href="/documents" className="font-semibold text-brand hover:underline">
            Upload a Word file
          </Link>
        </p>
      ) : null}

      {/* Instruction */}
      <section className="mt-5 rounded-card border border-line bg-surface p-5 shadow-card" aria-label="New redline">
        <div className="flex flex-wrap items-center justify-between gap-3">
          <h2 className={SECTION_LABEL}>Instruction</h2>
          <Tabs value={mode} onValueChange={(v) => setMode(v as Mode)}>
            <TabsList aria-label="Edit mode">
              <TabsTrigger value="plain" className="data-[state=active]:bg-navy">
                Plain language
              </TabsTrigger>
              <TabsTrigger value="manual" className="data-[state=active]:bg-navy">
                Manual edits
              </TabsTrigger>
            </TabsList>
          </Tabs>
        </div>

        {mode === "plain" ? (
          <div className="mt-3 flex flex-col gap-2.5 sm:flex-row sm:items-start">
            <Textarea
              rows={1}
              aria-label="Describe the change"
              placeholder={'e.g. "Change the liability cap from AED 100,000 to AED 1,000,000."'}
              value={instruction}
              disabled={busy}
              onChange={(e) => setInstruction(e.target.value)}
              onKeyDown={(e) => {
                if (e.key === "Enter" && !e.shiftKey) {
                  e.preventDefault();
                  void propose();
                }
              }}
              className="field-sizing-content max-h-40 min-h-11 flex-1 resize-none py-2.5 text-[15px]"
            />
            <Button variant="navy" size="lg" className="h-11 px-5" onClick={() => void propose()} disabled={busy}>
              {phase.kind === "proposing" ? <LoaderCircle className="animate-spin" /> : <Icon name="docPen" />}
              Propose Redline
            </Button>
          </div>
        ) : (
          <div className="mt-3 space-y-2">
            {rows.map((r, i) => (
              <div key={r.id} className="grid items-center gap-2 sm:grid-cols-[1fr_1fr_auto]">
                <Input
                  aria-label={`Original text ${i + 1}`}
                  placeholder="Original text"
                  value={r.target}
                  disabled={busy}
                  className="h-11"
                  onChange={(e) => setRows((prev) => prev.map((x) => (x.id === r.id ? { ...x, target: e.target.value } : x)))}
                />
                <Input
                  aria-label={`New text ${i + 1}`}
                  placeholder="New text"
                  value={r.replacement}
                  disabled={busy}
                  className="h-11"
                  onChange={(e) => setRows((prev) => prev.map((x) => (x.id === r.id ? { ...x, replacement: e.target.value } : x)))}
                />
                <IconButton
                  label="Remove edit"
                  icon={Trash2}
                  disabled={busy || rows.length === 1}
                  onClick={() => setRows((prev) => prev.filter((x) => x.id !== r.id))}
                />
              </div>
            ))}
            <div className="flex flex-wrap items-center justify-between gap-2 pt-1">
              <Button size="sm" disabled={busy} onClick={() => setRows((prev) => [...prev, { id: Date.now(), target: "", replacement: "" }])}>
                <Plus /> Add edit
              </Button>
              <Button variant="navy" size="lg" className="h-11 px-5" onClick={() => void propose()} disabled={busy}>
                {phase.kind === "proposing" ? <LoaderCircle className="animate-spin" /> : <Icon name="docPen" />}
                Propose Redline
              </Button>
            </div>
          </div>
        )}

        {formError ? (
          <p role="alert" className="mt-3 flex items-center gap-1.5 text-xs font-medium text-danger">
            <CircleAlert className="size-4" aria-hidden /> {formError}
          </p>
        ) : null}

        <div className="mt-3.5 flex flex-wrap items-center justify-between gap-x-6 gap-y-2">
          <p className="flex max-w-xl items-start gap-1.5 text-xs leading-5 text-ink-subtle">
            <Icon name="shieldTick" className="mt-0.5 size-4 text-ok" />
            Edits are kept minimal, and each original text must appear exactly once in the document before it is proposed.
          </p>
          <label className="ml-auto flex items-center gap-2 text-xs text-ink-subtle">
            Author
            <Input
              value={author}
              disabled={busy}
              onChange={(e) => setAuthor(e.target.value)}
              aria-label="Revision author"
              className="h-8 w-40 text-xs"
            />
          </label>
        </div>
      </section>

      {/* Active instruction and review */}
      <div className="mt-5" aria-live="polite">
        {activeLabel ? (
          <section className="flex flex-wrap items-center justify-between gap-3 rounded-card border border-line bg-surface px-5 py-4 shadow-card" aria-label="Active instruction">
            <div className="min-w-0">
              <p className="text-[11px] font-semibold uppercase tracking-[0.08em] text-ink-subtle">Active instruction</p>
              <p className="mt-1.5 text-[15px] font-medium text-ink">“{activeLabel}”</p>
            </div>
            {phase.kind === "proposing" ? (
              <Badge className="px-3 py-1 ring-1 ring-inset ring-line-strong">
                <LoaderCircle className="animate-spin" /> Analysing document
              </Badge>
            ) : phase.kind === "review" ? (
              <Badge tone="warn" className="px-3 py-1 ring-1 ring-inset ring-warn/25">
                <CircleAlert /> Proposed ({readyCount} ready)
              </Badge>
            ) : phase.kind === "applied" ? (
              <Badge tone="ok" className="px-3 py-1 ring-1 ring-inset ring-ok/20">
                <Check /> Applied
              </Badge>
            ) : (
              <Badge tone="danger" className="px-3 py-1">
                <CircleX /> Failed
              </Badge>
            )}
          </section>
        ) : null}

        {phase.kind === "proposing" ? (
          <div className="mt-5 space-y-3" role="status" aria-label="Finding the text to change">
            <Skeleton className="h-52 w-full" />
          </div>
        ) : phase.kind === "error" ? (
          <div className="mt-5 rounded-card border border-line bg-surface">
            <ErrorState title="Couldn't draft edits" message={phase.message} onRetry={() => void propose()} />
          </div>
        ) : phase.kind === "review" ? (
          phase.edits.length === 0 ? (
            <div className="mt-5 rounded-card border border-line bg-surface">
              <EmptyState
                icon={SearchX}
                title="No matching text found"
                hint="Nothing in this document fits that request, so no file was made."
                action={<Button onClick={() => setPhase({ kind: "idle" })}>Edit request</Button>}
              />
            </div>
          ) : (
            <section className="mt-7" aria-label="Proposed edits">
              <div className="flex items-center justify-between gap-3">
                <h2 className={SECTION_LABEL}>Proposed minimal edits ({phase.edits.length})</h2>
                <span className="text-xs text-ink-subtle tabular-nums">
                  {phase.include.size} of {phase.edits.length} selected
                </span>
              </div>
              <ul className="mt-3 space-y-3">
                {phase.edits.map((e, i) => (
                  <EditRow
                    key={e.id}
                    edit={e}
                    index={i + 1}
                    checked={phase.include.has(e.id)}
                    onCheckedChange={(on) =>
                      setPhase((p) => {
                        if (p.kind !== "review") return p;
                        const include = new Set(p.include);
                        if (on) include.add(e.id);
                        else include.delete(e.id);
                        return { ...p, include };
                      })
                    }
                  />
                ))}
              </ul>
              <div className="mt-3 flex flex-wrap items-center justify-between gap-3 rounded-card border border-line bg-surface px-5 py-4 shadow-card">
                <p className="text-sm text-ink-muted">
                  {phase.include.size === 0
                    ? "Select at least one revision to apply."
                    : `Ready to apply ${phase.include.size} revision${phase.include.size === 1 ? "" : "s"} to the document.`}
                </p>
                <div className="flex items-center gap-2">
                  <Button variant="ghost" onClick={() => setPhase({ kind: "idle" })} disabled={applying}>
                    Cancel
                  </Button>
                  <Button variant="navy" size="lg" onClick={() => void apply()} disabled={phase.include.size === 0 || applying}>
                    {applying ? <LoaderCircle className="animate-spin" /> : <Icon name="check" strokeWidth={2} />}
                    Apply Selected Edits
                  </Button>
                </div>
              </div>
            </section>
          )
        ) : phase.kind === "applied" ? (
          <section className="mt-3 rounded-card border border-ok/25 bg-surface px-5 py-4 shadow-card" aria-label="Result">
            <div className="flex flex-wrap items-center gap-3">
              <span className="grid size-10 place-items-center rounded-full bg-ok-soft text-ok">
                <Icon name="check" className="size-5" strokeWidth={2} />
              </span>
              <div className="min-w-0 flex-1">
                <p className="text-sm font-semibold text-ink">Tracked changes ready</p>
                <p className="mt-1 flex flex-wrap gap-1.5">
                  <Badge tone="ok">
                    <Plus /> {phase.session.revisions.ins} insertions
                  </Badge>
                  <Badge tone="danger">
                    <Minus /> {phase.session.revisions.del} deletions
                  </Badge>
                </p>
              </div>
              <Button variant="navy" size="lg" asChild>
                <a href={redlineDownloadUrl(phase.session.id)} download>
                  <Icon name="download" /> Download .docx
                </a>
              </Button>
              <Button size="lg" onClick={() => setPhase({ kind: "idle" })}>
                <Plus /> New redline
              </Button>
            </div>
          </section>
        ) : null}
      </div>

      {/* Sessions */}
      <section id="sessions" className="mt-8 scroll-mt-6 rounded-card border border-line bg-surface p-5 shadow-card" aria-label="Redline sessions">
        <div className="flex items-center justify-between">
          <h2 className={SECTION_LABEL}>Redline sessions</h2>
          <Button size="sm" onClick={() => void sessionsQ.mutate()} aria-label="Refresh sessions">
            <RefreshCw className={sessionsQ.isValidating ? "animate-spin" : undefined} />
            <span className="hidden sm:inline">Refresh</span>
          </Button>
        </div>

        <div className="mt-3">
          {sessionsQ.isLoading ? (
            <div className="space-y-2" aria-busy="true" aria-label="Loading sessions">
              {Array.from({ length: 3 }).map((_, i) => (
                <Skeleton key={i} className="h-12 w-full" />
              ))}
            </div>
          ) : sessionsQ.error ? (
            <ErrorState title="Couldn't load sessions" message={sessionsQ.error.message} onRetry={() => void sessionsQ.mutate()} />
          ) : sessions.length === 0 ? (
            <EmptyState icon={FileText} title="No sessions yet" hint="Applied redlines are kept here." />
          ) : (
            <>
            <ul className="space-y-2">
              {pageSessions.map((s) => {
                const st = sessionStatus(s);
                const open = expanded === s.id;
                return (
                  <li key={s.id} className="overflow-hidden rounded-lg border border-line">
                    <button
                      type="button"
                      aria-expanded={open}
                      onClick={() => setExpanded(open ? null : s.id)}
                      className="flex w-full items-center gap-3 px-3.5 py-3 text-left hover:bg-canvas"
                    >
                      <Badge tone={st === "all" ? "ok" : st === "partial" ? "warn" : "danger"}>
                        {st === "all" ? <Check /> : st === "partial" ? <Minus /> : <CircleX />}
                        {st === "all" ? "All applied" : st === "partial" ? "Partly applied" : "Nothing applied"}
                      </Badge>
                      <span className="min-w-0 flex-1 truncate text-sm text-ink">{s.instruction}</span>
                      <span className="hidden max-w-[200px] truncate text-xs text-ink-subtle md:block">{s.documentName}</span>
                      <span className="hidden text-xs text-ink-subtle tabular-nums lg:block">{formatDateTime(s.createdAt)}</span>
                      <ChevronDown className={cn("size-4 shrink-0 text-ink-subtle transition-transform", open && "rotate-180")} aria-hidden />
                    </button>
                    {open ? (
                      <div className="border-t border-line bg-canvas/60 p-3.5">
                        <ul className="space-y-2.5">
                          {s.edits.map((e, i) => (
                            <EditRow key={e.id} edit={e} index={i + 1} readOnly applied={s.appliedIds.includes(e.id)} />
                          ))}
                        </ul>
                        <div className="mt-3 flex items-center justify-between gap-2">
                          <span className="text-xs text-ink-subtle tabular-nums">
                            {s.author} · {s.revisions.ins} insertions · {s.revisions.del} deletions
                          </span>
                          <span className="flex gap-1.5">
                            {s.appliedIds.length > 0 ? (
                              <a href={redlineDownloadUrl(s.id)} download>
                                <IconButton
                                  label="Download .docx"
                                  icon={DownloadGlyph}
                                  variant="outline"
                                />
                              </a>
                            ) : (
                              <IconButton
                                label="Download .docx"
                                icon={DownloadGlyph}
                                variant="outline"
                                disabled
                              />
                            )}
                            <IconButton label="Delete session" icon={Trash2} variant="danger" onClick={() => setDeleteId(s.id)} />
                          </span>
                        </div>
                      </div>
                    ) : null}
                  </li>
                );
              })}
            </ul>
            {sessionPages > 1 ? (
              <div className="mt-3 flex items-center justify-between gap-2">
                <Button size="sm" variant="outline" disabled={safeSessionPage === 0} onClick={() => { setSessionPage(safeSessionPage - 1); setExpanded(null); }}>
                  <ChevronLeft /> Prev
                </Button>
                <span className="text-xs text-ink-subtle tabular-nums">
                  Page {safeSessionPage + 1} of {sessionPages} · {sessions.length} session{sessions.length === 1 ? "" : "s"}
                </span>
                <Button size="sm" variant="outline" disabled={safeSessionPage >= sessionPages - 1} onClick={() => { setSessionPage(safeSessionPage + 1); setExpanded(null); }}>
                  Next <ChevronRight />
                </Button>
              </div>
            ) : null}
            </>
          )}
        </div>
      </section>

      <ConfirmDialog
        open={deleteId !== null}
        onOpenChange={(o) => (o ? undefined : setDeleteId(null))}
        title="Delete this session?"
        description="The proposed edits and the generated file are removed."
        busy={deleting}
        onConfirm={() => void confirmDelete()}
      />
    </PageShell>
  );
}
