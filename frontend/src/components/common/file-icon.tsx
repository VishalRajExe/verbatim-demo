import { cn } from "@/lib/utils";

/** Small page glyph with a coloured file-type band. */
export function FileIcon({ kind, className }: { kind: "pdf" | "docx"; className?: string }) {
  const band = kind === "pdf" ? "fill-danger" : "fill-brand";
  return (
    <svg viewBox="0 0 32 32" aria-hidden className={cn("size-8 shrink-0", className)}>
      <path d="M8 3h11l6 6v18a2 2 0 0 1-2 2H8a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2Z" className="fill-surface stroke-line-strong" strokeWidth="1.2" />
      <path d="M19 3v4a2 2 0 0 0 2 2h4" fill="none" className="stroke-line-strong" strokeWidth="1.2" />
      <rect x="9" y="17" width="14" height="7" rx="1.5" className={band} />
      <text x="16" y="22.4" textAnchor="middle" fontSize="5.2" fontWeight="700" fill="white">
        {kind === "pdf" ? "PDF" : "DOC"}
      </text>
    </svg>
  );
}
