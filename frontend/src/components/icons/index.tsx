import type { SVGProps } from "react";
import { cn } from "@/lib/utils";
import { ICON_PATHS, type IconName } from "./paths";

export type { IconName };

/** Outline icon from the Verbatim set. Inherits colour from the text (currentColor). */
export function Icon({ name, className, ...props }: { name: IconName } & Omit<SVGProps<SVGSVGElement>, "name">) {
  return (
    <svg
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth={1.5}
      strokeLinecap="round"
      strokeLinejoin="round"
      aria-hidden
      className={cn("size-4 shrink-0", className)}
      {...props}
    >
      {ICON_PATHS[name].map((d) => (
        <path key={d} d={d} />
      ))}
    </svg>
  );
}
