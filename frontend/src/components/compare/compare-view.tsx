"use client";

import {
  ArrowLeftRight,
  ArrowUpDown,
  Check,
  CircleAlert,
  Cog,
  GitCompareArrows,
  History,
  LoaderCircle,
  SearchX,
  X,
} from "lucide-react";
import { useSearchParams } from "next/navigation";
import { useMemo, useState } from "react";
import { Icon } from "@/components/icons";
import { EmptyState } from "@/components/common/empty-state";
import { ErrorState } from "@/components/common/error-state";
import { PageHeader } from "@/components/common/page-header";
import { PageShell } from "@/components/common/page-shell";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuLabel,
  DropdownMenuRadioGroup,
  DropdownMenuRadioItem,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";
import { FieldLabel } from "@/components/ui/field-label";
import { IconButton } from "@/components/ui/icon-button";
import { Progress } from "@/components/ui/progress";
import { Select } from "@/components/ui/select";
import { Skeleton } from "@/components/ui/skeleton";
import { COMPARE_STAGES, getComparison, runComparison } from "@/lib/api/client";
import { useComparisons, useDocuments } from "@/lib/api/hooks";
import {
  isReady,
  SIGNIFICANCE_ORDER,
  type ChangeType,
  type Comparison,
  type Significance,
} from "@/lib/types";
import { cn, formatDateTime, truncate } from "@/lib/utils";
import { ChangeCard, SIG_STYLE } from "./change-card";

type Phase =
  | { kind: "idle" }
  | { kind: "running"; stage: number }
  | { kind: "error"; message: string }
  | { kind: "done"; result: Comparison };

type SigFilter = "ALL" | Significance;
type TypeFilter = "ALL" | ChangeType;
type SortKey = "significance" | "order";

export function CompareView() {
  const sp = useSearchParams();
  const docsQ = useDocuments();
  const histQ = useComparisons();
  const ready = useMemo(() => (docsQ.data ?? []).filter(isReady), [docsQ.data]);

  const [a, setA] = useState(sp.get("a") ?? "");
  const [b, setB] = useState(sp.get("b") ?? "");
  const [phase, setPhase] = useState<Phase>({ kind: "idle" });
  const [sig, setSig] = useState<SigFilter>("ALL");
  const [type, setType] = useState<TypeFilter>("ALL");
  const [category, setCategory] = useState("ALL");
  const [sort, setSort] = useState<SortKey>("significance");

  const same = a !== "" && a === b;
  const running = phase.kind === "running";

  function resetFilters() {
    setSig("ALL");
    setType("ALL");
    setCategory("ALL");
    setSort("significance");
  }

  async function run() {
    if (!a || !b || same) return;
    setPhase({ kind: "running", stage: 0 });
    resetFilters();
    try {
      const result = await runComparison(a, b, (stage) => setPhase({ kind: "running", stage }));
      setPhase({ kind: "done", result });
      void histQ.mutate();
    } catch (e) {
      setPhase({ kind: "error", message: e instanceof Error ? e.message : "The comparison failed." });
    }
  }

  async function openPrior(id: string) {
    setPhase({ kind: "running", stage: 0 });
    resetFilters();
    try {
      const result = await getComparison(id);
      setA(result.docAId);
      setB(result.docBId);
      setPhase({ kind: "done", result });
    } catch (e) {
      setPhase({ kind: "error", message: e instanceof Error ? e.message : "Couldn't open this comparison." });
    }
  }

  const prior = histQ.data ?? [];

  return (
    <PageShell>
      <PageHeader
        title="Compare contracts"
        subtitle="Clause-aware comparison. Changes are rated by how much they matter."
        actions={
          <DropdownMenu>
            <DropdownMenuTrigger asChild>
              <Button aria-label="Previous comparisons" disabled={prior.length === 0}>
                <History />
                <span className="tabular-nums">{prior.length}</span>
              </Button>
            </DropdownMenuTrigger>
            <DropdownMenuContent align="end" className="w-72">
              <DropdownMenuLabel>Previous comparisons</DropdownMenuLabel>
              {prior.map((p) => (
                <DropdownMenuItem key={p.id} onSelect={() => void openPrior(p.id)} className="flex-col items-start gap-0.5">
                  <span className="text-sm font-medium">
                    {truncate(p.docAName, 22)} → {truncate(p.docBName, 22)}
                  </span>
                  <span className="text-xs text-ink-subtle">
                    {p.total} changes · {formatDateTime(p.createdAt)}
                  </span>
                </DropdownMenuItem>
              ))}
            </DropdownMenuContent>
          </DropdownMenu>
        }
      />

      <section className="mt-5 rounded-card border border-line bg-surface p-4 shadow-card sm:p-5" aria-label="Choose documents">
        <div className="grid items-end gap-3 sm:grid-cols-[1fr_auto_1fr]">
          <div>
            <FieldLabel htmlFor="doc-a">Document A (baseline)</FieldLabel>
            <Select id="doc-a" value={a} onChange={(e) => setA(e.target.value)} disabled={running || docsQ.isLoading}>
              <option value="">Select…</option>
              {ready.map((d) => (
                <option key={d.id} value={d.id}>
                  {d.name}
                </option>
              ))}
            </Select>
          </div>
          <IconButton
            label="Swap documents"
            icon={ArrowLeftRight}
            variant="outline"
            size="iconMd"
            className="mx-auto h-10 w-10"
            disabled={running}
            onClick={() => {
              setA(b);
              setB(a);
            }}
          />
          <div>
            <FieldLabel htmlFor="doc-b">Document B (revised)</FieldLabel>
            <Select id="doc-b" value={b} onChange={(e) => setB(e.target.value)} disabled={running || docsQ.isLoading}>
              <option value="">Select…</option>
              {ready.map((d) => (
                <option key={d.id} value={d.id}>
                  {d.name}
                </option>
              ))}
            </Select>
          </div>
        </div>

        <div className="mt-4 flex flex-wrap items-center gap-3">
          <Button variant="primary" size="lg" onClick={() => void run()} disabled={!a || !b || same || running}>
            {running ? <LoaderCircle className="animate-spin" /> : <GitCompareArrows />}
            Compare
          </Button>
          {same ? (
            <p role="alert" className="flex items-center gap-1.5 text-xs font-medium text-danger">
              <CircleAlert className="size-4" aria-hidden /> Choose two different documents.
            </p>
          ) : null}
          {docsQ.error ? <p className="text-xs text-danger">Couldn&apos;t load documents.</p> : null}
        </div>
      </section>

      <div className="mt-5" aria-live="polite">
        {phase.kind === "idle" ? (
          <div className="rounded-card border border-dashed border-line-strong bg-surface/60">
            <EmptyState icon={GitCompareArrows} title="Pick two versions" hint="Changes show up here, most important first." />
          </div>
        ) : phase.kind === "running" ? (
          <RunningCard stage={phase.stage} />
        ) : phase.kind === "error" ? (
          <div className="rounded-card border border-line bg-surface">
            <ErrorState title="Comparison failed" message={phase.message} onRetry={() => void run()} />
          </div>
        ) : (
          <Results
            result={phase.result}
            sig={sig}
            setSig={setSig}
            type={type}
            setType={setType}
            category={category}
            setCategory={setCategory}
            sort={sort}
            setSort={setSort}
            onClear={resetFilters}
          />
        )}
      </div>
    </PageShell>
  );
}

