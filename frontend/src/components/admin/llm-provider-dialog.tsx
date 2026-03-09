import { useEffect } from "react";
import { useForm } from "react-hook-form";
import { z } from "zod";
import { zodResolver } from "@hookform/resolvers/zod";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { apiClient } from "@/api/client";
import { useNotifications } from "@/hooks/use-notifications";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
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

const providerSchema = z.object({
  provider: z.enum(["anthropic", "openai", "gemini", "ollama"]),
  label: z.string().min(1, "Label is required"),
  api_key: z.string().optional(),
  base_url: z.string().optional(),
});

type ProviderFormData = z.infer<typeof providerSchema>;

interface LLMProvider {
  id: string;
  provider: "anthropic" | "openai" | "gemini" | "ollama";
  label: string;
  api_key_set: boolean;
  base_url: string;
  is_active: boolean;
  created_at: string;
  updated_at: string;
}

interface LLMProviderDialogProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  provider: LLMProvider | null;
}

export function LLMProviderDialog({ open, onOpenChange, provider }: LLMProviderDialogProps) {
  const queryClient = useQueryClient();
  const notify = useNotifications();
  const isEdit = provider !== null;

  const {
    register,
    handleSubmit,
    setValue,
    watch,
    reset,
    formState: { errors },
  } = useForm<ProviderFormData>({
    resolver: zodResolver(providerSchema),
    defaultValues: {
      provider: "anthropic",
      label: "",
      api_key: "",
      base_url: "",
    },
  });

  const providerType = watch("provider");
  const showBaseUrl = providerType === "ollama" || providerType === "openai";

  useEffect(() => {
    if (open && provider) {
      reset({
        provider: provider.provider,
        label: provider.label,
        api_key: "",
        base_url: provider.base_url || "",
      });
    } else if (open) {
      reset({
        provider: "anthropic",
        label: "",
        api_key: "",
        base_url: "",
      });
    }
  }, [open, provider, reset]);

  const createMutation = useMutation({
    mutationFn: (data: ProviderFormData) =>
      apiClient<LLMProvider>({
        url: "/api/v1/admin/llm-config/providers",
        method: "POST",
        data,
      }),
    onSuccess: () => {
      notify.success("Provider created");
      queryClient.invalidateQueries({ queryKey: ["llm-config"] });
      onOpenChange(false);
    },
    onError: (err) => {
      notify.error(err instanceof Error ? err.message : "Failed to create provider");
    },
  });

  const updateMutation = useMutation({
    mutationFn: (data: ProviderFormData) =>
      apiClient<LLMProvider>({
        url: `/api/v1/admin/llm-config/providers/${provider!.id}`,
        method: "PATCH",
        data,
      }),
    onSuccess: () => {
      notify.success("Provider updated");
      queryClient.invalidateQueries({ queryKey: ["llm-config"] });
      onOpenChange(false);
    },
    onError: (err) => {
      notify.error(err instanceof Error ? err.message : "Failed to update provider");
    },
  });

  const isPending = createMutation.isPending || updateMutation.isPending;
  const mutationError = createMutation.error || updateMutation.error;

  function onSubmit(data: ProviderFormData) {
    // Strip empty optional fields
    const payload = { ...data };
    if (!payload.api_key) delete payload.api_key;
    if (!payload.base_url) delete payload.base_url;

    if (isEdit) {
      updateMutation.mutate(payload);
    } else {
      createMutation.mutate(payload);
    }
  }

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="sm:max-w-md">
        <DialogHeader>
          <DialogTitle>{isEdit ? "Edit Provider" : "Add Provider"}</DialogTitle>
          <DialogDescription>
            {isEdit
              ? "Update the provider configuration."
              : "Configure a new LLM API provider."}
          </DialogDescription>
        </DialogHeader>
        <form onSubmit={handleSubmit(onSubmit)} className="space-y-4">
          <div className="space-y-2">
            <Label>Provider Type</Label>
            <Select
              value={providerType}
              onValueChange={(v) => setValue("provider", v as ProviderFormData["provider"])}
              disabled={isEdit}
            >
              <SelectTrigger>
                <SelectValue placeholder="Select provider type" />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value="anthropic">Anthropic</SelectItem>
                <SelectItem value="openai">OpenAI</SelectItem>
                <SelectItem value="gemini">Gemini</SelectItem>
                <SelectItem value="ollama">Ollama</SelectItem>
              </SelectContent>
            </Select>
            {errors.provider && (
              <p className="text-xs text-destructive">{errors.provider.message}</p>
            )}
          </div>

          <div className="space-y-2">
            <Label htmlFor="label">Label</Label>
            <Input
              id="label"
              {...register("label")}
              placeholder="e.g. Production Anthropic"
            />
            {errors.label && (
              <p className="text-xs text-destructive">{errors.label.message}</p>
            )}
          </div>

          <div className="space-y-2">
            <Label htmlFor="api_key">
              API Key
              {isEdit && (
                <span className="ml-2 text-xs text-muted-foreground">
                  (leave blank to keep current)
                </span>
              )}
            </Label>
            <Input
              id="api_key"
              type="password"
              {...register("api_key")}
              placeholder={isEdit ? "********" : "sk-..."}
            />
          </div>

          {showBaseUrl && (
            <div className="space-y-2">
              <Label htmlFor="base_url">Base URL</Label>
              <Input
                id="base_url"
                {...register("base_url")}
                placeholder={providerType === "ollama" ? "http://localhost:11434" : "https://api.openai.com/v1"}
              />
            </div>
          )}

          {mutationError && (
            <p className="text-xs text-destructive">
              {mutationError instanceof Error ? mutationError.message : "An error occurred"}
            </p>
          )}

          <DialogFooter>
            <Button type="button" variant="outline" onClick={() => onOpenChange(false)}>
              Cancel
            </Button>
            <Button type="submit" disabled={isPending}>
              {isPending
                ? isEdit
                  ? "Saving..."
                  : "Creating..."
                : isEdit
                  ? "Save Changes"
                  : "Add Provider"}
            </Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  );
}
