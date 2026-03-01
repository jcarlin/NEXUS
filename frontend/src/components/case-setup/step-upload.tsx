import { UploadWidget } from "@/components/documents/upload-widget";

interface StepUploadProps {
  onUploadComplete: (results: { objectKey: string; filename: string }[]) => void;
}

export function StepUpload({ onUploadComplete }: StepUploadProps) {
  return (
    <div className="space-y-4">
      <div>
        <h2 className="text-lg font-semibold">Upload Documents</h2>
        <p className="text-sm text-muted-foreground">
          Upload the documents for this case. They will be processed automatically.
        </p>
      </div>
      <UploadWidget onUploadComplete={onUploadComplete} />
    </div>
  );
}
