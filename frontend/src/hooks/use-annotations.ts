import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import {
  fetchAnnotations,
  createAnnotation,
  updateAnnotation,
  deleteAnnotation,
} from "@/api/client";
import type { AnnotationCreate, AnnotationUpdate } from "@/types";

export function useAnnotations(documentId: string) {
  return useQuery({
    queryKey: ["annotations", documentId],
    queryFn: () => fetchAnnotations(documentId, { limit: 200 }),
    enabled: !!documentId,
  });
}

export function useCreateAnnotation(documentId: string) {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: (data: AnnotationCreate) => createAnnotation(data),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["annotations", documentId] });
    },
  });
}

export function useUpdateAnnotation(documentId: string) {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: ({ id, data }: { id: string; data: AnnotationUpdate }) =>
      updateAnnotation(id, data),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["annotations", documentId] });
    },
  });
}

export function useDeleteAnnotation(documentId: string) {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: (id: string) => deleteAnnotation(id),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["annotations", documentId] });
    },
  });
}
