"use client";

import * as D from "@radix-ui/react-dialog";
import { X } from "lucide-react";
import type { ComponentProps } from "react";
import { cn } from "@/lib/utils";

export const Dialog = D.Root;
export const DialogTrigger = D.Trigger;
export const DialogClose = D.Close;
export const DialogTitle = D.Title;
export const DialogDescription = D.Description;

const closeBtn =
  "absolute right-3 top-3 grid size-8 place-items-center rounded-md text-ink-subtle hover:bg-line/60 hover:text-ink";

export function DialogContent({
  className,
  children,
  ...props
}: ComponentProps<typeof D.Content>) {
  return (
    <D.Portal>
      <D.Overlay className="fixed inset-0 z-50 bg-ink/40 data-[state=open]:animate-fade-in" />
      <D.Content
        className={cn(
          "fixed left-1/2 top-1/2 z-50 w-[calc(100vw-2rem)] max-w-md -translate-x-1/2 -translate-y-1/2 rounded-card border border-line bg-surface p-5 shadow-xl data-[state=open]:animate-pop-in",
          className,
        )}
        {...props}
      >
        {children}
        <D.Close aria-label="Close" className={closeBtn}>
          <X className="size-4" />
        </D.Close>
      </D.Content>
    </D.Portal>
  );
}

/** Slide-over panel built on the same primitive. */
export function SheetContent({
  side = "right",
  className,
  children,
  ...props
}: ComponentProps<typeof D.Content> & { side?: "left" | "right" }) {
  return (
    <D.Portal>
      <D.Overlay className="fixed inset-0 z-50 bg-ink/35 data-[state=open]:animate-fade-in" />
      <D.Content
        className={cn(
          "fixed inset-y-0 z-50 flex w-full flex-col bg-surface shadow-sheet",
          side === "right"
            ? "right-0 max-w-[560px] border-l border-line data-[state=open]:animate-sheet-in"
            : "left-0 max-w-[280px] border-r border-line data-[state=open]:animate-fade-in",
          className,
        )}
        {...props}
      >
        {children}
      </D.Content>
    </D.Portal>
  );
}
