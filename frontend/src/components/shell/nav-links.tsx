"use client";

import { FileText, GitCompareArrows, MessagesSquare, PenLine } from "lucide-react";
import Link from "next/link";
import { usePathname } from "next/navigation";
import { cn } from "@/lib/utils";

const NAV = [
  { href: "/documents", label: "Documents", icon: FileText },
  { href: "/chats", label: "Ask & chats", icon: MessagesSquare },
  { href: "/compare", label: "Compare", icon: GitCompareArrows },
  { href: "/redline", label: "Redline", icon: PenLine },
] as const;

export function NavLinks({ onNavigate }: { onNavigate?: () => void }) {
  const pathname = usePathname();
  return (
    <nav aria-label="Main" className="flex flex-col gap-1 p-3">
      {NAV.map(({ href, label, icon: Icon }) => {
        const active = pathname === href || pathname.startsWith(`${href}/`);
        return (
          <Link
            key={href}
            href={href}
            onClick={onNavigate}
            aria-current={active ? "page" : undefined}
            className={cn(
              "flex items-center gap-3 rounded-control px-3 py-2 text-sm transition-colors",
              active ? "bg-brand-soft font-semibold text-brand" : "font-medium text-ink-muted hover:bg-canvas hover:text-ink",
            )}
          >
            <Icon className="size-[18px]" aria-hidden />
            {label}
          </Link>
        );
      })}
    </nav>
  );
}
