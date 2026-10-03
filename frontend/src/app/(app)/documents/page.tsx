import type { Metadata } from "next";
import { DocumentsView } from "@/components/library/documents-view";

export const metadata: Metadata = { title: "Documents" };

export default function DocumentsPage() {
  return <DocumentsView />;
}
