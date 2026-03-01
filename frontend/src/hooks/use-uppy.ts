import { useEffect, useMemo } from "react";
import Uppy, { type Meta, type Body, type UploadResult } from "@uppy/core";
import AwsS3 from "@uppy/aws-s3";
import { apiClient } from "@/api/client";

interface PresignedUploadResponse {
  upload_url: string;
  object_key: string;
  expires_in: number;
}

interface UseUppyOptions {
  matterId: string | null;
  onUploadComplete?: (results: { objectKey: string; filename: string }[]) => void;
}

export function useUppy({ matterId, onUploadComplete }: UseUppyOptions) {
  const uppy = useMemo(() => {
    const instance = new Uppy({
      restrictions: {
        maxFileSize: 500 * 1024 * 1024, // 500 MB
        allowedFileTypes: [
          ".pdf", ".docx", ".doc", ".xlsx", ".xls", ".pptx", ".ppt",
          ".html", ".htm", ".eml", ".msg", ".rtf", ".csv", ".txt", ".zip",
          ".png", ".jpg", ".jpeg", ".tiff", ".tif",
        ],
      },
      autoProceed: false,
    });

    instance.use(AwsS3, {
      shouldUseMultipart: false,
      async getUploadParameters(file) {
        const res = await apiClient<PresignedUploadResponse>({
          url: "/api/v1/ingest/presigned-upload",
          method: "POST",
          data: {
            filename: file.name ?? "unnamed",
            content_type: file.type || "application/octet-stream",
            matter_id: matterId,
          },
        });
        return {
          method: "PUT",
          url: res.upload_url,
          headers: { "Content-Type": file.type || "application/octet-stream" },
        };
      },
    });

    return instance;
  }, [matterId]);

  useEffect(() => {
    const handler = (result: UploadResult<Meta, Body>) => {
      if (result.successful && onUploadComplete) {
        onUploadComplete(
          result.successful.map((f) => ({
            objectKey: (f.meta?.["key"] as string) ?? f.name ?? "unknown",
            filename: f.name ?? "unknown",
          })),
        );
      }
    };

    uppy.on("complete", handler);
    return () => {
      uppy.off("complete", handler);
    };
  }, [uppy, onUploadComplete]);

  useEffect(() => {
    return () => {
      uppy.clear();
    };
  }, [uppy]);

  return uppy;
}
