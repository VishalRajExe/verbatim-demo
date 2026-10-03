"use client";

import useSWR from "swr";
import { getChat, getComparison, getDocument, getDocumentPages, listChats, listComparisons, listDocuments, listRedlines } from "./client";
import { isWorking } from "@/lib/types";

export function useDocuments() {
  return useSWR("documents", listDocuments, {
    revalidateOnFocus: false,
    // Poll while any document is still processing so progress stays live.
    refreshInterval: (data) => (data?.some(isWorking) ? 1500 : 0),
  });
}

export function useDocument(id: string | null) {
  return useSWR(
    id ? `document:${id}` : null,
    () => getDocument(id as string),
    { revalidateOnFocus: false },
  );
}

export function useDocumentPages(id: string | null) {
  return useSWR(
    id ? `documentPages:${id}` : null,
    () => getDocumentPages(id as string),
    { revalidateOnFocus: false },
  );
}

export function useChats() {
  return useSWR("chats", listChats, { revalidateOnFocus: false });
}

export function useChat(id: string | null) {
  // Don't fetch the pending placeholder chat
  const key = id && id !== "__pending__" ? `chat:${id}` : null;
  return useSWR(key, () => getChat(id as string), { revalidateOnFocus: false });
}

export function useComparisons() {
  return useSWR("comparisons", listComparisons, { revalidateOnFocus: false });
}

export function useComparison(id: string | null) {
  return useSWR(
    id ? `comparison:${id}` : null,
    () => getComparison(id as string),
    { revalidateOnFocus: false },
  );
}

export function useRedlines() {
  return useSWR("redlines", listRedlines, { revalidateOnFocus: false });
}
