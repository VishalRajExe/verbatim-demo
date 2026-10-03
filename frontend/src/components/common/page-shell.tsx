import type { ReactNode } from "react";
import { cn } from "@/lib/utils";

/** Scrolling page body with the centred column used by Documents, Compare and Redline. */
export function PageShell({ children, className }: { children: ReactNode; className?: string }) {
  return (
    <div className="scroll-thin h-full overflow-y-auto">
      <div className={cn("mx-auto w-full max-w-[980px] px-4 py-6 sm:px-6 sm:py-8", className)}>{children}</div>
    </div>
  );
}
