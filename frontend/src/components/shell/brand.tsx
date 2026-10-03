import { cn } from "@/lib/utils";

export function BrandMark({ className }: { className?: string }) {
  return (
    <svg viewBox="0 0 32 32" aria-hidden className={cn("size-8 shrink-0", className)}>
      <rect width="32" height="32" rx="8" className="fill-brand" />
      <path d="M11 8h7l4 4v11a1 1 0 0 1-1 1H11a1 1 0 0 1-1-1V9a1 1 0 0 1 1-1Z" fill="none" stroke="white" strokeWidth="1.6" strokeLinejoin="round" />
      <path d="m12.8 17.4 2.3 2.3 4.4-4.7" fill="none" stroke="white" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round" />
    </svg>
  );
}

export function Brand() {
  return (
    <div className="flex items-center gap-2.5">
      <BrandMark />
      <div className="leading-tight">
        <p className="text-sm font-semibold text-ink">Verbatim</p>
        <p className="text-xs text-ink-subtle">Contract intelligence</p>
      </div>
    </div>
  );
}
