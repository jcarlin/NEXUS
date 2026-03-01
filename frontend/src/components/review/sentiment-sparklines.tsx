interface SentimentSparklineProps {
  positive?: number | null;
  negative?: number | null;
  pressure?: number | null;
  opportunity?: number | null;
  rationalization?: number | null;
  intent?: number | null;
  concealment?: number | null;
}

const LABELS: { key: keyof SentimentSparklineProps; label: string; color: string }[] = [
  { key: "positive", label: "Pos", color: "bg-green-500" },
  { key: "negative", label: "Neg", color: "bg-red-500" },
  { key: "pressure", label: "Prs", color: "bg-orange-500" },
  { key: "opportunity", label: "Opp", color: "bg-yellow-500" },
  { key: "rationalization", label: "Rat", color: "bg-purple-500" },
  { key: "intent", label: "Int", color: "bg-blue-500" },
  { key: "concealment", label: "Con", color: "bg-gray-500" },
];

export function SentimentSparklines(props: SentimentSparklineProps) {
  const hasAny = LABELS.some((l) => props[l.key] != null);
  if (!hasAny) {
    return <span className="text-muted-foreground text-xs">--</span>;
  }

  return (
    <div className="flex flex-col gap-0.5 min-w-[120px]">
      {LABELS.map(({ key, label, color }) => {
        const value = props[key];
        if (value == null) return null;
        const widthPct = Math.max(value * 100, 2);
        return (
          <div key={key} className="flex items-center gap-1">
            <span className="text-[9px] text-muted-foreground w-6 text-right">{label}</span>
            <div className="flex-1 h-2 bg-muted rounded-sm overflow-hidden">
              <div
                className={`h-full rounded-sm ${color}`}
                style={{ width: `${widthPct}%` }}
              />
            </div>
          </div>
        );
      })}
    </div>
  );
}
