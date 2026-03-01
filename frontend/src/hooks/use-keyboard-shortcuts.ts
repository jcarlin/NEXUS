import { useEffect } from "react";
import { useNavigate } from "@tanstack/react-router";
import { useAppStore } from "@/stores/app-store";

interface KeyboardShortcutsOptions {
  onOpenCommandPalette: () => void;
}

export function useKeyboardShortcuts({ onOpenCommandPalette }: KeyboardShortcutsOptions) {
  const navigate = useNavigate();
  const toggleDefinedTerms = useAppStore((s) => s.toggleDefinedTerms);

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

      // Ctrl+D / Cmd+D → toggle defined terms sidebar
      if ((e.ctrlKey || e.metaKey) && e.key === "d") {
        e.preventDefault();
        toggleDefinedTerms();
        return;
      }

      // / → focus search (only if not already in an input)
      if (e.key === "/" && !isInput) {
        const searchInput = document.querySelector<HTMLInputElement>(
          "[data-search-input]",
        );
        if (searchInput) {
          e.preventDefault();
          searchInput.focus();
        }
        return;
      }

      // Esc → close any open dialog
      // (handled natively by Radix dialogs, but we ensure command palette closes)
    }

    document.addEventListener("keydown", handleKeyDown);
    return () => document.removeEventListener("keydown", handleKeyDown);
  }, [onOpenCommandPalette, navigate, toggleDefinedTerms]);
}
