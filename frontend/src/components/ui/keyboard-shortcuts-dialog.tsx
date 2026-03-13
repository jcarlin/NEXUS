import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
  DialogDescription,
} from "@/components/ui/dialog";

interface ShortcutEntry {
  keys: string[];
  description: string;
}

interface ShortcutGroup {
  title: string;
  shortcuts: ShortcutEntry[];
}

const isMac = typeof navigator !== "undefined" && /Mac|iPhone|iPad/.test(navigator.userAgent);
const modKey = isMac ? "\u2318" : "Ctrl";

const SHORTCUT_GROUPS: ShortcutGroup[] = [
  {
    title: "Global",
    shortcuts: [
      { keys: [`${modKey}+K`], description: "Open command palette" },
      { keys: [`${modKey}+N`], description: "New chat" },
      { keys: [`${modKey}+B`], description: "Toggle thread sidebar" },
      { keys: [`${modKey}+D`], description: "Toggle defined terms" },
      { keys: ["/"], description: "Focus search" },
      { keys: ["Shift+?"], description: "Show keyboard shortcuts" },
    ],
  },
  {
    title: "Chat / Citation Sidebar",
    shortcuts: [
      { keys: ["Esc"], description: "Collapse expanded view" },
      { keys: ["\u2190 / \u2192"], description: "Previous / next citation" },
    ],
  },
  {
    title: "Review",
    shortcuts: [
      { keys: ["j / k"], description: "Navigate down / up in list" },
      { keys: ["Enter"], description: "Open selected document" },
      { keys: ["Esc"], description: "Return to list" },
      { keys: ["r"], description: "Toggle relevance tag" },
      { keys: ["p"], description: "Toggle privilege status" },
      { keys: ["[ / ]"], description: "Previous / next document" },
    ],
  },
  {
    title: "Document Viewer",
    shortcuts: [
      { keys: ["\u2190 / \u2192"], description: "Previous / next page" },
      { keys: ["+/-"], description: "Zoom in / out" },
    ],
  },
];

interface KeyboardShortcutsDialogProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
}

export function KeyboardShortcutsDialog({
  open,
  onOpenChange,
}: KeyboardShortcutsDialogProps) {
  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-h-[80vh] overflow-y-auto sm:max-w-lg" data-testid="keyboard-shortcuts-dialog">
        <DialogHeader>
          <DialogTitle>Keyboard Shortcuts</DialogTitle>
          <DialogDescription>
            Available keyboard shortcuts grouped by context.
          </DialogDescription>
        </DialogHeader>

        <div className="space-y-6">
          {SHORTCUT_GROUPS.map((group) => (
            <div key={group.title}>
              <h3 className="mb-2 text-sm font-semibold text-muted-foreground">
                {group.title}
              </h3>
              <div className="space-y-1">
                {group.shortcuts.map((shortcut) => (
                  <div
                    key={shortcut.description}
                    className="flex items-center justify-between rounded-md px-2 py-1.5"
                  >
                    <span className="text-sm">{shortcut.description}</span>
                    <div className="flex gap-1">
                      {shortcut.keys.map((key) => (
                        <kbd
                          key={key}
                          className="rounded border bg-muted px-2 py-0.5 text-xs font-mono text-muted-foreground"
                        >
                          {key}
                        </kbd>
                      ))}
                    </div>
                  </div>
                ))}
              </div>
            </div>
          ))}
        </div>
      </DialogContent>
    </Dialog>
  );
}
