import { useState } from "react";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { Trash2, Info, AlertTriangle } from "lucide-react";
import { apiClient } from "@/api/client";
import { filterAvailableUsers } from "@/lib/dataset-access";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { Separator } from "@/components/ui/separator";
import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import type {
  DatasetAccessResponse,
  DatasetAccessRole,
  PaginatedResponse,
  User,
} from "@/types";

interface DatasetAccessDialogProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  datasetId: string;
}

export function DatasetAccessDialog({
  open,
  onOpenChange,
  datasetId,
}: DatasetAccessDialogProps) {
  const queryClient = useQueryClient();
  const [selectedUserId, setSelectedUserId] = useState("");
  const [selectedRole, setSelectedRole] = useState<DatasetAccessRole>("viewer");

  const { data: accessList, isLoading: accessLoading } = useQuery({
    queryKey: ["datasets", datasetId, "access"],
    queryFn: () =>
      apiClient<DatasetAccessResponse[]>({
        url: `/api/v1/datasets/${datasetId}/access`,
        method: "GET",
      }),
    enabled: open && !!datasetId,
  });

  const { data: usersData } = useQuery({
    queryKey: ["admin-users"],
    queryFn: () =>
      apiClient<PaginatedResponse<User>>({
        url: "/api/v1/admin/users",
        method: "GET",
        params: { limit: 100, offset: 0 },
      }),
    enabled: open,
  });

  const grantMutation = useMutation({
    mutationFn: (data: { user_id: string; access_role: DatasetAccessRole }) =>
      apiClient<DatasetAccessResponse>({
        url: `/api/v1/datasets/${datasetId}/access`,
        method: "POST",
        data,
      }),
    onSuccess: () => {
      queryClient.invalidateQueries({
        queryKey: ["datasets", datasetId, "access"],
      });
      setSelectedUserId("");
      setSelectedRole("viewer");
    },
  });

  const revokeMutation = useMutation({
    mutationFn: (userId: string) =>
      apiClient<void>({
        url: `/api/v1/datasets/${datasetId}/access/${userId}`,
        method: "DELETE",
      }),
    onSuccess: () => {
      queryClient.invalidateQueries({
        queryKey: ["datasets", datasetId, "access"],
      });
    },
  });

  const isDefaultOpen = !accessLoading && (!accessList || accessList.length === 0);
  const availableUsers = filterAvailableUsers(
    usersData?.items ?? [],
    accessList ?? [],
  );

  // Resolve user emails for display
  const userMap = new Map(
    (usersData?.items ?? []).map((u) => [u.id, u]),
  );

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="sm:max-w-lg">
        <DialogHeader>
          <DialogTitle>Dataset Permissions</DialogTitle>
          <DialogDescription>
            Manage who can access this dataset.
          </DialogDescription>
        </DialogHeader>

        <div className="space-y-4">
          {/* Default-open indicator */}
          {isDefaultOpen && (
            <Alert>
              <Info className="h-4 w-4" />
              <AlertTitle>Default Access</AlertTitle>
              <AlertDescription>
                All matter users can currently access this dataset. Adding a
                permission entry will restrict access to listed users only.
              </AlertDescription>
            </Alert>
          )}

          {/* Current access list */}
          {accessList && accessList.length > 0 && (
            <div className="space-y-2">
              <p className="text-sm font-medium">Current Access</p>
              <div className="divide-y rounded-md border">
                {accessList.map((entry) => {
                  const user = userMap.get(entry.user_id);
                  return (
                    <div
                      key={entry.id}
                      className="flex items-center justify-between px-3 py-2"
                    >
                      <div className="min-w-0">
                        <p className="truncate text-sm">
                          {user?.email ?? entry.user_id}
                        </p>
                        <p className="text-xs text-muted-foreground">
                          {new Date(entry.granted_at).toLocaleDateString()}
                        </p>
                      </div>
                      <div className="flex items-center gap-2">
                        <Badge variant="secondary">{entry.access_role}</Badge>
                        <Button
                          variant="ghost"
                          size="icon"
                          className="h-7 w-7 text-destructive hover:text-destructive"
                          onClick={() => revokeMutation.mutate(entry.user_id)}
                          disabled={revokeMutation.isPending}
                        >
                          <Trash2 className="h-3.5 w-3.5" />
                        </Button>
                      </div>
                    </div>
                  );
                })}
              </div>
            </div>
          )}

          <Separator />

          {/* Restriction warning when granting first access */}
          {isDefaultOpen && selectedUserId && (
            <Alert variant="destructive">
              <AlertTriangle className="h-4 w-4" />
              <AlertTitle>Warning</AlertTitle>
              <AlertDescription>
                Granting access will restrict this dataset. Only listed users
                will be able to access it.
              </AlertDescription>
            </Alert>
          )}

          {/* Grant access form */}
          <div className="space-y-3">
            <p className="text-sm font-medium">Grant Access</p>
            <div className="flex items-end gap-2">
              <div className="flex-1 space-y-1">
                <Select
                  value={selectedUserId}
                  onValueChange={setSelectedUserId}
                >
                  <SelectTrigger>
                    <SelectValue placeholder="Select user" />
                  </SelectTrigger>
                  <SelectContent>
                    {availableUsers.map((user) => (
                      <SelectItem key={user.id} value={user.id}>
                        {user.email}
                      </SelectItem>
                    ))}
                    {availableUsers.length === 0 && (
                      <SelectItem value="__none__" disabled>
                        No users available
                      </SelectItem>
                    )}
                  </SelectContent>
                </Select>
              </div>
              <div className="w-28 space-y-1">
                <Select
                  value={selectedRole}
                  onValueChange={(v) =>
                    setSelectedRole(v as DatasetAccessRole)
                  }
                >
                  <SelectTrigger>
                    <SelectValue />
                  </SelectTrigger>
                  <SelectContent>
                    <SelectItem value="viewer">Viewer</SelectItem>
                    <SelectItem value="editor">Editor</SelectItem>
                    <SelectItem value="admin">Admin</SelectItem>
                  </SelectContent>
                </Select>
              </div>
              <Button
                size="sm"
                disabled={
                  !selectedUserId ||
                  selectedUserId === "__none__" ||
                  grantMutation.isPending
                }
                onClick={() =>
                  grantMutation.mutate({
                    user_id: selectedUserId,
                    access_role: selectedRole,
                  })
                }
              >
                {grantMutation.isPending ? "Granting..." : "Grant"}
              </Button>
            </div>
          </div>

          {grantMutation.isError && (
            <p className="text-xs text-destructive">
              {grantMutation.error.message}
            </p>
          )}
        </div>
      </DialogContent>
    </Dialog>
  );
}
