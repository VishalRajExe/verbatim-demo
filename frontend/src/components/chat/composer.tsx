"use client";

import { Send, Square } from "lucide-react";
import { useEffect, useRef, type KeyboardEvent } from "react";
import { Button } from "@/components/ui/button";
import { Tip } from "@/components/ui/tooltip";

export function Composer({
  value,
  onChange,
  onSend,
  onStop,
  streaming,
  blockedReason,
  focusSignal,
}: {
  value: string;
  onChange: (v: string) => void;
  onSend: () => void;
  onStop: () => void;
  streaming: boolean;
  blockedReason: string | null;
  focusSignal: number;
}) {
  const ref = useRef<HTMLTextAreaElement>(null);

  useEffect(() => {
    if (focusSignal > 0) ref.current?.focus();
  }, [focusSignal]);

  function onKeyDown(e: KeyboardEvent<HTMLTextAreaElement>) {
    if (e.key === "Enter" && !e.shiftKey && !e.nativeEvent.isComposing) {
      e.preventDefault();
      if (!blockedReason && value.trim() && !streaming) onSend();
    }
  }

  return (
    <form
      onSubmit={(e) => {
        e.preventDefault();
        if (!blockedReason && value.trim() && !streaming) onSend();
      }}
      className="border-t border-line bg-surface p-3 sm:px-5 sm:py-4"
    >
      <div className="mx-auto flex max-w-3xl items-end gap-2">
        <textarea
          ref={ref}
          value={value}
          onChange={(e) => onChange(e.target.value)}
          onKeyDown={onKeyDown}
          rows={2}
          aria-label="Question"
          placeholder="Ask a question about the selected documents…"
          className="max-h-40 min-h-[64px] w-full resize-none rounded-control border border-line-strong bg-surface px-3 py-2.5 text-sm leading-6 text-ink placeholder:text-ink-subtle"
        />
        {streaming ? (
          <Button type="button" variant="danger" size="lg" onClick={onStop}>
            <Square className="fill-current" /> Stop
          </Button>
        ) : (
          <Tip label={blockedReason ?? "Send (Enter)"}>
            <span className="inline-flex">
              <Button type="submit" variant="primary" size="lg" disabled={Boolean(blockedReason) || !value.trim()}>
                <Send /> Ask
              </Button>
            </span>
          </Tip>
        )}
      </div>
    </form>
  );
}