function RunningCard({ stage }: { stage: number }) {
  return (
    <div className="rounded-card border border-line bg-surface p-5 shadow-card" role="status">
      <Progress value={((stage + 0.5) / COMPARE_STAGES.length) * 100} label="Comparison progress" />
      <ol className="mt-4 space-y-2.5">
        {COMPARE_STAGES.map((label, i) => (
          <li key={label} className={cn("flex items-center gap-2.5 text-sm", i > stage ? "text-ink-subtle" : "text-ink")}>
            {i < stage ? (
              <Check className="size-4 text-ok" aria-hidden />
            ) : i === stage ? (
              <LoaderCircle className="size-4 animate-spin text-brand" aria-hidden />
            ) : (
              <span className="grid size-4 place-items-center" aria-hidden>
                <span className="size-1.5 rounded-full bg-line-strong" />
              </span>
            )}
            {label}
          </li>
        ))}
      </ol>
      <div className="mt-5 space-y-3" aria-hidden>
        <Skeleton className="h-24 w-full" />
        <Skeleton className="h-24 w-full" />
      </div>
    </div>
  );
}

function Results({
  result,
  sig,
  setSig,
  type,
  setType,
  category,
  setCategory,
  sort,
  setSort,
  onClear,
}: {
  result: Comparison;
  sig: SigFilter;
  setSig: (s: SigFilter) => void;
  type: TypeFilter;
  setType: (t: TypeFilter) => void;
  category: string;
  setCategory: (c: string) => void;
  sort: SortKey;
  setSort: (s: SortKey) => void;
  onClear: () => void;
}) {
  const { changes } = result;
  const categories = useMemo(() => Array.from(new Set(changes.map((c) => c.category))).sort(), [changes]);
  const count = (s: Significance) => changes.filter((c) => c.significance === s).length;

  const visible = useMemo(() => {
    const list = changes.filter(
      (c) =>
        (sig === "ALL" || c.significance === sig) &&
        (type === "ALL" || c.type === type) &&
        (category === "ALL" || c.category === category),
    );
    return list.sort((x, y) =>
      sort === "order" ? x.order - y.order : SIGNIFICANCE_ORDER[x.significance] - SIGNIFICANCE_ORDER[y.significance] || x.order - y.order,
    );
  }, [changes, sig, type, category, sort]);

  const filtered = sig !== "ALL" || type !== "ALL" || category !== "ALL";
  const chips: { key: SigFilter; label: string; n: number; dot: string }[] = [
    { key: "ALL", label: "All", n: changes.length, dot: "bg-ink" },
    ...(["HIGH", "MEDIUM", "LOW", "COSMETIC"] as const).map((s) => ({
      key: s,
      label: SIG_STYLE[s].label,
      n: count(s),
      dot: SIG_STYLE[s].dot,
    })),
  ];

  return (
    <div className="space-y-4">
      <section className="rounded-card border border-line bg-surface p-4 shadow-card sm:p-5" aria-label="Summary">
        <div className="flex items-center justify-between gap-3">
          <h2 className="text-sm font-semibold text-ink">Summary</h2>
          <Badge tone={result.summarySource === "ai" ? "accent" : "neutral"}>
            {result.summarySource === "ai" ? <Icon name="nodes" /> : <Cog />}
            {result.summarySource === "ai" ? "AI" : "automatic"}
          </Badge>
        </div>
        <p className="mt-2 text-sm leading-6 text-ink-muted">{result.summary}</p>
        <p className="mt-2 text-xs text-ink-subtle">
          {result.docAName} → {result.docBName} · {result.unchangedCount} unchanged clauses
        </p>
        <div className="mt-3 flex flex-wrap gap-2" role="group" aria-label="Filter by significance">
          {chips.map((c) => (
            <button
              key={c.key}
              type="button"
              aria-pressed={sig === c.key}
              onClick={() => setSig(c.key)}
              className={cn(
                "inline-flex items-center gap-1.5 rounded-full border px-3 py-1 text-xs font-medium transition-colors",
                sig === c.key ? "border-brand bg-brand-soft text-brand" : "border-line-strong bg-surface text-ink-muted hover:bg-canvas",
              )}
            >
              <span className={cn("size-2 rounded-full", c.dot)} aria-hidden />
              {c.label}
              <span className="tabular-nums font-semibold">{c.n}</span>
            </button>
          ))}
        </div>
      </section>

      <div className="flex flex-wrap items-center gap-2">
        <div className="w-36">
          <Select aria-label="Filter by type" className="h-9 text-xs" value={type} onChange={(e) => setType(e.target.value as TypeFilter)}>
            <option value="ALL">All types</option>
            <option value="MODIFIED">Modified</option>
            <option value="ADDED">Added</option>
            <option value="REMOVED">Removed</option>
            <option value="MOVED">Moved</option>
          </Select>
        </div>
        <div className="w-40">
          <Select aria-label="Filter by category" className="h-9 text-xs" value={category} onChange={(e) => setCategory(e.target.value)}>
            <option value="ALL">All categories</option>
            {categories.map((c) => (
              <option key={c} value={c}>
                {c}
              </option>
            ))}
          </Select>
        </div>
        <DropdownMenu>
          <DropdownMenuTrigger asChild>
            <Button size="md" aria-label="Sort changes">
              <ArrowUpDown />
              <span className="text-xs">{sort === "significance" ? "Most important" : "Document order"}</span>
            </Button>
          </DropdownMenuTrigger>
          <DropdownMenuContent align="start">
            <DropdownMenuRadioGroup value={sort} onValueChange={(v) => setSort(v as SortKey)}>
              <DropdownMenuRadioItem value="significance">Most important first</DropdownMenuRadioItem>
              <DropdownMenuRadioItem value="order">Document order</DropdownMenuRadioItem>
            </DropdownMenuRadioGroup>
          </DropdownMenuContent>
        </DropdownMenu>
        {filtered ? (
          <Button variant="ghost" size="sm" onClick={onClear}>
            <X /> Clear
          </Button>
        ) : null}
        <span className="ml-auto text-xs text-ink-subtle">
          {visible.length} of {changes.length}
        </span>
      </div>

      {visible.length === 0 ? (
        <div className="rounded-card border border-line bg-surface">
          <EmptyState
            icon={SearchX}
            title="No changes match"
            hint="Try a different filter."
            action={<Button onClick={onClear}>Clear filters</Button>}
          />
        </div>
      ) : (
        <ul className="space-y-3">
          {visible.map((c) => (
            <li key={c.id}>
              <ChangeCard change={c} docAId={result.docAId} docBId={result.docBId} />
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}
