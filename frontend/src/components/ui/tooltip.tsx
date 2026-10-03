"use client";

import * as T from "@radix-ui/react-tooltip";
import type { ReactNode } from "react";

export function TooltipProvider({ children }: { children: ReactNode }) {
  return (
    <T.Provider delayDuration={250} skipDelayDuration={100}>
      {children}
    </T.Provider>
  );
}

export function Tip({
  label,
  children,
  side = "top",
}: {
  label: string;
  children: ReactNode;
  side?: "top" | "bottom" | "left" | "right";
}) {
  return (
    <T.Root>
      <T.Trigger asChild>{children}</T.Trigger>
      <T.Portal>
        <T.Content
          side={side}
          sideOffset={6}
          className="z-[90] max-w-xs animate-pop-in whitespace-pre-line rounded-md bg-ink px-2 py-1 text-xs font-medium text-white shadow-md"
        >
          {label}
          <T.Arrow className="fill-ink" />
        </T.Content>
      </T.Portal>
    </T.Root>
  );
}
