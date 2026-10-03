import type { Metadata } from "next";
import { Suspense } from "react";
import { CompareView } from "@/components/compare/compare-view";
import { Skeleton } from "@/components/ui/skeleton";

export const metadata: Metadata = { title: "Compare" };

export default function ComparePage() {
  return (
    <Suspense
      fallback={
        <div className="mx-auto max-w-[980px] space-y-4 p-8">
          <Skeleton className="h-8 w-56" />
          <Skeleton className="h-40 w-full" />
        </div>
      }
    >
      <CompareView />
    </Suspense>
  );
}
