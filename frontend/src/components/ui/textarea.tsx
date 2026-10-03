import type { ComponentProps } from "react";
import { cn } from "@/lib/utils";

export function Textarea({ className, ...props }: ComponentProps<"textarea">) {
  return (
    <textarea
      className={cn(
        "min-h-20 w-full resize-none rounded-control border border-line-strong bg-surface px-3 py-2.5 text-sm leading-6 text-ink placeholder:text-ink-subtle disabled:opacity-50",
        className,
      )}
      {...props}
    />
  );
}
