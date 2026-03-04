import { User } from "lucide-react";

interface UserMessageProps {
  content: string;
}

export function UserMessage({ content }: UserMessageProps) {
  return (
    <div className="flex flex-col items-end gap-1">
      <div className="flex items-center gap-1.5 px-1">
        <span className="text-xs font-medium text-muted-foreground">You</span>
        <User className="h-3.5 w-3.5 text-muted-foreground" />
      </div>
      <div className="max-w-[80%] rounded-2xl bg-primary px-4 py-2.5 text-primary-foreground">
        <p className="whitespace-pre-wrap text-sm">{content}</p>
      </div>
    </div>
  );
}
