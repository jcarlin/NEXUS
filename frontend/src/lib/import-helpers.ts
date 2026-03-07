/**
 * Helper functions for the ingest flow.
 */

import type { ProcessUploadedRequest } from "@/api/generated/schemas";

export interface UploadedFile {
  objectKey: string;
  filename: string;
}

export type ProcessUploadedPayload = ProcessUploadedRequest;

/**
 * Transform camelCase upload results to snake_case API payload.
 */
export function buildProcessUploadedPayload(
  files: UploadedFile[],
): ProcessUploadedPayload {
  return {
    files: files
      .filter((f) => f.objectKey)
      .map((f) => ({
        object_key: f.objectKey,
        filename: f.filename,
      })),
  };
}

/**
 * Calculate ingest progress as a percentage (0–100).
 */
export function calculateIngestProgress(job: {
  processed_documents: number;
  failed_documents: number;
  skipped_documents: number;
  total_documents: number;
}): number {
  if (job.total_documents <= 0) return 0;
  const processed =
    job.processed_documents + job.failed_documents + job.skipped_documents;
  return Math.round((processed / job.total_documents) * 100);
}
