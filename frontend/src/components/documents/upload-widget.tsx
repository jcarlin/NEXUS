import { Dashboard } from "@uppy/react";
import { useUppy } from "@/hooks/use-uppy";
import { useAppStore } from "@/stores/app-store";
import "@uppy/core/dist/style.min.css";
import "@uppy/dashboard/dist/style.min.css";

interface UploadWidgetProps {
  datasetId?: string | null;
  onUploadComplete?: (results: { objectKey: string; filename: string }[]) => void;
}

export function UploadWidget({ datasetId, onUploadComplete }: UploadWidgetProps) {
  const matterId = useAppStore((s) => s.matterId);
  const uppy = useUppy({ matterId, datasetId, onUploadComplete });

  return (
    <Dashboard
      uppy={uppy}
      proudlyDisplayPoweredByUppy={false}
      theme="dark"
      height={350}
      note="PDF, DOCX, XLSX, PPTX, HTML, EML, MSG, RTF, CSV, TXT, ZIP, images. Max 500 MB."
    />
  );
}
