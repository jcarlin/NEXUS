interface FollowUpChipsProps {
  questions: string[];
  onSelect: (question: string) => void;
}

export function FollowUpChips({ questions, onSelect }: FollowUpChipsProps) {
  if (questions.length === 0) return null;

  return (
    <div className="flex flex-wrap gap-2">
      {questions.map((q) => (
        <button
          key={q}
          onClick={() => onSelect(q)}
          className="rounded-full border bg-background px-3 py-1.5 text-xs text-muted-foreground transition-colors hover:bg-accent hover:text-accent-foreground"
        >
          {q}
        </button>
      ))}
    </div>
  );
}
