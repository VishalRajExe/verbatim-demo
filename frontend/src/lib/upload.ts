import { z } from "zod";

export const MAX_UPLOAD_MB = 25;
export const ACCEPT =
  ".pdf,.docx,application/pdf,application/vnd.openxmlformats-officedocument.wordprocessingml.document";

const UploadFileSchema = z.object({
  name: z.string().regex(/\.(pdf|docx)$/i, "Only PDF and DOCX files are supported."),
  size: z
    .number()
    .min(1, "This file is empty.")
    .max(MAX_UPLOAD_MB * 1024 * 1024, `File is larger than ${MAX_UPLOAD_MB} MB.`),
});

/** Client-side pre-check only. The server repeats this check with magic bytes. */
export function validateUploadFile(file: { name: string; size: number }): string | null {
  const result = UploadFileSchema.safeParse(file);
  if (result.success) return null;
  return result.error.issues[0]?.message ?? "This file can't be uploaded.";
}
