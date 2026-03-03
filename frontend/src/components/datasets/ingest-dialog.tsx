import { useState } from "react";
import { useForm } from "react-hook-form";
import { zodResolver } from "@hookform/resolvers/zod";
import { z } from "zod";
import { useMutation } from "@tanstack/react-query";
import { toast } from "sonner";
import { apiClient } from "@/api/client";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Checkbox } from "@/components/ui/checkbox";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import type {
  AdapterType,
  DatasetIngestResponse,
  DryRunEstimate,
} from "@/types";

const ADAPTER_OPTIONS: { value: AdapterType; label: string }[] = [
  { value: "directory", label: "Directory" },
  { value: "huggingface_csv", label: "HuggingFace CSV" },
  { value: "edrm_xml", label: "EDRM XML" },
  { value: "concordance_dat", label: "Concordance DAT" },
];

const NEEDS_CONTENT_DIR: AdapterType[] = ["edrm_xml", "concordance_dat"];

const ingestSchema = z.object({
  adapter_type: z.enum([
    "directory",
    "huggingface_csv",
    "edrm_xml",
    "concordance_dat",
  ]),
  source_path: z.string().min(1, "Source path is required"),
  content_dir: z.string().optional(),
  resume: z.boolean().default(false),
  limit: z.number().int().positive().optional(),
  disable_hnsw: z.boolean().default(false),
});

type IngestFormValues = z.infer<typeof ingestSchema>;

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
  const [dryRunResult, setDryRunResult] = useState<DryRunEstimate | null>(null);

  const {
    register,
    handleSubmit,
    watch,
    setValue,
    reset,
    formState: { errors },
  } = useForm<IngestFormValues>({
    resolver: zodResolver(ingestSchema),
    defaultValues: {
      adapter_type: "directory",
      source_path: "",
      content_dir: "",
      resume: false,
      disable_hnsw: false,
    },
  });

  const adapterType = watch("adapter_type");
  const showContentDir = NEEDS_CONTENT_DIR.includes(adapterType);

  const ingestMutation = useMutation({
    mutationFn: (data: IngestFormValues) =>
      apiClient<DatasetIngestResponse>({
        url: `/api/v1/datasets/${datasetId}/ingest`,
        method: "POST",
        data: {
          ...data,
          content_dir: showContentDir ? data.content_dir || null : null,
          limit: data.limit || null,
        },
      }),
    onSuccess: (result) => {
      toast.success(
        `Import started: ${result.total_documents} documents queued`,
      );
      onOpenChange(false);
      reset();
      setDryRunResult(null);
      onStarted?.();
    },
    onError: (error: Error) => {
      toast.error(error.message);
    },
  });

  const dryRunMutation = useMutation({
    mutationFn: (data: IngestFormValues) =>
      apiClient<DryRunEstimate>({
        url: `/api/v1/datasets/${datasetId}/ingest/dry-run`,
        method: "POST",
        data: {
          ...data,
          content_dir: showContentDir ? data.content_dir || null : null,
          limit: data.limit || null,
        },
      }),
    onSuccess: (result) => {
      setDryRunResult(result);
    },
    onError: (error: Error) => {
      toast.error(error.message);
    },
  });

  function handleClose(isOpen: boolean) {
    if (!isOpen) {
      reset();
      setDryRunResult(null);
    }
    onOpenChange(isOpen);
  }

  return (
    <Dialog open={open} onOpenChange={handleClose}>
      <DialogContent className="sm:max-w-lg">
        <DialogHeader>
          <DialogTitle>Import Documents</DialogTitle>
          <DialogDescription>
            Import documents from a server-side source into this dataset.
          </DialogDescription>
        </DialogHeader>

        <form
          className="space-y-4 py-2"
          onSubmit={handleSubmit((data) => ingestMutation.mutate(data))}
        >
          <div className="space-y-2">
            <Label htmlFor="adapter-type">Source Type</Label>
            <Select
              value={adapterType}
              onValueChange={(v) =>
                setValue("adapter_type", v as AdapterType, {
                  shouldValidate: true,
                })
              }
            >
              <SelectTrigger id="adapter-type">
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                {ADAPTER_OPTIONS.map((opt) => (
                  <SelectItem key={opt.value} value={opt.value}>
                    {opt.label}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          </div>

          <div className="space-y-2">
            <Label htmlFor="source-path">
              {adapterType === "directory"
                ? "Directory Path"
                : "File Path"}
            </Label>
            <Input
              id="source-path"
              placeholder={
                adapterType === "directory"
                  ? "/data/documents/"
                  : "/data/dataset.parquet"
              }
              {...register("source_path")}
            />
            {errors.source_path && (
              <p className="text-xs text-destructive">
                {errors.source_path.message}
              </p>
            )}
          </div>

          {showContentDir && (
            <div className="space-y-2">
              <Label htmlFor="content-dir">Content Directory</Label>
              <Input
                id="content-dir"
                placeholder="/data/referenced-files/"
                {...register("content_dir")}
              />
              <p className="text-xs text-muted-foreground">
                Directory containing files referenced by the load file
              </p>
            </div>
          )}

          <div className="space-y-2">
            <Label htmlFor="limit">Limit (optional)</Label>
            <Input
              id="limit"
              type="number"
              min={1}
              placeholder="Import all"
              {...register("limit", { valueAsNumber: true })}
            />
          </div>

          <div className="flex flex-col gap-3">
            <div className="flex items-center gap-2">
              <Checkbox
                id="resume"
                checked={watch("resume")}
                onCheckedChange={(checked) =>
                  setValue("resume", !!checked)
                }
              />
              <Label htmlFor="resume" className="text-sm font-normal">
                Resume (skip duplicates)
              </Label>
            </div>
            <div className="flex items-center gap-2">
              <Checkbox
                id="disable-hnsw"
                checked={watch("disable_hnsw")}
                onCheckedChange={(checked) =>
                  setValue("disable_hnsw", !!checked)
                }
              />
              <Label htmlFor="disable-hnsw" className="text-sm font-normal">
                Disable HNSW (faster bulk insert)
              </Label>
            </div>
          </div>

          {dryRunResult && (
            <div className="rounded-md border bg-muted/50 p-3 text-sm">
              <p className="mb-1 font-medium">Dry Run Estimate</p>
              <div className="grid grid-cols-2 gap-x-4 gap-y-1 text-xs">
                <span className="text-muted-foreground">Documents:</span>
                <span>{dryRunResult.total_documents.toLocaleString()}</span>
                <span className="text-muted-foreground">Characters:</span>
                <span>{dryRunResult.total_characters.toLocaleString()}</span>
                <span className="text-muted-foreground">Est. chunks:</span>
                <span>{dryRunResult.estimated_chunks.toLocaleString()}</span>
                <span className="text-muted-foreground">Est. tokens:</span>
                <span>{dryRunResult.estimated_tokens.toLocaleString()}</span>
                <span className="text-muted-foreground">Est. cost:</span>
                <span>${dryRunResult.estimated_cost_usd.toFixed(2)}</span>
              </div>
            </div>
          )}

          <DialogFooter className="gap-2">
            <Button
              type="button"
              variant="outline"
              disabled={dryRunMutation.isPending}
              onClick={handleSubmit((data) => dryRunMutation.mutate(data))}
            >
              {dryRunMutation.isPending ? "Scanning..." : "Dry Run"}
            </Button>
            <Button
              type="submit"
              disabled={ingestMutation.isPending}
            >
              {ingestMutation.isPending ? "Starting..." : "Start Import"}
            </Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  );
}
