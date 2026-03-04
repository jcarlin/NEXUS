import { useState } from "react";
import { useForm } from "react-hook-form";
import { zodResolver } from "@hookform/resolvers/zod";
import { z } from "zod";
import { Trash2, Pencil, MessageSquare, Highlighter, Tag } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import {
  useCreateAnnotation,
  useUpdateAnnotation,
  useDeleteAnnotation,
} from "@/hooks/use-annotations";
import type { Annotation, AnnotationType, AnnotationAnchor } from "@/types";

const annotationSchema = z.object({
  content: z.string().min(1, "Content is required"),
  annotation_type: z.enum(["note", "highlight", "tag"]),
  color: z.string().optional(),
});

type AnnotationFormValues = z.infer<typeof annotationSchema>;

const TYPE_ICONS: Record<AnnotationType, React.ReactNode> = {
  note: <MessageSquare className="h-3.5 w-3.5" />,
  highlight: <Highlighter className="h-3.5 w-3.5" />,
  tag: <Tag className="h-3.5 w-3.5" />,
};

const COLOR_OPTIONS = [
  { value: "rgba(255, 230, 0, 0.3)", label: "Yellow" },
  { value: "rgba(59, 130, 246, 0.25)", label: "Blue" },
  { value: "rgba(16, 185, 129, 0.25)", label: "Green" },
  { value: "rgba(239, 68, 68, 0.25)", label: "Red" },
  { value: "rgba(168, 85, 247, 0.25)", label: "Purple" },
];

interface AnnotationPanelProps {
  documentId: string;
  annotations: Annotation[];
  selectedId?: string | null;
  onSelectAnnotation?: (annotation: Annotation) => void;
  pendingAnchor?: { anchor: AnnotationAnchor; pageNumber: number } | null;
  onClearPending?: () => void;
}

