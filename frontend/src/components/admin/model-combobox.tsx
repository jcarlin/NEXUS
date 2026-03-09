import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { Check, ChevronsUpDown, Loader2, AlertTriangle } from "lucide-react";
import { apiClient } from "@/api/client";
import { cn } from "@/lib/utils";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import {
  Command,
  CommandEmpty,
  CommandGroup,
  CommandInput,
  CommandItem,
  CommandList,
  CommandSeparator,
} from "@/components/ui/command";
import {
  Popover,
  PopoverContent,
  PopoverTrigger,
} from "@/components/ui/popover";

interface AvailableModel {
  id: string;
  display_name: string;
  context_window: number | null;
}

interface AvailableModelListResponse {
  items: AvailableModel[];
  provider_type: string;
}

interface ModelComboboxProps {
  providerId: string | null;
  value: string;
  onChange: (value: string) => void;
}

export function ModelCombobox({ providerId, value, onChange }: ModelComboboxProps) {
  const [open, setOpen] = useState(false);
  const [customMode, setCustomMode] = useState(false);

  const {
    data,
    isLoading,
    isError,
  } = useQuery({
    queryKey: ["llm-config", "provider-models", providerId],
    queryFn: () =>
      apiClient<AvailableModelListResponse>({
        url: `/api/v1/admin/llm-config/providers/${providerId}/models`,
        method: "GET",
      }),
    enabled: !!providerId,
    staleTime: 5 * 60 * 1000,
    retry: 1,
  });

  const models = data?.items ?? [];

  // Fallback to plain text input when: no provider, error, or user chose custom mode
  if (!providerId || isError || customMode) {
    return (
      <div className="flex items-center gap-2">
        {isError && <AlertTriangle className="h-4 w-4 text-amber-500 shrink-0" />}
        <Input
          className="w-[240px]"
          placeholder="e.g. claude-sonnet-4-6-20260320"
          value={value}
          onChange={(e) => onChange(e.target.value)}
        />
        {customMode && (
          <Button
            variant="ghost"
            size="sm"
            className="text-xs whitespace-nowrap"
            onClick={() => setCustomMode(false)}
          >
            Browse models
          </Button>
        )}
      </div>
    );
  }

  const selectedModel = models.find((m) => m.id === value);

  return (
    <Popover open={open} onOpenChange={setOpen}>
      <PopoverTrigger asChild>
        <Button
          variant="outline"
          role="combobox"
          aria-expanded={open}
          className="w-[280px] justify-between font-normal"
        >
          {isLoading ? (
            <span className="flex items-center gap-2 text-muted-foreground">
              <Loader2 className="h-3 w-3 animate-spin" />
              Loading models...
            </span>
          ) : selectedModel ? (
            <span className="truncate">{selectedModel.display_name}</span>
          ) : value ? (
            <span className="truncate">{value}</span>
          ) : (
            <span className="text-muted-foreground">Select model...</span>
          )}
          <ChevronsUpDown className="ml-2 h-4 w-4 shrink-0 opacity-50" />
        </Button>
      </PopoverTrigger>
      <PopoverContent className="w-[280px] p-0" align="start">
        <Command>
          <CommandInput placeholder="Search models..." />
          <CommandList>
            <CommandEmpty>No models found.</CommandEmpty>
            <CommandGroup>
              {models.map((model) => (
                <CommandItem
                  key={model.id}
                  value={model.id}
                  onSelect={(v) => {
                    onChange(v);
                    setOpen(false);
                  }}
                >
                  <Check
                    className={cn(
                      "mr-2 h-4 w-4 shrink-0",
                      value === model.id ? "opacity-100" : "opacity-0",
                    )}
                  />
                  <div className="flex flex-col min-w-0">
                    <span className="truncate">{model.display_name}</span>
                    {model.context_window && (
                      <span className="text-xs text-muted-foreground">
                        {(model.context_window / 1000).toFixed(0)}k context
                      </span>
                    )}
                  </div>
                </CommandItem>
              ))}
            </CommandGroup>
            <CommandSeparator />
            <CommandGroup>
              <CommandItem
                onSelect={() => {
                  setCustomMode(true);
                  setOpen(false);
                }}
              >
                Use custom model...
              </CommandItem>
            </CommandGroup>
          </CommandList>
        </Command>
      </PopoverContent>
    </Popover>
  );
}
