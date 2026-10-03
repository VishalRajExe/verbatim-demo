import type { Metadata } from "next";
import { Suspense } from "react";
import { DocumentViewer, ViewerSkeleton } from "@/components/viewer/document-viewer";

export const metadata: Metadata = { title: "Document" };

export default function DocumentPage() {
  return (
    <Suspense fallback={<ViewerSkeleton />}>
      <DocumentViewer />
    </Suspense>
  );
}
