import type { LucideIcon } from "lucide-react";
import { Link } from "@tanstack/react-router";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";
import { formatNumber } from "@/lib/utils";

interface StatCardProps {
  title: string;
  value: string | number;
  icon: LucideIcon;
  description?: string;
  loading?: boolean;
  href?: string;
}

export function StatCard({ title, value, icon: Icon, description, loading, href }: StatCardProps) {
  const card = (
    <Card className={href ? "transition-colors hover:border-primary/50 hover:bg-muted/50" : undefined}>
      <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
        <CardTitle className="text-sm font-medium">{title}</CardTitle>
        <Icon className="h-4 w-4 text-muted-foreground" />
      </CardHeader>
      <CardContent>
        {loading ? (
          <Skeleton className="h-7 w-20" />
        ) : (
          <div className="text-2xl font-semibold tracking-tight tabular-nums">{typeof value === "number" ? formatNumber(value) : value}</div>
        )}
        {description && <p className="text-xs text-muted-foreground">{description}</p>}
      </CardContent>
    </Card>
  );

  if (href) {
    return (
      <Link to={href} className="no-underline">
        {card}
      </Link>
    );
  }

  return card;
}
