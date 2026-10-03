import { cn } from "@/lib/utils";

/**
 * Truncates the middle of a long filename, keeping the start and the last few characters.
 * Contracts are often named "Master Services Agreement 12 - Vendor 12.pdf": cutting the end hides what differs.
 */
export function MiddleTruncate({ text, tail = 14, className }: { text: string; tail?: number; className?: string }) {
  if (text.length <= tail + 6) return <span className={cn("truncate", className)}>{text}</span>;
  return (
    <span className={cn("flex min-w-0", className)} title={text}>
      <span className="truncate">{text.slice(0, -tail)}</span>
      <span className="shrink-0 whitespace-pre">{text.slice(-tail)}</span>
    </span>
  );
}
