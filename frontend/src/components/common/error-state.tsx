"use client";

import { RotateCcw, TriangleAlert } from "lucide-react";
import { Button } from "@/components/ui/button";
import { cn } from "@/lib/utils";

export function ErrorState({
  title = "Something went wrong",
  message,
  onRetry,
  className,
}: {
  title?: string;
  message?: string;
  onRetry?: () => void;
  className?: string;
}) {
  return (
    <div role="alert" className={cn("flex flex-col items-center px-6 py-12 text-center", className)}>
      <span className="grid size-12 place-items-center rounded-full bg-danger-soft text-danger">
        <TriangleAlert className="size-6" />
      </span>
      <h3 className="mt-3 text-base font-semibold text-ink">{title}</h3>
      {message ? <p className="mt-1 max-w-sm text-sm text-ink-subtle">{message}</p> : null}
      {onRetry ? (
        <Button className="mt-4" onClick={onRetry}>
          <RotateCcw /> Retry
        </Button>
      ) : null}
    </div>
  );
}
