"use client";

import { ChevronsUpDown, Cog, Copy, FileMinus, FilePlus, Minus } from "lucide-react";
import { Icon } from "@/components/icons";
import { useRouter } from "next/navigation";
import { useMemo, useState, type ReactNode } from "react";
import { Badge } from "@/components/ui/badge";
import { IconButton } from "@/components/ui/icon-button";
import { useToast } from "@/components/ui/toast";
import { diffWords } from "@/lib/diff";
import type { Change, Significance } from "@/lib/types";
import { cn } from "@/lib/utils";

export const SIG_STYLE: Record<Significance, { label: string; tone: "danger" | "warn" | "brand" | "neutral"; dot: string }> = {
  HIGH: { label: "High", tone: "danger", dot: "bg-danger" },
  MEDIUM: { label: "Medium", tone: "warn", dot: "bg-warn" },
  LOW: { label: "Low", tone: "brand", dot: "bg-brand" },
  COSMETIC: { label: "Cosmetic", tone: "neutral", dot: "bg-line-strong" },
};

export function ChangeCard({ change, docAId, docBId }: { change: Change; docAId: string; docBId: string }) {
  const router = useRouter();
  const { toast } = useToast();
  const parts = useMemo(
    () => (change.aText !== null && change.bText !== null ? diffWords(change.aText, change.bText) : null),
    [change.aText, change.bText],
  );
  const sig = SIG_STYLE[change.significance];

  return (
    <article className="rounded-card border border-line bg-surface p-4 shadow-card">
      <header className="flex flex-wrap items-center gap-2">
        <Badge tone={sig.tone} shape="tag">
          {change.significance}
        </Badge>
        <Badge shape="tag">{change.type}</Badge>
        <span className="text-xs text-ink-subtle">{change.category}</span>
        <span className="ml-auto flex items-center gap-0.5">
          <span className="mr-1.5 text-sm font-semibold tabular-nums text-ink">{change.clause}</span>
          <IconButton
            label="Open baseline"
            icon={FileMinus}
            disabled={change.aStart === null || change.aEnd === null}
            onClick={() => router.push(`/documents/${docAId}?ranges=${change.aStart}-${change.aEnd}`)}
          />
          <IconButton
            label="Open revised"
            icon={FilePlus}
            disabled={change.bStart === null || change.bEnd === null}
            onClick={() => router.push(`/documents/${docBId}?ranges=${change.bStart}-${change.bEnd}`)}
          />
          <IconButton
            label="Copy summary"
            icon={Copy}
            onClick={() => {
              void navigator.clipboard?.writeText(`${change.clause}: ${change.summary}`);
              toast("Summary copied", "success");
            }}
          />
        </span>
      </header>

      <p className="mt-2.5 flex flex-wrap items-center gap-2 text-sm font-medium text-ink">
        {change.summary}
        <Badge tone={change.summarySource === "ai" ? "accent" : "neutral"}>
          {change.summarySource === "ai" ? <Icon name="nodes" /> : <Cog />}
          {change.summarySource === "ai" ? "AI" : "automatic"}
        </Badge>
      </p>

      <div className="mt-3 grid gap-3 md:grid-cols-2">
        <Panel side="A" text={change.aText} page={change.aPage}>
          {parts?.filter((p) => p.type !== "ins").map((p, i) =>
            p.type === "del" ? (
              <del key={i} className="rounded-sm bg-danger/15 text-danger decoration-danger/60">
                {p.text}
              </del>
            ) : (
              <span key={i}>{p.text}</span>
            ),
          )}
        </Panel>
        <Panel side="B" text={change.bText} page={change.bPage}>
          {parts?.filter((p) => p.type !== "del").map((p, i) =>
            p.type === "ins" ? (
              <ins key={i} className="rounded-sm bg-ok/15 text-ok no-underline">
                {p.text}
              </ins>
            ) : (
              <span key={i}>{p.text}</span>
            ),
          )}
        </Panel>
      </div>
    </article>
  );
}

function Panel({
  side,
  text,
  page,
  children,
}: {
  side: "A" | "B";
  text: string | null;
  page: number | null;
  children?: ReactNode;
}) {
  const [open, setOpen] = useState(false);
  const long = (text?.length ?? 0) > 260;
  const a = side === "A";
  return (
    <section className={cn("rounded-lg p-3", a ? "bg-removed" : "bg-added")} aria-label={a ? "Baseline text" : "Revised text"}>
      <h4 className={cn("mb-1.5 flex items-center gap-2 text-xs font-semibold", a ? "text-danger" : "text-ok")}>
        {a ? "A · baseline" : "B · revised"}
        {page ? <span className="font-medium opacity-70">p.{page}</span> : null}
        {long ? (
          <button
            type="button"
            onClick={() => setOpen((o) => !o)}
            aria-label={open ? "Show less" : "Show more"}
            aria-expanded={open}
            className="ml-auto grid size-6 place-items-center rounded hover:bg-ink/5"
          >
            <ChevronsUpDown className="size-3.5" />
          </button>
        ) : null}
      </h4>
      {text === null ? (
        <p className="flex items-center gap-1.5 text-sm text-ink-subtle">
          <Minus className="size-4" aria-hidden /> Not in this version
        </p>
      ) : (
        <p className={cn("whitespace-pre-line text-sm leading-6 text-ink", long && !open && "line-clamp-4")}>
          {children ?? text}
        </p>
      )}
    </section>
  );
}
