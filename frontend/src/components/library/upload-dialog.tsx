"use client";

import { CircleCheck, CircleX, CloudUpload, LoaderCircle, X } from "lucide-react";
import { useRef, useState, type DragEvent } from "react";
import { mutate } from "swr";
import { FileIcon } from "@/components/common/file-icon";
import { Button } from "@/components/ui/button";
import { Dialog, DialogClose, DialogContent, DialogDescription, DialogTitle } from "@/components/ui/dialog";
import { IconButton } from "@/components/ui/icon-button";
import { Progress } from "@/components/ui/progress";
import { uploadDocument } from "@/lib/api/client";
import { ACCEPT, MAX_UPLOAD_MB, validateUploadFile } from "@/lib/upload";
import { cn, formatBytes } from "@/lib/utils";

interface Item {
  id: number;
  name: string;
  size: number;
  state: "uploading" | "added" | "rejected";
  progress: number;
  message: string | null;
}

export function UploadDialog({ open, onOpenChange }: { open: boolean; onOpenChange: (o: boolean) => void }) {
  const [items, setItems] = useState<Item[]>([]);
  const [dragging, setDragging] = useState(false);
  const input = useRef<HTMLInputElement>(null);
  const seq = useRef(0);

  const patch = (id: number, p: Partial<Item>) => setItems((prev) => prev.map((i) => (i.id === id ? { ...i, ...p } : i)));

  function addFiles(files: FileList | File[]) {
    for (const file of Array.from(files)) {
      const id = ++seq.current;
      const problem = validateUploadFile(file);
      if (problem) {
        setItems((prev) => [{ id, name: file.name, size: file.size, state: "rejected", progress: 0, message: problem }, ...prev]);
        continue;
      }
      setItems((prev) => [{ id, name: file.name, size: file.size, state: "uploading", progress: 0, message: null }, ...prev]);
      uploadDocument(file, (pct) => patch(id, { progress: pct }))
        .then(() => {
          patch(id, { state: "added", progress: 100 });
          void mutate("documents");
        })
        .catch(() => patch(id, { state: "rejected", message: "Upload failed. Check your connection and try again." }));
    }
  }

  function onDrop(e: DragEvent<HTMLDivElement>) {
    e.preventDefault();
    setDragging(false);
    if (e.dataTransfer.files.length) addFiles(e.dataTransfer.files);
  }

  const busy = items.some((i) => i.state === "uploading");

  return (
    <Dialog
      open={open}
      onOpenChange={(o) => {
        onOpenChange(o);
        if (!o) setItems([]);
      }}
    >
      <DialogContent className="max-w-lg">
        <DialogTitle className="text-base font-semibold">Upload documents</DialogTitle>
        <DialogDescription className="sr-only">Choose PDF or DOCX files to add to your library.</DialogDescription>

        <div
          onDragOver={(e) => {
            e.preventDefault();
            setDragging(true);
          }}
          onDragLeave={() => setDragging(false)}
          onDrop={onDrop}
          className={cn(
            "mt-4 flex flex-col items-center rounded-card border-2 border-dashed px-6 py-8 text-center transition-colors",
            dragging ? "border-brand bg-brand-soft" : "border-line-strong bg-canvas",
          )}
        >
          <span className="grid size-12 place-items-center rounded-full bg-brand-soft text-brand">
            <CloudUpload className="size-6" />
          </span>
          <p className="mt-3 text-sm font-medium text-ink">Drop files here</p>
          <p className="mt-0.5 text-xs text-ink-subtle">PDF or DOCX · up to {MAX_UPLOAD_MB} MB</p>
          <Button className="mt-4" variant="primary" onClick={() => input.current?.click()}>
            Browse files
          </Button>
          <input
            ref={input}
            type="file"
            multiple
            accept={ACCEPT}
            className="sr-only"
            aria-label="Choose files"
            onChange={(e) => {
              if (e.target.files) addFiles(e.target.files);
              e.target.value = "";
            }}
          />
        </div>

        {items.length > 0 ? (
          <ul className="mt-4 max-h-60 space-y-2 overflow-y-auto" aria-live="polite">
            {items.map((i) => (
              <li key={i.id} className="flex items-center gap-3 rounded-lg border border-line bg-surface p-2.5">
                <FileIcon kind={/\.docx$/i.test(i.name) ? "docx" : "pdf"} className="size-8" />
                <div className="min-w-0 flex-1">
                  <p className="truncate text-sm font-medium text-ink">{i.name}</p>
                  {i.state === "uploading" ? (
                    <Progress value={i.progress} className="mt-1.5" label={`Uploading ${i.name}`} />
                  ) : i.state === "rejected" ? (
                    <p className="mt-0.5 text-xs text-danger">{i.message}</p>
                  ) : (
                    <p className="mt-0.5 text-xs text-ok">Added. Processing now.</p>
                  )}
                </div>
                <span className="text-xs text-ink-subtle">{formatBytes(i.size)}</span>
                {i.state === "uploading" ? (
                  <LoaderCircle className="size-4 animate-spin text-brand" aria-label="Uploading" />
                ) : i.state === "added" ? (
                  <CircleCheck className="size-4 text-ok" aria-label="Added" />
                ) : (
                  <>
                    <CircleX className="size-4 text-danger" aria-label="Rejected" />
                    <IconButton
                      label="Remove"
                      icon={X}
                      size="icon"
                      onClick={() => setItems((prev) => prev.filter((x) => x.id !== i.id))}
                    />
                  </>
                )}
              </li>
            ))}
          </ul>
        ) : null}

        <div className="mt-5 flex justify-end">
          <DialogClose asChild>
            <Button variant={items.some((i) => i.state === "added") ? "primary" : "outline"} disabled={busy}>
              {items.some((i) => i.state === "added") ? "Done" : "Close"}
            </Button>
          </DialogClose>
        </div>
      </DialogContent>
    </Dialog>
  );
}
