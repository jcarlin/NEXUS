import { useQuery } from "@tanstack/react-query";
import { apiClient } from "@/api/client";
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
  DialogDescription,
} from "@/components/ui/dialog";
import { Skeleton } from "@/components/ui/skeleton";
import { formatDate } from "@/lib/utils";

interface EmailEntry {
  email_id: string;
  subject: string;
  date: string;
  message_id: string;
}

// TODO: replace with generated CommunicationPairsResponse after `npm run generate-api`
interface CommPairResponse {
  person_a: string;
  person_b: string;
  emails: EmailEntry[];
  total: number;
}

interface CommDrilldownProps {
  personA: string;
  personB: string;
  open: boolean;
  onOpenChange: (open: boolean) => void;
}

export function CommDrilldown({ personA, personB, open, onOpenChange }: CommDrilldownProps) {
  const { data, isLoading } = useQuery({
    queryKey: ["comm-pairs", personA, personB],
    queryFn: () =>
      apiClient<CommPairResponse>({
        url: "/api/v1/graph/communication-pairs",
        method: "GET",
        params: { person_a: personA, person_b: personB },
      }),
    enabled: open && !!personA && !!personB,
  });

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-w-lg max-h-[80vh] overflow-auto">
        <DialogHeader>
          <DialogTitle>
            {personA} &harr; {personB}
          </DialogTitle>
          <DialogDescription>
            {data ? `${data.total} communication(s)` : "Loading communications..."}
          </DialogDescription>
        </DialogHeader>

        {isLoading && (
          <div className="space-y-3">
            {Array.from({ length: 4 }).map((_, i) => (
              <Skeleton key={i} className="h-12 w-full" />
            ))}
          </div>
        )}

        {data && data.emails.length === 0 && (
          <p className="text-sm text-muted-foreground py-4">
            No emails found between these entities.
          </p>
        )}

        {data && data.emails.length > 0 && (
          <ul className="space-y-2">
            {data.emails.map((email) => (
              <li
                key={email.email_id}
                className="rounded-md border p-3 text-sm space-y-1"
              >
                <p className="font-medium truncate">{email.subject || "(no subject)"}</p>
                <p className="text-muted-foreground text-xs">
                  {formatDate(email.date)}
                </p>
              </li>
            ))}
          </ul>
        )}
      </DialogContent>
    </Dialog>
  );
}
