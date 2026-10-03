import type { Metadata } from "next";
import { RedlineView } from "@/components/redline/redline-view";

export const metadata: Metadata = { title: "Redline" };

export default function RedlinePage() {
  return <RedlineView />;
}
