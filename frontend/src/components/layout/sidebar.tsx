import { Link, useMatchRoute } from "@tanstack/react-router";
import {
  LayoutDashboard,
  MessageSquare,
  FileText,
  FolderTree,
  Upload,
  Users,
  Network,
  BarChart3,
  Clock,
  Flame,
  ListChecks,
  Package,
  Settings,
  Shield,
  ScrollText,
  FlaskConical,
  PanelLeftClose,
  PanelLeft,
} from "lucide-react";
import { cn } from "@/lib/utils";
import { useAppStore } from "@/stores/app-store";
import { useAuthStore } from "@/stores/auth-store";
import { Button } from "@/components/ui/button";
import { Tooltip, TooltipContent, TooltipTrigger } from "@/components/ui/tooltip";
import { ScrollArea } from "@/components/ui/scroll-area";

interface NavItem {
  to: string;
  label: string;
  icon: React.ComponentType<{ className?: string }>;
  roles?: string[];
}

const mainNav: NavItem[] = [
  { to: "/", label: "Dashboard", icon: LayoutDashboard },
  { to: "/chat", label: "Chat", icon: MessageSquare },
  { to: "/documents", label: "Documents", icon: FileText },
  { to: "/documents/import", label: "Ingest", icon: Upload },
  { to: "/datasets", label: "Datasets", icon: FolderTree },
  { to: "/entities", label: "Entities", icon: Users },
];

const analysisNav: NavItem[] = [
  { to: "/analytics/comms", label: "Comms Matrix", icon: BarChart3 },
  { to: "/analytics/timeline", label: "Timeline", icon: Clock },
  { to: "/entities/network", label: "Network Graph", icon: Network },
];

const reviewNav: NavItem[] = [
  { to: "/review/hot-docs", label: "Hot Docs", icon: Flame },
  { to: "/review/result-set", label: "Result Set", icon: ListChecks },
  { to: "/review/exports", label: "Exports", icon: Package },
  { to: "/case-setup", label: "Case Setup", icon: Settings, roles: ["admin", "attorney"] },
];

const adminNav: NavItem[] = [
  { to: "/admin/users", label: "Users", icon: Shield, roles: ["admin"] },
  { to: "/admin/audit-log", label: "Audit Log", icon: ScrollText, roles: ["admin"] },
  { to: "/admin/evaluation", label: "Evaluation", icon: FlaskConical, roles: ["admin"] },
  { to: "/admin/knowledge-graph", label: "Knowledge Graph", icon: Network, roles: ["admin"] },
];

export function Sidebar() {
  const collapsed = useAppStore((s) => s.sidebarCollapsed);
  const toggleSidebar = useAppStore((s) => s.toggleSidebar);
  const userRole = useAuthStore((s) => s.user?.role);

  const matchRoute = useMatchRoute();

  function filterByRole(items: NavItem[]) {
    return items.filter((item) => !item.roles || (userRole && item.roles.includes(userRole)));
  }

  function NavLink({ item }: { item: NavItem }) {
    const isActive = matchRoute({ to: item.to, fuzzy: true });
    const Icon = item.icon;

    const link = (
      <Link
        to={item.to}
        className={cn(
          "group relative flex items-center gap-3 rounded-md px-3 py-2 text-sm font-medium transition-all duration-150 hover:bg-accent/60 hover:text-foreground",
          isActive && "bg-accent text-foreground",
          collapsed && "justify-center px-2",
        )}
      >
        {isActive && (
          <span className="absolute left-0 top-1 bottom-1 w-[3px] rounded-full bg-amber" />
        )}
        <Icon className={cn(
          "h-4 w-4 shrink-0 transition-colors",
          isActive ? "text-amber" : "text-muted-foreground group-hover:text-foreground",
        )} />
        {!collapsed && <span>{item.label}</span>}
      </Link>
    );

    if (collapsed) {
      return (
        <Tooltip>
          <TooltipTrigger asChild>{link}</TooltipTrigger>
          <TooltipContent side="right">{item.label}</TooltipContent>
        </Tooltip>
      );
    }

    return link;
  }

  function NavSection({ title, items }: { title: string; items: NavItem[] }) {
    const filtered = filterByRole(items);
    if (filtered.length === 0) return null;
    return (
      <div className="space-y-1">
        {!collapsed && (
          <p className="px-3 py-1 text-xs font-semibold uppercase tracking-wider text-muted-foreground">
            {title}
          </p>
        )}
        {filtered.map((item) => (
          <NavLink key={item.to} item={item} />
        ))}
      </div>
    );
  }

  return (
    <aside
      className={cn(
        "flex h-full flex-col border-r bg-sidebar text-sidebar-foreground transition-all duration-200",
        collapsed ? "w-14" : "w-56",
      )}
    >
      <div className={cn("flex h-14 items-center border-b border-sidebar-border/50 px-3", collapsed ? "justify-center" : "justify-between")}>
        {!collapsed && <span className="text-lg font-bold tracking-widest text-amber">NEXUS</span>}
        <Button variant="ghost" size="icon" onClick={toggleSidebar} className="h-8 w-8 text-muted-foreground hover:text-foreground">
          {collapsed ? <PanelLeft className="h-4 w-4" /> : <PanelLeftClose className="h-4 w-4" />}
        </Button>
      </div>

      <ScrollArea className="flex-1 px-2 py-3">
        <div className="space-y-4">
          <NavSection title="Main" items={mainNav} />
          <div className="mx-3 h-px bg-sidebar-border/30" />
          <NavSection title="Analysis" items={analysisNav} />
          <div className="mx-3 h-px bg-sidebar-border/30" />
          <NavSection title="Review" items={reviewNav} />
          {filterByRole(adminNav).length > 0 && (
            <>
              <div className="mx-3 h-px bg-sidebar-border/30" />
              <NavSection title="Admin" items={adminNav} />
            </>
          )}
        </div>
      </ScrollArea>
    </aside>
  );
}
