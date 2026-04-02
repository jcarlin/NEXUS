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
  ToggleLeft,
  SlidersHorizontal,
  Activity,
  Gauge,
  ChevronsLeft,
  ChevronsRight,
  GitBranch,
  PanelLeft,
  X,
} from "lucide-react";
import { cn } from "@/lib/utils";
import { useAppStore } from "@/stores/app-store";
import { useAuthStore } from "@/stores/auth-store";
import { useFeatureFlags, type FeatureFlags } from "@/hooks/use-feature-flags";
import { Button } from "@/components/ui/button";
import { Tooltip, TooltipContent, TooltipTrigger } from "@/components/ui/tooltip";
import { ScrollArea } from "@/components/ui/scroll-area";

interface NavItem {
  to: string;
  label: string;
  icon: React.ComponentType<{ className?: string }>;
  roles?: string[];
  pageFlag?: keyof FeatureFlags;
}

const mainNav: NavItem[] = [
  { to: "/chat", label: "Chat", icon: MessageSquare, pageFlag: "page_chat" },
  { to: "/documents", label: "Documents", icon: FileText, pageFlag: "page_documents" },
  { to: "/documents/import", label: "Ingest", icon: Upload, pageFlag: "page_ingest" },
  { to: "/datasets", label: "Datasets", icon: FolderTree, pageFlag: "page_datasets" },
  { to: "/entities", label: "Entities", icon: Users, pageFlag: "page_entities" },
];

const analysisNav: NavItem[] = [
  { to: "/analytics/comms", label: "Comms Matrix", icon: BarChart3, pageFlag: "page_comms_matrix" },
  { to: "/analytics/timeline", label: "Timeline", icon: Clock, pageFlag: "page_timeline" },
  { to: "/entities/network", label: "Network Graph", icon: Network, pageFlag: "page_network_graph" },
];

const reviewNav: NavItem[] = [
  { to: "/review/hot-docs", label: "Hot Docs", icon: Flame, pageFlag: "page_hot_docs" },
  { to: "/review/result-set", label: "Result Set", icon: ListChecks, pageFlag: "page_result_set" },
  { to: "/review/exports", label: "Exports", icon: Package, pageFlag: "page_exports" },
  { to: "/case-setup", label: "Case Setup", icon: Settings, roles: ["admin", "attorney"], pageFlag: "page_case_setup" },
];

const adminNav: NavItem[] = [
  { to: "/admin/dashboard", label: "Dashboard", icon: LayoutDashboard, roles: ["admin"] },
  { to: "/admin/pipeline", label: "Pipeline", icon: Gauge, roles: ["admin"] },
  { to: "/admin/users", label: "Users", icon: Shield, roles: ["admin"] },
  { to: "/admin/audit-log", label: "Audit Log", icon: ScrollText, roles: ["admin"] },
  { to: "/admin/evaluation", label: "Evaluation", icon: FlaskConical, roles: ["admin"] },
  { to: "/admin/knowledge-graph", label: "Graph Admin", icon: Network, roles: ["admin"] },
  { to: "/admin/llm-settings", label: "LLM Settings", icon: Settings, roles: ["admin"] },
  { to: "/admin/feature-flags", label: "Feature Flags", icon: ToggleLeft, roles: ["admin"] },
  { to: "/admin/pages", label: "Pages", icon: PanelLeft, roles: ["admin"] },
  { to: "/admin/settings", label: "Settings", icon: SlidersHorizontal, roles: ["admin"] },
  { to: "/admin/operations", label: "Operations", icon: Activity, roles: ["admin"] },
  { to: "/admin/architecture", label: "Architecture", icon: GitBranch, roles: ["admin"] },
];

interface SidebarProps {
  forceExpanded?: boolean;
  onClose?: () => void;
}

export function Sidebar({ forceExpanded, onClose }: SidebarProps = {}) {
  const storeCollapsed = useAppStore((s) => s.sidebarCollapsed);
  const collapsed = forceExpanded ? false : storeCollapsed;
  const toggleSidebar = useAppStore((s) => s.toggleSidebar);
  const userRole = useAuthStore((s) => s.user?.role);
  const { data: flags } = useFeatureFlags();

  const matchRoute = useMatchRoute();

  function filterVisible(items: NavItem[]) {
    return items
      .filter((item) => !item.roles || (userRole && item.roles.includes(userRole)))
      .filter((item) => !item.pageFlag || flags?.[item.pageFlag] !== false);
  }

  const allPaths = [...mainNav, ...analysisNav, ...reviewNav, ...adminNav].map((i) => i.to);

  function NavLink({ item }: { item: NavItem }) {
    const isMatch = matchRoute({ to: item.to, fuzzy: true });
    // Suppress active state if a more specific sibling also matches (e.g. /documents vs /documents/import)
    const isShadowed =
      isMatch &&
      allPaths.some(
        (p) => p !== item.to && p.startsWith(item.to) && matchRoute({ to: p, fuzzy: true }),
      );
    const isActive = isMatch && !isShadowed;
    const Icon = item.icon;

    const link = (
      <Link
        to={item.to}
        className={cn(
          "group relative flex items-center gap-3 rounded-lg px-3 py-2 text-sm font-medium transition-all duration-150 hover:bg-white/[0.06] hover:text-foreground",
          isActive && "bg-white/[0.08] text-foreground",
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
    const filtered = filterVisible(items);
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
      data-tour="sidebar-nav"
      className={cn(
        "flex h-full flex-col border-r border-sidebar-border/40 bg-sidebar backdrop-blur-xl text-sidebar-foreground transition-all duration-200",
        collapsed ? "w-14" : "w-56",
      )}
    >
      <div className={cn("flex h-14 items-center border-b border-sidebar-border/50 px-3", collapsed ? "justify-center" : "justify-between")}>
        {!collapsed && <span className="text-lg font-bold tracking-widest text-amber">NEXUS</span>}
        {forceExpanded ? (
          onClose && (
            <Button variant="ghost" size="icon" onClick={onClose} className="h-7 w-7 text-sidebar-foreground hover:text-foreground" aria-label="Close menu">
              <X className="h-4 w-4" />
            </Button>
          )
        ) : (
          <Tooltip>
            <TooltipTrigger asChild>
              <Button variant="ghost" size="icon" onClick={toggleSidebar} className="h-7 w-7 text-muted-foreground hover:text-foreground">
                {collapsed ? <ChevronsRight className="h-4 w-4" /> : <ChevronsLeft className="h-4 w-4" />}
              </Button>
            </TooltipTrigger>
            <TooltipContent side="right">{collapsed ? "Expand sidebar" : "Collapse sidebar"}</TooltipContent>
          </Tooltip>
        )}
      </div>

      <ScrollArea className="flex-1 px-2 py-3">
        <div className="space-y-4">
          <NavSection title="Main" items={mainNav} />
          <div className="mx-3 h-px bg-sidebar-border/30" />
          <NavSection title="Analysis" items={analysisNav} />
          <div className="mx-3 h-px bg-sidebar-border/30" />
          <NavSection title="Review" items={reviewNav} />
          {filterVisible(adminNav).length > 0 && (
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
