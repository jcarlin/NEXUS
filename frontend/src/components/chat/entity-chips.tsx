import { Link } from "@tanstack/react-router";
import { Badge } from "@/components/ui/badge";
import type { EntityMention } from "@/types";

const typeColors: Record<string, string> = {
  PERSON: "bg-blue-100 text-blue-800 hover:bg-blue-200",
  ORGANIZATION: "bg-purple-100 text-purple-800 hover:bg-purple-200",
  LOCATION: "bg-green-100 text-green-800 hover:bg-green-200",
  DATE: "bg-amber-100 text-amber-800 hover:bg-amber-200",
  MONETARY: "bg-emerald-100 text-emerald-800 hover:bg-emerald-200",
  EMAIL: "bg-cyan-100 text-cyan-800 hover:bg-cyan-200",
  PHONE: "bg-orange-100 text-orange-800 hover:bg-orange-200",
};

interface EntityChipsProps {
  entities: EntityMention[];
}

export function EntityChips({ entities }: EntityChipsProps) {
  if (entities.length === 0) return null;

  return (
    <div className="flex flex-wrap gap-1.5">
      {entities.map((entity) => {
        const colorClass =
          typeColors[entity.type.toUpperCase()] ??
          "bg-gray-100 text-gray-800 hover:bg-gray-200";

        if (entity.kg_id) {
          return (
            <Link key={entity.name} to="/entities/$id" params={{ id: entity.kg_id }}>
              <Badge
                variant="outline"
                className={`cursor-pointer border-0 text-xs ${colorClass}`}
              >
                {entity.name}
              </Badge>
            </Link>
          );
        }

        return (
          <Badge
            key={entity.name}
            variant="outline"
            className={`border-0 text-xs ${colorClass}`}
          >
            {entity.name}
          </Badge>
        );
      })}
    </div>
  );
}
