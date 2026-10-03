"use client";

import {
  ArrowUpDown,
  Download,
  Eye,
  FileText,
  GitCompareArrows,
  MessageSquare,
  MessagesSquare,
  RefreshCw,
  Search,
  TriangleAlert,
  Trash2,
  Upload,
  X,
} from "lucide-react";
import { useRouter } from "next/navigation";
import { useMemo, useState } from "react";
import { mutate as globalMutate } from "swr";
import { ConfirmDialog } from "@/components/common/confirm-dialog";
import { DocStatusCell } from "@/components/common/doc-status";
import { EmptyState } from "@/components/common/empty-state";
import { ErrorState } from "@/components/common/error-state";
import { FileIcon } from "@/components/common/file-icon";
import { PageHeader } from "@/components/common/page-header";
import { PageShell } from "@/components/common/page-shell";
import { Button } from "@/components/ui/button";
import { Checkbox } from "@/components/ui/checkbox";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuRadioGroup,
  DropdownMenuRadioItem,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";
import { IconButton } from "@/components/ui/icon-button";
import { Input } from "@/components/ui/input";
import { Skeleton } from "@/components/ui/skeleton";
import { useToast } from "@/components/ui/toast";
import { Tip } from "@/components/ui/tooltip";
import { API_BASE, deleteDocument } from "@/lib/api/client";
import { useDocuments } from "@/lib/api/hooks";
import { isReady, type DocumentItem } from "@/lib/types";
import { formatBytes, formatDateTime } from "@/lib/utils";
import { UploadDialog } from "./upload-dialog";

type SortKey = "newest" | "oldest" | "name" | "size";
const SORTS: { key: SortKey; label: string }[] = [
  { key: "newest", label: "Newest first" },
  { key: "oldest", label: "Oldest first" },
  { key: "name", label: "Name A to Z" },
  { key: "size", label: "Largest first" },
];

function sortAndFilter(docs: DocumentItem[], query: string, sort: SortKey): DocumentItem[] {
  const q = query.trim().toLowerCase();
  const list = q ? docs.filter((d) => d.name.toLowerCase().includes(q)) : [...docs];
  list.sort((a, b) => {
    switch (sort) {
      case "oldest":
        return a.createdAt.localeCompare(b.createdAt);
      case "name":
        return a.name.localeCompare(b.name);
      case "size":
        return b.sizeBytes - a.sizeBytes;
      default:
        return b.createdAt.localeCompare(a.createdAt);
    }
  });
  return list;
}

