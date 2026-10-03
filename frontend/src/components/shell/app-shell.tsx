"use client";

import { Menu } from "lucide-react";
import { useState, type ReactNode } from "react";
import { IconButton } from "@/components/ui/icon-button";
import { Dialog, DialogTitle, SheetContent } from "@/components/ui/dialog";
import { Brand, BrandMark } from "./brand";
import { NavLinks } from "./nav-links";

export function AppShell({ children }: { children: ReactNode }) {
  const [navOpen, setNavOpen] = useState(false);
  return (
    <div className="flex h-dvh bg-canvas text-ink">
      <aside className="hidden w-60 shrink-0 flex-col border-r border-line bg-surface lg:flex">
        <div className="px-4 py-4">
          <Brand />
        </div>
        <NavLinks />
      </aside>

      <div className="flex min-w-0 flex-1 flex-col">
        <header className="flex h-12 shrink-0 items-center gap-2 border-b border-line bg-surface px-3 lg:hidden">
          <IconButton label="Open menu" icon={Menu} onClick={() => setNavOpen(true)} />
          <BrandMark className="size-6" />
          <span className="text-sm font-semibold">Verbatim</span>
        </header>
        <main className="relative min-h-0 flex-1">{children}</main>
      </div>

      <Dialog open={navOpen} onOpenChange={setNavOpen}>
        <SheetContent side="left" aria-describedby={undefined}>
          <DialogTitle className="sr-only">Navigation</DialogTitle>
          <div className="px-4 py-4">
            <Brand />
          </div>
          <NavLinks onNavigate={() => setNavOpen(false)} />
        </SheetContent>
      </Dialog>
    </div>
  );
}
