import type { LucideIcon } from "lucide-react";
import type { ReactNode } from "react";
import { cn } from "@/lib/utils";

/** Stacked-pages illustration with a centred icon. Pure SVG, no assets. */
export function EmptyState({
  icon: Icon,
  title,
  hint,
  action,
  className,
}: {
  icon: LucideIcon;
  title: string;
  hint?: string;
  action?: ReactNode;
  className?: string;
}) {
  return (
    <div className={cn("flex flex-col items-center px-6 py-12 text-center", className)}>
      <div className="relative grid size-28 place-items-center">
        <svg viewBox="0 0 112 112" fill="none" aria-hidden className="absolute inset-0">
          <rect x="20" y="14" width="56" height="72" rx="8" transform="rotate(-8 48 50)" className="fill-surface stroke-line-strong" strokeWidth="1.5" />
          <rect x="36" y="22" width="56" height="72" rx="8" transform="rotate(6 64 58)" className="fill-surface stroke-line-strong" strokeWidth="1.5" />
          <path d="M48 42h28M48 52h20M48 62h24" transform="rotate(6 64 58)" className="stroke-line-strong" strokeWidth="2" strokeLinecap="round" />
        </svg>
        <span className="relative grid size-11 place-items-center rounded-full bg-brand-soft text-brand ring-4 ring-surface">
          <Icon className="size-5" />
        </span>
      </div>
      <h3 className="mt-3 text-base font-semibold text-ink">{title}</h3>
      {hint ? <p className="mt-1 max-w-sm text-sm text-ink-subtle">{hint}</p> : null}
      {action ? <div className="mt-4 flex flex-wrap items-center justify-center gap-2">{action}</div> : null}
    </div>
  );
}
