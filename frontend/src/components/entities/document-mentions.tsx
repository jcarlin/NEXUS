import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";

interface DocumentMentionsProps {
  entityName: string;
}

export function DocumentMentions({ entityName }: DocumentMentionsProps) {
  return (
    <Card>
      <CardHeader>
        <CardTitle className="text-sm font-medium">
          Document Mentions
        </CardTitle>
      </CardHeader>
      <CardContent>
        <p className="text-sm text-muted-foreground">
          Documents mentioning &quot;{entityName}&quot; will appear here once
          the document-entity lookup endpoint is available.
        </p>
      </CardContent>
    </Card>
  );
}
