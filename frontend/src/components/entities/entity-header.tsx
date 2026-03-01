import { Badge } from "@/components/ui/badge";
import { Card, CardContent } from "@/components/ui/card";
import { formatDate } from "@/lib/utils";
import type { EntityResponse } from "@/types";

const TYPE_COLORS: Record<string, string> = {
  PERSON: "bg-blue-500/15 text-blue-400 border-blue-500/30",
  ORG: "bg-emerald-500/15 text-emerald-400 border-emerald-500/30",
  LOCATION: "bg-orange-500/15 text-orange-400 border-orange-500/30",
  DATE: "bg-violet-500/15 text-violet-400 border-violet-500/30",
  MONEY: "bg-pink-500/15 text-pink-400 border-pink-500/30",
};

function typeBadgeClass(type: string): string {
  return TYPE_COLORS[type] ?? "bg-slate-500/15 text-slate-400 border-slate-500/30";
}

interface EntityHeaderProps {
  entity: EntityResponse;
}

export function EntityHeader({ entity }: EntityHeaderProps) {
  return (
    <Card>
      <CardContent className="pt-6">
        <div className="flex items-start justify-between">
          <div className="space-y-2">
            <div className="flex items-center gap-3">
              <h1 className="text-2xl font-bold">{entity.name}</h1>
              <Badge
                variant="outline"
                className={`text-xs uppercase ${typeBadgeClass(entity.type)}`}
              >
                {entity.type}
              </Badge>
            </div>
            {entity.description && (
              <p className="text-sm text-muted-foreground max-w-2xl">
                {entity.description}
              </p>
            )}
            {entity.aliases.length > 0 && (
              <div className="flex items-center gap-2 flex-wrap">
                <span className="text-xs text-muted-foreground">Aliases:</span>
                {entity.aliases.map((alias) => (
                  <Badge key={alias} variant="secondary" className="text-[10px]">
                    {alias}
                  </Badge>
                ))}
              </div>
            )}
          </div>
          <div className="text-right space-y-1 shrink-0">
            <p className="text-2xl font-bold tabular-nums">
              {entity.mention_count}
            </p>
            <p className="text-xs text-muted-foreground">mentions</p>
          </div>
        </div>
        <div className="flex gap-6 mt-4 text-sm text-muted-foreground">
          {entity.first_seen && (
            <div>
              <span className="font-medium text-foreground">First seen: </span>
              {formatDate(entity.first_seen)}
            </div>
          )}
          {entity.last_seen && (
            <div>
              <span className="font-medium text-foreground">Last seen: </span>
              {formatDate(entity.last_seen)}
            </div>
          )}
        </div>
      </CardContent>
    </Card>
  );
}
