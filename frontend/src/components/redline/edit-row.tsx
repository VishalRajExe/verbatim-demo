"use client";

import { CircleAlert, Minus, SearchX, TriangleAlert } from "lucide-react";
import type { ReactNode } from "react";
import { Icon } from "@/components/icons";
import { Checkbox } from "@/components/ui/checkbox";
import { diffTokens } from "@/lib/diff";
import type { RedlineEdit } from "@/lib/types";
import { cn } from "@/lib/utils";

function Label({ children }: { children: ReactNode }) {
  return <p className="text-[11px] font-semibold uppercase tracking-[0.06em] text-ink-subtle">{children}</p>;
}

function CheckChip({ check }: { check: RedlineEdit["check"] }) {
  const base = "inline-flex items-center gap-1 rounded-md px-2 py-0.5 text-xs font-semibold [&_svg]:size-3.5";
  if (check === "verified") {
    return (
      <span className={cn(base, "bg-ok-soft/70 text-ok ring-1 ring-inset ring-ok/15")}>
        <Icon name="check" strokeWidth={2} /> Single occurrence verified
      </span>
    );
  }
  if (check === "ambiguous") {
    return (
      <span className={cn(base, "bg-warn-soft text-warn")}>
        <TriangleAlert /> Skipped: appears more than once
      </span>
    );
  }
  return (
    <span className={cn(base, "bg-danger-soft text-danger")}>
      <SearchX /> Not found in document
    </span>
  );
}

/** The change as it will look in Word: deletions struck in red, insertions underlined in green. */
export function TrackedPreview({ target, replacement }: { target: string; replacement: string }) {
  const parts = diffTokens(target, replacement);
  return (
    <p className="font-serif text-[17px] leading-8 text-ink" aria-label={`Change from ${target} to ${replacement}`}>
      {parts.map((p, i) => {
        const next = parts[i + 1];
        const prev = parts[i - 1];
        if (p.type === "del") {
          // A struck number butted against its replacement ("1001,000") is unreadable: leave a hair of air.
          return (
            <del key={i} className={cn("text-danger line-through decoration-danger/80 decoration-1", next?.type === "ins" && "mr-[0.22em]")}>
              {p.text}
            </del>
          );
        }
        if (p.type === "ins") {
          return (
            <ins
              key={i}
              className={cn("text-ok underline decoration-ok/80 decoration-1 underline-offset-4", prev?.type === "same" && "ml-[0.12em]")}
            >
              {p.text}
            </ins>
          );
        }
        return <span key={i}>{p.text}</span>;
      })}
    </p>
  );
}

/**
 * One proposed revision. The checkbox is only enabled for edits whose original text was found exactly once.
 * `readOnly` is the compact form used inside saved sessions.
 */
export function EditRow({
  edit,
  index,
  checked,
  onCheckedChange,
  readOnly = false,
  applied = false,
}: {
  edit: RedlineEdit;
  index: number;
  checked?: boolean;
  onCheckedChange?: (on: boolean) => void;
  readOnly?: boolean;
  applied?: boolean;
}) {
  const ok = edit.check === "verified";
  return (
    <li
      className={cn(
        "rounded-card border bg-surface shadow-card",
        readOnly ? "p-3.5" : "p-5",
        ok ? "border-line" : "border-warn/30",
      )}
    >
      <div className="flex gap-3.5">
        <div className="pt-0.5">
          {readOnly ? (
            applied ? (
              <Icon name="check" className="size-[18px] text-ok" strokeWidth={2} aria-label="Applied" role="img" aria-hidden={false} />
            ) : (
              <Minus className="size-[18px] text-ink-subtle" aria-label="Not applied" />
            )
          ) : (
            <Checkbox
              aria-label={`Include revision ${index}`}
              checked={checked}
              disabled={!ok}
              onCheckedChange={(c) => onCheckedChange?.(c === true)}
              className="data-[state=checked]:border-navy data-[state=checked]:bg-navy"
            />
          )}
        </div>

        <div className="min-w-0 flex-1">
          <div className="flex flex-wrap items-center gap-x-2.5 gap-y-1.5">
            <span className="text-sm font-semibold text-ink">Revision #{index}</span>
            <CheckChip check={edit.check} />
          </div>
          <p className="mt-1 text-sm text-ink-muted">{edit.reason}</p>

          <div className="mt-4">
            <Label>Tracked change preview</Label>
            <div className="mt-2 rounded-lg bg-paper px-4 py-2.5">
              <TrackedPreview target={edit.target} replacement={edit.replacement} />
            </div>
          </div>

          {readOnly ? null : (
            <div className="mt-3 grid gap-3 sm:grid-cols-2">
              <div className="rounded-lg border border-line px-3.5 py-3">
                <Label>Target text (original)</Label>
                <p className="mt-1.5 font-serif text-[15px] leading-6 text-ink line-through decoration-ink/60">{edit.target}</p>
              </div>
              <div className="rounded-lg border border-line px-3.5 py-3">
                <Label>Replacement text (revised)</Label>
                <p className="mt-1.5 font-serif text-[15px] leading-6 text-ink underline decoration-ok/70 underline-offset-4">
                  {edit.replacement}
                </p>
              </div>
            </div>
          )}

          {edit.note ? (
            <p className="mt-3 flex items-start gap-1.5 text-xs text-warn">
              <CircleAlert className="mt-0.5 size-3.5 shrink-0" aria-hidden /> {edit.note}
            </p>
          ) : null}
        </div>
      </div>
    </li>
  );
}
