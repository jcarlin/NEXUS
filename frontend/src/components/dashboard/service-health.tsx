import { Link } from "@tanstack/react-router";
import { useHealthApiV1HealthGet } from "@/api/generated/system/system";
import { Card, CardContent } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import {
  ArrowRight,
  Database,
  Search,
  GitBranch,
  MemoryStick,
  HardDrive,
} from "lucide-react";
import type { LucideIcon } from "lucide-react";
import { useAuthStore } from "@/stores/auth-store";

interface ServiceDef {
  key: string;
  label: string;
  icon: LucideIcon;
}

const SERVICES: ServiceDef[] = [
  { key: "postgres", label: "PostgreSQL", icon: Database },
  { key: "qdrant", label: "Qdrant", icon: Search },
  { key: "neo4j", label: "Neo4j", icon: GitBranch },
  { key: "redis", label: "Redis", icon: MemoryStick },
  { key: "minio", label: "MinIO", icon: HardDrive },
];

interface HealthResponse {
  status: string;
  services: Record<string, string>;
}

function StatusDot({ status }: { status: "ok" | "error" | "loading" }) {
  const color =
    status === "ok"
      ? "bg-green-500"
      : status === "error"
        ? "bg-red-500"
        : "bg-muted-foreground/40";

  return (
    <span
      className={`inline-block h-2 w-2 rounded-full ${color}`}
      aria-label={status}
    />
  );
}

export function ServiceHealth() {
  const userRole = useAuthStore((s) => s.user?.role);
  const { data, isLoading } = useHealthApiV1HealthGet({
    query: { refetchInterval: 30000 },
  });

  const health = data as HealthResponse | undefined;
  const services = health?.services ?? {};

  const allOk =
    !isLoading &&
    health &&
    SERVICES.every((s) => services[s.key] === "ok");

  return (
    <Card className="flex-1 min-w-0">
      <CardContent className="flex items-center gap-6 py-3">
        <div className="flex items-center gap-4 flex-wrap">
          {SERVICES.map(({ key, label, icon: Icon }) => {
            const raw = services[key];
            const status: "ok" | "error" | "loading" = isLoading
              ? "loading"
              : raw === "ok"
                ? "ok"
                : "error";

            return (
              <div key={key} className="flex items-center gap-1.5 text-sm">
                <Icon className="h-3.5 w-3.5 text-muted-foreground" />
                <span className="text-muted-foreground">{label}</span>
                <StatusDot status={status} />
              </div>
            );
          })}
        </div>
        <div className="ml-auto flex items-center gap-2">
          {isLoading ? (
            <Badge variant="secondary">Checking...</Badge>
          ) : allOk ? (
            <Badge variant="secondary" className="bg-green-500/10 text-green-600 border-green-500/20">
              All Systems Operational
            </Badge>
          ) : (
            <Badge variant="destructive">Degraded</Badge>
          )}
          {userRole === "admin" && (
            <Link
              to="/admin/operations"
              className="text-xs text-muted-foreground hover:text-foreground transition-colors flex items-center gap-1"
            >
              Operations
              <ArrowRight className="h-3 w-3" />
            </Link>
          )}
        </div>
      </CardContent>
    </Card>
  );
}
