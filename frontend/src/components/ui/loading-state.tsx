import { useState, useEffect } from "react";
import { Loader2 } from "lucide-react";

interface LoadingStateProps {
  messages: string[];
  interval?: number;
  className?: string;
}

export function LoadingState({ messages, interval = 3000, className }: LoadingStateProps) {
  const [index, setIndex] = useState(0);

  useEffect(() => {
    if (messages.length <= 1) return;
    const timer = setInterval(() => {
      setIndex((i) => (i + 1) % messages.length);
    }, interval);
    return () => clearInterval(timer);
  }, [messages.length, interval]);

  return (
    <div className={`flex flex-col items-center justify-center gap-4 ${className ?? ""}`}>
      <Loader2 className="h-8 w-8 animate-spin text-muted-foreground" />
      <p className="text-sm text-muted-foreground animate-in fade-in duration-300" key={index}>
        {messages[index]}
      </p>
    </div>
  );
}
