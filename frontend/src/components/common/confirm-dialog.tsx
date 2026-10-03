"use client";

import { LoaderCircle, Trash2 } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Dialog, DialogClose, DialogContent, DialogDescription, DialogTitle } from "@/components/ui/dialog";

export function ConfirmDialog({
  open,
  onOpenChange,
  title,
  description,
  confirmLabel = "Delete",
  busy = false,
  onConfirm,
}: {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  title: string;
  description?: string;
  confirmLabel?: string;
  busy?: boolean;
  onConfirm: () => void;
}) {
  return (
    <Dialog open={open} onOpenChange={(o) => (busy ? undefined : onOpenChange(o))}>
      <DialogContent>
        <div className="flex gap-3">
          <span className="grid size-10 shrink-0 place-items-center rounded-full bg-danger-soft text-danger">
            <Trash2 className="size-5" />
          </span>
          <div className="min-w-0 pr-6">
            <DialogTitle className="text-base font-semibold text-ink">{title}</DialogTitle>
            {description ? (
              <DialogDescription className="mt-1 text-sm text-ink-subtle">{description}</DialogDescription>
            ) : null}
          </div>
        </div>
        <div className="mt-5 flex justify-end gap-2">
          <DialogClose asChild>
            <Button disabled={busy}>Cancel</Button>
          </DialogClose>
          <Button variant="dangerSolid" onClick={onConfirm} disabled={busy}>
            {busy ? <LoaderCircle className="animate-spin" /> : <Trash2 />}
            {confirmLabel}
          </Button>
        </div>
      </DialogContent>
    </Dialog>
  );
}
