import { useEffect } from "react";
import { useQuery } from "@tanstack/react-query";
import { useAppStore } from "@/stores/app-store";
import { apiClient } from "@/api/client";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import type { Matter } from "@/types";

export function MatterSelector() {
  const matterId = useAppStore((s) => s.matterId);
  const setMatter = useAppStore((s) => s.setMatter);

  const { data: matters } = useQuery({
    queryKey: ["matters"],
    queryFn: () =>
      apiClient<Matter[]>({ url: "/api/v1/auth/me/matters", method: "GET" }),
  });

  // Auto-select the first matter when none is selected
  useEffect(() => {
    if (!matterId && matters && matters.length > 0) {
      setMatter(matters[0]!.id);
    }
  }, [matterId, matters, setMatter]);

  return (
    <Select value={matterId ?? undefined} onValueChange={setMatter}>
      <SelectTrigger className="w-[220px]">
        <SelectValue placeholder="Select matter..." />
      </SelectTrigger>
      <SelectContent>
        {matters?.map((m) => (
          <SelectItem key={m.id} value={m.id}>
            {m.name}
          </SelectItem>
        ))}
      </SelectContent>
    </Select>
  );
}
