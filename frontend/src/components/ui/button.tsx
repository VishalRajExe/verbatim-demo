import { Slot } from "@radix-ui/react-slot";
import { cva, type VariantProps } from "class-variance-authority";
import type { ComponentProps } from "react";
import { cn } from "@/lib/utils";

export const buttonVariants = cva(
  "inline-flex shrink-0 items-center justify-center gap-2 whitespace-nowrap rounded-control text-sm font-semibold transition-colors disabled:pointer-events-none disabled:opacity-50 [&_svg]:size-4 [&_svg]:shrink-0",
  {
    variants: {
      variant: {
        primary: "bg-brand text-white hover:bg-brand-hover",
        outline: "border border-line-strong bg-surface text-ink hover:bg-canvas",
        ghost: "text-ink-muted hover:bg-line/60 hover:text-ink",
        danger: "border border-danger/25 bg-surface text-danger hover:bg-danger-soft/60",
        dangerSolid: "bg-danger text-white hover:bg-danger/90",
        soft: "bg-brand-soft text-brand hover:bg-brand-soft/70",
        accent: "bg-accent text-white hover:bg-accent/90",
        navy: "bg-navy text-white hover:bg-navy-hover",
      },
      size: {
        sm: "h-8 px-3",
        md: "h-9 px-4",
        lg: "h-10 px-5",
        icon: "size-8",
        iconMd: "size-9",
      },
    },
    defaultVariants: { variant: "outline", size: "md" },
  },
);

export type ButtonProps = ComponentProps<"button"> & VariantProps<typeof buttonVariants> & { asChild?: boolean };

export function Button({ className, variant, size, asChild = false, type, ...props }: ButtonProps) {
  const Comp = asChild ? Slot : "button";
  const extra = asChild ? {} : { type: type ?? "button" };
  return <Comp className={cn(buttonVariants({ variant, size }), className)} {...extra} {...props} />;
}
