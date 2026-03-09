import { useEffect, useMemo } from "react";
import Uppy, { type Meta, type Body, type UploadResult } from "@uppy/core";
import XHRUpload from "@uppy/xhr-upload";
import { apiClient } from "@/api/client";
import { useAuthStore } from "@/stores/auth-store";
import { useAppStore } from "@/stores/app-store";

interface UseUppyOptions {
  matterId: string | null;
  datasetId?: string | null;
  onUploadComplete?: (results: { objectKey: string; filename: string }[]) => void;
}

export function useUppy({ matterId, datasetId, onUploadComplete }: UseUppyOptions) {
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

    const API_BASE = import.meta.env.VITE_API_BASE_URL || "";

    instance.use(XHRUpload, {
      endpoint: `${API_BASE}/api/v1/ingest/upload`,
      fieldName: "file",
      headers: () => {
        const headers: Record<string, string> = {};
        const token = useAuthStore.getState().accessToken;
        const matterId = useAppStore.getState().matterId;
        if (token) headers["Authorization"] = `Bearer ${token}`;
        if (matterId) headers["X-Matter-ID"] = matterId;
        return headers;
      },
    });

    return instance;
  }, [matterId]);

  useEffect(() => {
    const handler = async (result: UploadResult<Meta, Body>) => {
      if (!result.successful?.length) return;

      const files = result.successful.map((f) => {
        const body = (f.response?.body ?? {}) as Record<string, string>;
        return {
          object_key: body.object_key ?? "",
          filename: body.filename ?? f.name ?? "unknown",
        };
      }).filter((f) => f.object_key);

      if (files.length > 0) {
        const params: Record<string, string> = {};
        if (datasetId) params["dataset_id"] = datasetId;

        await apiClient({
          url: "/api/v1/ingest/process-uploaded",
          method: "POST",
          data: { files },
          params,
        });
      }

      onUploadComplete?.(
        result.successful.map((f) => {
          const body = (f.response?.body ?? {}) as Record<string, string>;
          return {
            objectKey: body.object_key ?? f.name ?? "unknown",
            filename: body.filename ?? f.name ?? "unknown",
          };
        }),
      );
    };

    uppy.on("complete", handler);
    return () => {
      uppy.off("complete", handler);
    };
  }, [uppy, matterId, datasetId, onUploadComplete]);

  useEffect(() => {
    return () => {
      uppy.clear();
    };
  }, [uppy]);

  return uppy;
}
