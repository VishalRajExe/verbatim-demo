import { FileQuestion } from "lucide-react";
import Link from "next/link";
import { EmptyState } from "@/components/common/empty-state";
import { Button } from "@/components/ui/button";

export default function NotFound() {
  return (
    <div className="grid min-h-dvh place-items-center bg-canvas">
      <EmptyState
        icon={FileQuestion}
        title="Page not found"
        hint="The page may have moved, or the link is wrong."
        action={
          <Button asChild variant="primary">
            <Link href="/documents">Go to documents</Link>
          </Button>
        }
      />
    </div>
  );
}
