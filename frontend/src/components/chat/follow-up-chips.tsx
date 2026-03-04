interface FollowUpChipsProps {
  questions: string[];
  onSelect: (question: string) => void;
}

export function FollowUpChips({ questions, onSelect }: FollowUpChipsProps) {
  if (questions.length === 0) return null;

  return (
    <div className="flex flex-wrap gap-2">
      {questions.map((q, idx) => (
        <button
          key={q}
          onClick={() => onSelect(q)}
          className="animate-in fade-in slide-in-from-bottom-2 rounded-full border bg-background px-3 py-1.5 text-xs text-muted-foreground transition-colors duration-200 hover:bg-accent hover:text-accent-foreground"
          style={{ animationDelay: `${idx * 75}ms`, animationFillMode: "both" }}
        >
          {q}
        </button>
      ))}
    </div>
  );
}
