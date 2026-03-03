import { useState } from "react";
import { createFileRoute } from "@tanstack/react-router";
import { useQuery } from "@tanstack/react-query";
import { Plus } from "lucide-react";
import { apiClient } from "@/api/client";
import type { User, PaginatedResponse } from "@/types";
import { Button } from "@/components/ui/button";
import { UserTable } from "@/components/admin/user-table";
import { UserCreateDialog } from "@/components/admin/user-create-dialog";

export const Route = createFileRoute("/admin/users")({
  component: UsersPage,
});

function UsersPage() {
  const [createOpen, setCreateOpen] = useState(false);

  const { data, isLoading } = useQuery({
    queryKey: ["admin-users"],
    queryFn: () =>
      apiClient<PaginatedResponse<User>>({
        url: "/api/v1/admin/users",
        method: "GET",
        params: { limit: 100, offset: 0 },
      }),
  });

  return (
    <div className="space-y-6 animate-page-in">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-semibold tracking-tight">User Management</h1>
          <p className="text-muted-foreground">
            Manage platform users and roles.
          </p>
        </div>
        <Button onClick={() => setCreateOpen(true)}>
          <Plus className="mr-2 h-4 w-4" />
          Create User
        </Button>
      </div>

      <UserTable data={data?.items ?? []} isLoading={isLoading} />

      <UserCreateDialog open={createOpen} onOpenChange={setCreateOpen} />
    </div>
  );
}
