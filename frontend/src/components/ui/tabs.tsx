"use client";

import * as T from "@radix-ui/react-tabs";
import type { ComponentProps } from "react";
import { cn } from "@/lib/utils";

export const Tabs = T.Root;

export function TabsList({ className, ...props }: ComponentProps<typeof T.List>) {
  return <T.List className={cn("inline-flex rounded-lg border border-line bg-surface p-0.5", className)} {...props} />;
}

export function TabsTrigger({ className, ...props }: ComponentProps<typeof T.Trigger>) {
  return (
    <T.Trigger
      className={cn(
        "inline-flex items-center gap-1.5 rounded-md px-3 py-1.5 text-sm font-semibold text-ink-muted transition-colors hover:text-ink data-[state=active]:bg-accent data-[state=active]:text-white [&_svg]:size-4",
        className,
      )}
      {...props}
    />
  );
}

export const TabsContent = T.Content;
