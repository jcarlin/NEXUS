import { useState } from "react";
import { useMutation } from "@tanstack/react-query";
import { FileOutput } from "lucide-react";
import { apiClient } from "@/api/client";
import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
  DialogTrigger,
} from "@/components/ui/dialog";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { Label } from "@/components/ui/label";
import type { ProductionSet } from "@/routes/review/exports";

interface Props {
  productionSets: ProductionSet[];
  onCreated: () => void;
}

const EXPORT_TYPES = [
  { value: "court_ready", label: "Court Ready" },
  { value: "edrm_xml", label: "EDRM XML" },
  { value: "privilege_log", label: "Privilege Log" },
  { value: "result_set", label: "Result Set" },
];

const EXPORT_FORMATS = [
  { value: "zip", label: "ZIP" },
  { value: "csv", label: "CSV" },
  { value: "xlsx", label: "XLSX" },
];

export function CreateExportDialog({ productionSets, onCreated }: Props) {
  const [open, setOpen] = useState(false);
  const [exportType, setExportType] = useState("result_set");
  const [exportFormat, setExportFormat] = useState("zip");
  const [productionSetId, setProductionSetId] = useState<string>("");

  const mutation = useMutation({
    mutationFn: () =>
      apiClient<unknown>({
        url: "/api/v1/exports",
        method: "POST",
        data: {
          export_type: exportType,
          export_format: exportFormat,
          production_set_id: productionSetId || undefined,
        },
      }),
    onSuccess: () => {
      setOpen(false);
      setExportType("result_set");
      setExportFormat("zip");
      setProductionSetId("");
      onCreated();
    },
  });

  return (
    <Dialog open={open} onOpenChange={setOpen}>
      <DialogTrigger asChild>
        <Button size="sm">
          <FileOutput className="mr-1.5 h-3.5 w-3.5" />
          New Export
        </Button>
      </DialogTrigger>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>Create Export Job</DialogTitle>
        </DialogHeader>
        <form
          className="space-y-4"
          onSubmit={(e) => {
            e.preventDefault();
            mutation.mutate();
          }}
        >
          <div className="space-y-2">
            <Label>Export Type</Label>
            <Select value={exportType} onValueChange={setExportType}>
              <SelectTrigger>
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                {EXPORT_TYPES.map((t) => (
                  <SelectItem key={t.value} value={t.value}>
                    {t.label}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          </div>

          <div className="space-y-2">
            <Label>Format</Label>
            <Select value={exportFormat} onValueChange={setExportFormat}>
              <SelectTrigger>
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                {EXPORT_FORMATS.map((f) => (
                  <SelectItem key={f.value} value={f.value}>
                    {f.label}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          </div>

          {productionSets.length > 0 && (
            <div className="space-y-2">
              <Label>Production Set (optional)</Label>
              <Select value={productionSetId} onValueChange={setProductionSetId}>
                <SelectTrigger>
                  <SelectValue placeholder="All documents" />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value="">All documents</SelectItem>
                  {productionSets.map((ps) => (
                    <SelectItem key={ps.id} value={ps.id}>
                      {ps.name} ({ps.document_count} docs)
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>
          )}

          <div className="flex justify-end gap-2">
            <Button type="button" variant="ghost" onClick={() => setOpen(false)}>
              Cancel
            </Button>
            <Button type="submit" disabled={mutation.isPending}>
              {mutation.isPending ? "Creating..." : "Start Export"}
            </Button>
          </div>
          {mutation.isError && (
            <p className="text-sm text-destructive">
              {mutation.error.message}
            </p>
          )}
        </form>
      </DialogContent>
    </Dialog>
  );
}