export function AnnotationPanel({
  documentId,
  annotations,
  selectedId,
  onSelectAnnotation,
  pendingAnchor,
  onClearPending,
}: AnnotationPanelProps) {
  const [editingId, setEditingId] = useState<string | null>(null);

  const createMutation = useCreateAnnotation(documentId);
  const updateMutation = useUpdateAnnotation(documentId);
  const deleteMutation = useDeleteAnnotation(documentId);

  const form = useForm<AnnotationFormValues>({
    resolver: zodResolver(annotationSchema),
    defaultValues: {
      content: "",
      annotation_type: "highlight",
      color: COLOR_OPTIONS[0]!.value,
    },
  });

  const onSubmitCreate = (values: AnnotationFormValues) => {
    createMutation.mutate(
      {
        document_id: documentId,
        content: values.content,
        annotation_type: values.annotation_type as AnnotationType,
        color: values.color || null,
        page_number: pendingAnchor?.pageNumber ?? null,
        anchor: pendingAnchor?.anchor,
      },
      {
        onSuccess: () => {
          form.reset();
          onClearPending?.();
        },
      },
    );
  };

  const onSubmitEdit = (id: string, content: string) => {
    updateMutation.mutate(
      { id, data: { content } },
      { onSuccess: () => setEditingId(null) },
    );
  };

  // Group annotations by page number
  const grouped = annotations.reduce<Record<string, Annotation[]>>((acc, a) => {
    const key = a.page_number != null ? `Page ${a.page_number}` : "No page";
    (acc[key] ??= []).push(a);
    return acc;
  }, {});

  const sortedGroups = Object.entries(grouped).sort(([a], [b]) => {
    const numA = parseInt(a.replace("Page ", ""));
    const numB = parseInt(b.replace("Page ", ""));
    if (isNaN(numA)) return 1;
    if (isNaN(numB)) return -1;
    return numA - numB;
  });

  return (
    <div className="space-y-4">
      {/* Create Form */}
      <Card>
        <CardHeader className="pb-3">
          <CardTitle className="text-sm">
            {pendingAnchor ? "Add Annotation to Selection" : "Add Annotation"}
          </CardTitle>
        </CardHeader>
        <CardContent>
          <form onSubmit={form.handleSubmit(onSubmitCreate)} className="space-y-3">
            <div className="space-y-1">
              <Label htmlFor="annotation_type" className="text-xs">Type</Label>
              <Select
                value={form.watch("annotation_type")}
                onValueChange={(v) => form.setValue("annotation_type", v as AnnotationType)}
              >
                <SelectTrigger id="annotation_type">
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value="highlight">Highlight</SelectItem>
                  <SelectItem value="note">Note</SelectItem>
                  <SelectItem value="tag">Tag</SelectItem>
                </SelectContent>
              </Select>
            </div>

            <div className="space-y-1">
              <Label htmlFor="content" className="text-xs">Content</Label>
              <textarea
                id="content"
                {...form.register("content")}
                className="flex w-full rounded-md border border-input bg-transparent px-3 py-2 text-sm shadow-sm placeholder:text-muted-foreground focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-ring min-h-[60px] resize-y"
                placeholder="Enter annotation text..."
              />
              {form.formState.errors.content && (
                <p className="text-xs text-destructive">{form.formState.errors.content.message}</p>
              )}
            </div>

            <div className="space-y-1">
              <Label htmlFor="color" className="text-xs">Color</Label>
              <Select
                value={form.watch("color") ?? ""}
                onValueChange={(v) => form.setValue("color", v)}
              >
                <SelectTrigger id="color">
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  {COLOR_OPTIONS.map((c) => (
                    <SelectItem key={c.value} value={c.value}>
                      <span className="flex items-center gap-2">
                        <span
                          className="inline-block w-3 h-3 rounded-sm border"
                          style={{ backgroundColor: c.value }}
                        />
                        {c.label}
                      </span>
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>

            <div className="flex gap-2">
              <Button type="submit" size="sm" disabled={createMutation.isPending}>
                {createMutation.isPending ? "Adding..." : "Add"}
              </Button>
              {pendingAnchor && (
                <Button type="button" variant="ghost" size="sm" onClick={onClearPending}>
                  Cancel
                </Button>
              )}
            </div>
          </form>
        </CardContent>
      </Card>

      {/* Annotation List */}
      {sortedGroups.map(([group, items]) => (
        <Card key={group}>
          <CardHeader className="pb-2">
            <CardTitle className="text-xs text-muted-foreground">{group}</CardTitle>
          </CardHeader>
          <CardContent className="space-y-2">
            {items.map((annotation) => (
              <div
                key={annotation.id}
                className={`flex items-start gap-2 rounded-md p-2 text-sm cursor-pointer transition-colors ${
                  annotation.id === selectedId
                    ? "bg-accent"
                    : "hover:bg-muted/50"
                }`}
                onClick={() => onSelectAnnotation?.(annotation)}
              >
                <span className="mt-0.5 shrink-0">{TYPE_ICONS[annotation.annotation_type]}</span>
                <div className="flex-1 min-w-0">
                  {editingId === annotation.id ? (
                    <EditInline
                      initialValue={annotation.content}
                      onSave={(content) => onSubmitEdit(annotation.id, content)}
                      onCancel={() => setEditingId(null)}
                    />
                  ) : (
                    <p className="text-sm leading-snug break-words">{annotation.content}</p>
                  )}
                </div>
                {editingId !== annotation.id && (
                  <div className="flex shrink-0 gap-1">
                    <Button
                      variant="ghost"
                      size="icon"
                      className="h-6 w-6"
                      onClick={(e) => {
                        e.stopPropagation();
                        setEditingId(annotation.id);
                      }}
                    >
                      <Pencil className="h-3 w-3" />
                    </Button>
                    <Button
                      variant="ghost"
                      size="icon"
                      className="h-6 w-6 text-destructive"
                      onClick={(e) => {
                        e.stopPropagation();
                        deleteMutation.mutate(annotation.id);
                      }}
                    >
                      <Trash2 className="h-3 w-3" />
                    </Button>
                  </div>
                )}
              </div>
            ))}
          </CardContent>
        </Card>
      ))}

      {annotations.length === 0 && (
        <p className="text-sm text-muted-foreground text-center py-4">
          No annotations yet. Drag on the PDF to highlight a region, or use the form above.
        </p>
      )}
    </div>
  );
}

function EditInline({
  initialValue,
  onSave,
  onCancel,
}: {
  initialValue: string;
  onSave: (value: string) => void;
  onCancel: () => void;
}) {
  const [value, setValue] = useState(initialValue);

  return (
    <div className="space-y-1">
      <Input
        value={value}
        onChange={(e) => setValue(e.target.value)}
        autoFocus
        onKeyDown={(e) => {
          if (e.key === "Enter") onSave(value);
          if (e.key === "Escape") onCancel();
        }}
      />
      <div className="flex gap-1">
        <Button size="sm" variant="outline" className="h-6 text-xs" onClick={() => onSave(value)}>
          Save
        </Button>
        <Button size="sm" variant="ghost" className="h-6 text-xs" onClick={onCancel}>
          Cancel
        </Button>
      </div>
    </div>
  );
}
