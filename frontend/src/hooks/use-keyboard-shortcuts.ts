import { useEffect, useCallback, useState } from "react";
import { useNavigate } from "@tanstack/react-router";
import { useAppStore } from "@/stores/app-store";

interface KeyboardShortcutsOptions {
  onOpenCommandPalette: () => void;
}

export function useKeyboardShortcuts({ onOpenCommandPalette }: KeyboardShortcutsOptions) {
  const navigate = useNavigate();
  const toggleDefinedTerms = useAppStore((s) => s.toggleDefinedTerms);
  const toggleThreadSidebar = useAppStore((s) => s.toggleThreadSidebar);
  const [shortcutsHelpOpen, setShortcutsHelpOpen] = useState(false);

  useEffect(() => {
    function handleKeyDown(e: KeyboardEvent) {
      const target = e.target as HTMLElement;
      const isInput =
        target.tagName === "INPUT" ||
        target.tagName === "TEXTAREA" ||
        target.isContentEditable;

      // Ctrl+K / Cmd+K → open command palette
      if ((e.ctrlKey || e.metaKey) && e.key === "k") {
        e.preventDefault();
        onOpenCommandPalette();
        return;
      }

      // Ctrl+N / Cmd+N → new chat
      if ((e.ctrlKey || e.metaKey) && e.key === "n") {
        e.preventDefault();
        navigate({ to: "/chat" });
        return;
      }

      // Ctrl+B / Cmd+B → toggle thread sidebar
      if ((e.ctrlKey || e.metaKey) && e.key === "b") {
        e.preventDefault();
        toggleThreadSidebar();
        return;
      }

      // Ctrl+D / Cmd+D → toggle defined terms sidebar
      if ((e.ctrlKey || e.metaKey) && e.key === "d") {
        e.preventDefault();
        toggleDefinedTerms();
        return;
      }

      // Skip non-modifier shortcuts when focus is in an input
      if (isInput) return;

      // / → focus search
      if (e.key === "/") {
        const searchInput = document.querySelector<HTMLInputElement>(
          "[data-search-input]",
        );
        if (searchInput) {
          e.preventDefault();
          searchInput.focus();
        }
        return;
      }

      // Shift+? → toggle keyboard shortcuts help
      if (e.key === "?" && e.shiftKey) {
        e.preventDefault();
        setShortcutsHelpOpen((prev) => !prev);
        return;
      }

      // Esc → close any open dialog
      // (handled natively by Radix dialogs, but we ensure command palette closes)
    }

    document.addEventListener("keydown", handleKeyDown);
    return () => document.removeEventListener("keydown", handleKeyDown);
  }, [onOpenCommandPalette, navigate, toggleDefinedTerms, toggleThreadSidebar]);

  return { shortcutsHelpOpen, setShortcutsHelpOpen };
}

// ---------------------------------------------------------------------------
// Review-specific keyboard shortcuts
// ---------------------------------------------------------------------------

export interface ReviewShortcutOptions {
  /** Total number of items in the list */
  itemCount: number;
  /** Current focused index (-1 if none) */
  focusedIndex: number;
  /** Update focused index */
  onFocusChange: (index: number) => void;
  /** Open the focused item */
  onOpen?: (index: number) => void;
  /** Return to list / deselect */
  onEscape?: () => void;
  /** Toggle relevance tag on focused item */
  onToggleRelevance?: (index: number) => void;
  /** Toggle privilege status on focused item */
  onTogglePrivilege?: (index: number) => void;
  /** Navigate to previous document in set */
  onPrevDocument?: () => void;
  /** Navigate to next document in set */
  onNextDocument?: () => void;
}

export function useReviewShortcuts(options: ReviewShortcutOptions) {
  const {
    itemCount,
    focusedIndex,
    onFocusChange,
    onOpen,
    onEscape,
    onToggleRelevance,
    onTogglePrivilege,
    onPrevDocument,
    onNextDocument,
  } = options;

  const handleKeyDown = useCallback(
    (e: KeyboardEvent) => {
      const target = e.target as HTMLElement;
      const isInput =
        target.tagName === "INPUT" ||
        target.tagName === "TEXTAREA" ||
        target.isContentEditable;

      if (isInput) return;

      switch (e.key) {
        case "j": {
          e.preventDefault();
          const next = Math.min(focusedIndex + 1, itemCount - 1);
          onFocusChange(next);
          break;
        }
        case "k": {
          // Only handle bare 'k' without modifiers for review nav
          if (e.ctrlKey || e.metaKey) return;
          e.preventDefault();
          const prev = Math.max(focusedIndex - 1, 0);
          onFocusChange(prev);
          break;
        }
        case "Enter": {
          if (focusedIndex >= 0 && onOpen) {
            e.preventDefault();
            onOpen(focusedIndex);
          }
          break;
        }
        case "Escape": {
          if (onEscape) {
            e.preventDefault();
            onEscape();
          }
          break;
        }
        case "r": {
          if (focusedIndex >= 0 && onToggleRelevance) {
            e.preventDefault();
            onToggleRelevance(focusedIndex);
          }
          break;
        }
        case "p": {
          if (focusedIndex >= 0 && onTogglePrivilege) {
            e.preventDefault();
            onTogglePrivilege(focusedIndex);
          }
          break;
        }
        case "[": {
          if (onPrevDocument) {
            e.preventDefault();
            onPrevDocument();
          }
          break;
        }
        case "]": {
          if (onNextDocument) {
            e.preventDefault();
            onNextDocument();
          }
          break;
        }
      }
    },
    [
      itemCount,
      focusedIndex,
      onFocusChange,
      onOpen,
      onEscape,
      onToggleRelevance,
      onTogglePrivilege,
      onPrevDocument,
      onNextDocument,
    ],
  );

  useEffect(() => {
    document.addEventListener("keydown", handleKeyDown);
    return () => document.removeEventListener("keydown", handleKeyDown);
  }, [handleKeyDown]);
}
