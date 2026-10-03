import type { ComponentProps } from "react";
import { cn } from "@/lib/utils";

export function FieldLabel({ className, ...props }: ComponentProps<"label">) {
  return (
    <label
      className={cn("mb-1.5 block text-[11px] font-semibold uppercase tracking-wide text-ink-subtle", className)}
      {...props}
    />
  );
}
