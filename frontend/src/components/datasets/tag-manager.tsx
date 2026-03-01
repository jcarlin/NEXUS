import { useState } from "react";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { X } from "lucide-react";
import { apiClient } from "@/api/client";
import { Badge } from "@/components/ui/badge";
import { Input } from "@/components/ui/input";
import type { TagResponse } from "@/types";

interface TagManagerProps {
  documentId: string;
  tags: string[];
}

export function TagManager({ documentId, tags }: TagManagerProps) {
  const queryClient = useQueryClient();
  const [input, setInput] = useState("");
  const [showSuggestions, setShowSuggestions] = useState(false);

  const { data: allTags } = useQuery({
    queryKey: ["tags"],
    queryFn: () =>
      apiClient<TagResponse[]>({ url: "/api/v1/tags", method: "GET" }),
  });

  const addMutation = useMutation({
    mutationFn: (tagName: string) =>
      apiClient<void>({
        url: `/api/v1/documents/${documentId}/tags`,
        method: "POST",
        data: { tag_name: tagName },
      }),
    onSuccess: () => {
      queryClient.invalidateQueries({
        queryKey: ["documents", documentId],
      });
      queryClient.invalidateQueries({ queryKey: ["tags"] });
      setInput("");
    },
  });

  const removeMutation = useMutation({
    mutationFn: (tagName: string) =>
      apiClient<void>({
        url: `/api/v1/documents/${documentId}/tags/${encodeURIComponent(tagName)}`,
        method: "DELETE",
      }),
    onSuccess: () => {
      queryClient.invalidateQueries({
        queryKey: ["documents", documentId],
      });
      queryClient.invalidateQueries({ queryKey: ["tags"] });
    },
  });

  const suggestions = allTags
    ?.filter(
      (t) =>
        t.tag_name.toLowerCase().includes(input.toLowerCase()) &&
        !tags.includes(t.tag_name),
    )
    .slice(0, 8);

  function handleAdd(tagName: string) {
    if (tagName.trim() && !tags.includes(tagName.trim())) {
      addMutation.mutate(tagName.trim());
    }
    setShowSuggestions(false);
  }

  return (
    <div className="space-y-2">
      <div className="flex flex-wrap gap-1">
        {tags.map((tag) => (
          <Badge key={tag} variant="secondary" className="gap-1">
            {tag}
            <button
              onClick={() => removeMutation.mutate(tag)}
              className="ml-0.5 rounded-full hover:bg-muted"
            >
              <X className="h-3 w-3" />
            </button>
          </Badge>
        ))}
      </div>
      <div className="relative">
        <Input
          value={input}
          onChange={(e) => {
            setInput(e.target.value);
            setShowSuggestions(true);
          }}
          onFocus={() => setShowSuggestions(true)}
          onBlur={() => {
            // Delay to allow click on suggestion
            setTimeout(() => setShowSuggestions(false), 200);
          }}
          onKeyDown={(e) => {
            if (e.key === "Enter") {
              e.preventDefault();
              handleAdd(input);
            }
          }}
          placeholder="Add tag..."
          className="h-8 text-sm"
        />
        {showSuggestions && input && suggestions && suggestions.length > 0 && (
          <div className="absolute z-10 mt-1 w-full rounded-md border bg-popover shadow-md">
            {suggestions.map((tag) => (
              <button
                key={tag.tag_name}
                className="flex w-full items-center justify-between px-3 py-1.5 text-sm hover:bg-accent"
                onMouseDown={(e) => {
                  e.preventDefault();
                  handleAdd(tag.tag_name);
                }}
              >
                <span>{tag.tag_name}</span>
                <span className="text-xs text-muted-foreground">
                  {tag.document_count}
                </span>
              </button>
            ))}
          </div>
        )}
      </div>
    </div>
  );
}
