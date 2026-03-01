import { Card, CardContent } from "@/components/ui/card";

interface UserMessageProps {
  content: string;
}

export function UserMessage({ content }: UserMessageProps) {
  return (
    <div className="flex justify-end">
      <Card className="max-w-[80%] bg-primary text-primary-foreground">
        <CardContent className="p-3">
          <p className="whitespace-pre-wrap text-sm">{content}</p>
        </CardContent>
      </Card>
    </div>
  );
}
