/**
 * Pure utility functions for dataset drag-and-drop document management.
 * No React dependencies — fully testable in isolation.
 */

/**
 * Determines which document IDs to include in a drag payload.
 * If the dragged document is already in the selection, includes all selected docs.
 * Otherwise, includes only the dragged document.
 */
export function buildDragPayload(
  draggedId: string,
  selectedIds: Set<string>,
): string[] {
  if (selectedIds.has(draggedId)) {
    return Array.from(selectedIds);
  }
  return [draggedId];
}

/**
 * Toggles a document ID in/out of the selection set (immutable).
 */
export function toggleSelection(
  current: Set<string>,
  id: string,
): Set<string> {
  const next = new Set(current);
  if (next.has(id)) {
    next.delete(id);
  } else {
    next.add(id);
  }
  return next;
}

/**
 * Checks whether all IDs on the current page are selected.
 * Returns false for an empty page.
 */
export function isAllSelected(
  selectedIds: Set<string>,
  pageIds: string[],
): boolean {
  return pageIds.length > 0 && pageIds.every((id) => selectedIds.has(id));
}
