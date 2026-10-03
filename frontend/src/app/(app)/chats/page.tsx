import type { Metadata } from "next";
import { Suspense } from "react";
import { ChatWorkspace } from "@/components/chat/chat-workspace";
import { Skeleton } from "@/components/ui/skeleton";

export const metadata: Metadata = { title: "Ask & chats" };

export default function ChatsPage() {
  return (
    <Suspense
      fallback={
        <div className="flex h-full">
          <Skeleton className="hidden w-64 rounded-none lg:block" />
          <div className="flex-1 space-y-3 p-6">
            <Skeleton className="h-8 w-2/3" />
            <Skeleton className="h-4 w-1/2" />
          </div>
        </div>
      }
    >
      <ChatWorkspace />
    </Suspense>
  );
}
