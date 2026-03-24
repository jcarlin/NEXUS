import { useState } from "react";
import { useNavigate } from "@tanstack/react-router";
import {
  LayoutDashboard,
  MessageSquare,
  FileText,
  Users,
  Network,
  BarChart3,
  Clock,
  Flame,
  ListChecks,
  Settings,
  Shield,
  ScrollText,
  FlaskConical,
} from "lucide-react";
import {
  CommandDialog,
  CommandEmpty,
  CommandGroup,
  CommandInput,
  CommandItem,
  CommandList,
  CommandSeparator,
} from "@/components/ui/command";

interface CommandPaletteProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
}

const pages = [
  { label: "Dashboard", to: "/admin/dashboard", icon: LayoutDashboard },
  { label: "Chat", to: "/chat", icon: MessageSquare },
  { label: "Documents", to: "/documents", icon: FileText },
  { label: "Entities", to: "/entities", icon: Users },
  { label: "Comms Matrix", to: "/analytics/comms", icon: BarChart3 },
  { label: "Timeline", to: "/analytics/timeline", icon: Clock },
  { label: "Network Graph", to: "/entities/network", icon: Network },
  { label: "Hot Docs", to: "/review/hot-docs", icon: Flame },
  { label: "Result Set", to: "/review/result-set", icon: ListChecks },
  { label: "Case Setup", to: "/case-setup", icon: Settings },
  { label: "Users", to: "/admin/users", icon: Shield },
  { label: "Audit Log", to: "/admin/audit-log", icon: ScrollText },
  { label: "Evaluation", to: "/admin/evaluation", icon: FlaskConical },
] as const;

export function CommandPalette({ open, onOpenChange }: CommandPaletteProps) {
  const navigate = useNavigate();
  const [search, setSearch] = useState("");

  function handleSelect(to: string) {
    onOpenChange(false);
    setSearch("");
    navigate({ to });
  }

  return (
    <CommandDialog open={open} onOpenChange={onOpenChange}>
      <CommandInput
        placeholder="Type a command or search..."
        value={search}
        onValueChange={setSearch}
      />
      <CommandList>
        <CommandEmpty>No results found.</CommandEmpty>
        <CommandGroup heading="Pages">
          {pages.map((page) => (
            <CommandItem
              key={page.to}
              value={page.label}
              onSelect={() => handleSelect(page.to)}
            >
              <page.icon className="mr-2 h-4 w-4" />
              <span>{page.label}</span>
            </CommandItem>
          ))}
        </CommandGroup>
        <CommandSeparator />
        <CommandGroup heading="Actions">
          <CommandItem
            value="New Chat"
            onSelect={() => handleSelect("/chat")}
          >
            <MessageSquare className="mr-2 h-4 w-4" />
            <span>New Chat</span>
          </CommandItem>
          <CommandItem
            value="Import Documents"
            onSelect={() => handleSelect("/documents/import")}
          >
            <FileText className="mr-2 h-4 w-4" />
            <span>Import Documents</span>
          </CommandItem>
        </CommandGroup>
      </CommandList>
    </CommandDialog>
  );
}
