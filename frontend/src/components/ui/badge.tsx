import { cva, type VariantProps } from "class-variance-authority";
import type { ComponentProps } from "react";
import { cn } from "@/lib/utils";

const badgeVariants = cva("inline-flex items-center gap-1 whitespace-nowrap text-xs font-semibold leading-5 [&_svg]:size-3", {
  variants: {
    tone: {
      neutral: "bg-line/70 text-ink-muted",
      ok: "bg-ok-soft text-ok",
      warn: "bg-warn-soft text-warn",
      danger: "bg-danger-soft text-danger",
      brand: "bg-brand-soft text-brand",
      accent: "bg-accent/10 text-accent",
    },
    shape: {
      pill: "rounded-full px-2.5 py-0.5",
      tag: "rounded-md px-2 py-0.5 text-[11px] uppercase tracking-wide",
    },
  },
  defaultVariants: { tone: "neutral", shape: "pill" },
});

export function Badge({
  className,
  tone,
  shape,
  ...props
}: ComponentProps<"span"> & VariantProps<typeof badgeVariants>) {
  return <span className={cn(badgeVariants({ tone, shape }), className)} {...props} />;
}