export function DocumentsView() {
  const router = useRouter();
  const { toast } = useToast();
  const { data, error, isLoading, isValidating, mutate } = useDocuments();

  const [query, setQuery] = useState("");
  const [sort, setSort] = useState<SortKey>("newest");
  const [selected, setSelected] = useState<Set<string>>(new Set());
  const [uploadOpen, setUploadOpen] = useState(false);
  const [toDelete, setToDelete] = useState<DocumentItem[] | null>(null);
  const [deleting, setDeleting] = useState(false);

  const rows = useMemo(() => sortAndFilter(data ?? [], query, sort), [data, query, sort]);
  const selectedRows = rows.filter((r) => selected.has(r.id));
  const selectedReady = selectedRows.filter(isReady);
  const allSelected = rows.length > 0 && selectedRows.length === rows.length;

  function toggle(id: string, on: boolean) {
    setSelected((prev) => {
      const next = new Set(prev);
      if (on) next.add(id);
      else next.delete(id);
      return next;
    });
  }

  async function confirmDelete() {
    if (!toDelete) return;
    setDeleting(true);
    try {
      await Promise.all(toDelete.map((d) => deleteDocument(d.id)));
      setSelected(new Set());
      await mutate();
      void globalMutate("chats");
      toast(toDelete.length === 1 ? "Document deleted" : `${toDelete.length} documents deleted`, "success");
      setToDelete(null);
    } catch {
      toast("Couldn't delete. Try again.", "error");
    } finally {
      setDeleting(false);
    }
  }

  const askUrl = (ids: string[]) => `/chats?${ids.map((i) => `doc=${i}`).join("&")}`;

  return (
    <PageShell>
      <PageHeader
        title="Documents"
        subtitle="Upload PDF or DOCX contracts to analyse them."
        actions={
          <>
            <Button onClick={() => void mutate()} aria-label="Refresh">
              <RefreshCw className={isValidating ? "animate-spin" : undefined} />
              <span className="hidden sm:inline">Refresh</span>
            </Button>
            <Button variant="primary" onClick={() => setUploadOpen(true)}>
              <Upload />
              <span className="hidden sm:inline">Upload document</span>
              <span className="sm:hidden">Upload</span>
            </Button>
          </>
        }
      />

      <div className="mt-5 flex flex-wrap items-center gap-2">
        <div className="relative min-w-[200px] flex-1 sm:max-w-xs">
          <Search aria-hidden className="pointer-events-none absolute left-3 top-1/2 size-4 -translate-y-1/2 text-ink-subtle" />
          <Input
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            placeholder="Search"
            aria-label="Search documents"
            className="h-9 pl-9 pr-9"
          />
          {query ? (
            <button
              type="button"
              aria-label="Clear search"
              onClick={() => setQuery("")}
              className="absolute right-2 top-1/2 grid size-6 -translate-y-1/2 place-items-center rounded text-ink-subtle hover:bg-line/60"
            >
              <X className="size-3.5" />
            </button>
          ) : null}
        </div>

        <DropdownMenu>
          <Tip label="Sort">
            <DropdownMenuTrigger asChild>
              <Button aria-label="Sort" size="md">
                <ArrowUpDown />
              </Button>
            </DropdownMenuTrigger>
          </Tip>
          <DropdownMenuContent align="start">
            <DropdownMenuRadioGroup value={sort} onValueChange={(v) => setSort(v as SortKey)}>
              {SORTS.map((s) => (
                <DropdownMenuRadioItem key={s.key} value={s.key}>
                  {s.label}
                </DropdownMenuRadioItem>
              ))}
            </DropdownMenuRadioGroup>
          </DropdownMenuContent>
        </DropdownMenu>

        <span className="ml-auto text-xs text-ink-subtle" aria-live="polite">
          {data ? `${rows.length} of ${data.length}` : ""}
        </span>
      </div>

      {selectedRows.length > 0 ? (
        <div className="mt-3 flex flex-wrap items-center gap-2 rounded-card border border-brand/20 bg-brand-soft px-3 py-2" role="region" aria-label="Selection actions">
          <span className="text-sm font-semibold text-brand">{selectedRows.length} selected</span>
          <span className="mx-1 h-4 w-px bg-brand/20" aria-hidden />
          <IconButton
            label="Ask across selected"
            icon={MessagesSquare}
            disabled={selectedReady.length === 0 || selectedReady.length > 5}
            onClick={() => router.push(askUrl(selectedReady.map((d) => d.id)))}
          />
          <IconButton
            label={selectedReady.length === 2 ? "Compare the two" : "Select two ready documents to compare"}
            icon={GitCompareArrows}
            disabled={selectedReady.length !== 2}
            onClick={() => {
              const [a, b] = selectedReady;
              if (a && b) router.push(`/compare?a=${a.id}&b=${b.id}`);
            }}
          />
          <IconButton label="Delete selected" icon={Trash2} className="text-danger hover:bg-danger-soft/60" onClick={() => setToDelete(selectedRows)} />
          <IconButton label="Clear selection" icon={X} className="ml-auto" onClick={() => setSelected(new Set())} />
        </div>
      ) : null}

      <div className="mt-3 overflow-hidden rounded-card border border-line bg-surface shadow-card">
        {isLoading ? (
          <LoadingRows />
        ) : error ? (
          <ErrorState title="Couldn't load documents" message={error.message} onRetry={() => void mutate()} />
        ) : !data || data.length === 0 ? (
          <EmptyState
            icon={FileText}
            title="No documents yet"
            hint="Upload a PDF or DOCX contract to start asking questions."
            action={
              <Button variant="primary" onClick={() => setUploadOpen(true)}>
                <Upload /> Upload document
              </Button>
            }
          />
        ) : rows.length === 0 ? (
          <EmptyState
            icon={Search}
            title="No matches"
            hint={`Nothing is named “${query}”.`}
            action={<Button onClick={() => setQuery("")}>Clear search</Button>}
          />
        ) : (
          <div className="scroll-thin overflow-x-auto">
            <table className="w-full min-w-[640px] text-left text-sm">
              <thead>
                <tr className="border-b border-line text-[11px] font-semibold uppercase tracking-wide text-ink-subtle">
                  <th className="w-10 py-3 pl-4 font-semibold">
                    <Checkbox
                      aria-label="Select all"
                      checked={allSelected ? true : selectedRows.length > 0 ? "indeterminate" : false}
                      onCheckedChange={(c) => setSelected(c === true ? new Set(rows.map((r) => r.id)) : new Set())}
                    />
                  </th>
                  <th className="px-3 py-3 font-semibold">Name</th>
                  <th className="hidden px-3 py-3 font-semibold md:table-cell">Size</th>
                  <th className="hidden px-3 py-3 font-semibold md:table-cell">Pages</th>
                  <th className="px-3 py-3 font-semibold">Status</th>
                  <th className="px-4 py-3 text-right font-semibold">
                    <span className="sr-only">Actions</span>
                  </th>
                </tr>
              </thead>
              <tbody>
                {rows.map((d) => (
                  <tr key={d.id} className="border-b border-line last:border-0 hover:bg-canvas/70">
                    <td className="py-3 pl-4 align-middle">
                      <Checkbox
                        aria-label={`Select ${d.name}`}
                        checked={selected.has(d.id)}
                        onCheckedChange={(c) => toggle(d.id, c === true)}
                      />
                    </td>
                    <td className="max-w-[360px] px-3 py-3 align-middle">
                      <div className="flex items-center gap-3">
                        <FileIcon kind={d.kind} />
                        <div className="min-w-0">
                          <p className="truncate font-medium text-ink">{d.name}</p>
                          {d.status === "failed" && d.errorMessage ? (
                            <p className="mt-0.5 flex items-start gap-1 text-xs text-danger">
                              <TriangleAlert className="mt-0.5 size-3 shrink-0" aria-hidden />
                              {d.errorMessage}
                            </p>
                          ) : (
                            <p className="mt-0.5 flex items-center gap-1.5 text-xs text-ink-subtle">
                              {formatDateTime(d.createdAt)}
                              {d.warning ? (
                                <Tip label={d.warning}>
                                  <span className="inline-flex text-warn" tabIndex={0} aria-label={d.warning}>
                                    <TriangleAlert className="size-3.5" />
                                  </span>
                                </Tip>
                              ) : null}
                            </p>
                          )}
                          <p className="mt-0.5 text-xs text-ink-subtle md:hidden">
                            {formatBytes(d.sizeBytes)}
                            {d.pages ? ` · ${d.pages} p` : ""}
                          </p>
                        </div>
                      </div>
                    </td>
                    <td className="hidden px-3 py-3 align-middle text-ink-muted md:table-cell">{formatBytes(d.sizeBytes)}</td>
                    <td className="hidden px-3 py-3 align-middle text-ink-muted md:table-cell">{d.pages ?? "—"}</td>
                    <td className="px-3 py-3 align-middle">
                      <DocStatusCell doc={d} />
                    </td>
                    <td className="px-4 py-3 align-middle">
                      <div className="flex items-center justify-end gap-1">
                        {isReady(d) ? (
                          <>
                            <IconButton label="Open" icon={Eye} variant="outline" onClick={() => router.push(`/documents/${d.id}`)} />
                            <IconButton label="Chat" icon={MessageSquare} variant="outline" onClick={() => router.push(askUrl([d.id]))} />
                            <IconButton label="Compare" icon={GitCompareArrows} variant="outline" onClick={() => router.push(`/compare?a=${d.id}`)} />
                            <a href={`${API_BASE}/api/documents/${d.id}/file`} download={d.name} tabIndex={-1}>
                              <IconButton label="Download" icon={Download} variant="outline" />
                            </a>
                          </>
                        ) : null}
                        <IconButton label="Delete" icon={Trash2} variant="danger" onClick={() => setToDelete([d])} />
                      </div>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>

      <UploadDialog open={uploadOpen} onOpenChange={setUploadOpen} />
      <ConfirmDialog
        open={toDelete !== null}
        onOpenChange={(o) => (o ? undefined : setToDelete(null))}
        title={toDelete && toDelete.length > 1 ? `Delete ${toDelete.length} documents?` : "Delete this document?"}
        description={
          toDelete && toDelete.length === 1
            ? `“${toDelete[0]?.name}” and its chats will be removed.`
            : "The documents and their chats will be removed."
        }
        busy={deleting}
        onConfirm={() => void confirmDelete()}
      />
    </PageShell>
  );
}

function LoadingRows() {
  return (
    <div aria-busy="true" aria-label="Loading documents">
      {Array.from({ length: 5 }).map((_, i) => (
        <div key={i} className="flex items-center gap-4 border-b border-line px-4 py-4 last:border-0">
          <Skeleton className="size-[18px]" />
          <Skeleton className="size-8" />
          <div className="flex-1 space-y-2">
            <Skeleton className="h-3.5 w-1/2" />
            <Skeleton className="h-3 w-1/4" />
          </div>
          <Skeleton className="hidden h-6 w-16 rounded-full sm:block" />
          <Skeleton className="h-8 w-32" />
        </div>
      ))}
    </div>
  );
}
