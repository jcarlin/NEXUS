import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { IngestForm } from "./ingest-form";

interface IngestDialogProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  datasetId: string;
  onStarted?: () => void;
}

export function IngestDialog({
  open,
  onOpenChange,
  datasetId,
  onStarted,
}: IngestDialogProps) {
  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="sm:max-w-lg">
        <DialogHeader>
          <DialogTitle>Ingest Documents</DialogTitle>
          <DialogDescription>
            Ingest documents from a server-side source into this dataset.
          </DialogDescription>
        </DialogHeader>
        <IngestForm
          datasetId={datasetId}
          onStarted={() => {
            onOpenChange(false);
            onStarted?.();
          }}
        />
      </DialogContent>
    </Dialog>
  );
}
