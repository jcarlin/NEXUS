import { AlertCircle, RotateCcw } from "lucide-react";
import { Button } from "@/components/ui/button";

interface ErrorMessageProps {
  message: string;
  onRetry: () => void;
}

export function ErrorMessage({ message, onRetry }: ErrorMessageProps) {
  return (
    <div className="flex justify-start">
      <div className="max-w-[80%] rounded-lg border border-destructive/30 bg-destructive/5 px-4 py-3">
        <div className="flex items-start gap-2">
          <AlertCircle className="mt-0.5 h-4 w-4 shrink-0 text-destructive" />
          <div className="min-w-0 flex-1 space-y-2">
            <p className="text-sm text-destructive">{message}</p>
            <Button
              variant="outline"
              size="sm"
              className="h-7 gap-1.5 text-xs"
              onClick={onRetry}
            >
              <RotateCcw className="h-3 w-3" />
              Try again
            </Button>
          </div>
        </div>
      </div>
    </div>
  );
}
