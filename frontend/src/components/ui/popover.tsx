"use client";

import * as P from "@radix-ui/react-popover";
import type { ComponentProps } from "react";
import { cn } from "@/lib/utils";

export const Popover = P.Root;
export const PopoverTrigger = P.Trigger;
export const PopoverAnchor = P.Anchor;

export function PopoverContent({ className, align = "start", sideOffset = 8, ...props }: ComponentProps<typeof P.Content>) {
  return (
    <P.Portal>
      <P.Content
        align={align}
        sideOffset={sideOffset}
        collisionPadding={12}
        className={cn(
          "z-50 w-[min(26rem,calc(100vw-1.5rem))] origin-(--radix-popover-content-transform-origin) rounded-card border border-line bg-surface p-0 shadow-[0_12px_32px_rgb(15_23_42/0.14)] outline-none data-[state=open]:animate-pop-in",
          className,
        )}
        {...props}
      />
    </P.Portal>
  );
}
