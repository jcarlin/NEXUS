import { useNavigate } from "@tanstack/react-router";
import { useEffect } from "react";
import { useAuthStore } from "@/stores/auth-store";
import { Skeleton } from "@/components/ui/skeleton";

function AppShellSkeleton() {
  return (
    <div className="flex h-screen overflow-hidden">
      {/* Sidebar skeleton */}
      <div className="hidden xl:flex w-56 flex-col border-r bg-background p-4 gap-4">
        <Skeleton className="h-8 w-32" />
        <div className="space-y-2 mt-4">
          {Array.from({ length: 6 }).map((_, i) => (
            <Skeleton key={i} className="h-8 w-full" />
          ))}
        </div>
      </div>
      {/* Main content skeleton */}
      <div className="flex flex-1 flex-col overflow-hidden">
        {/* Header skeleton */}
        <div className="flex h-14 items-center justify-between border-b bg-background px-4">
          <Skeleton className="h-8 w-64" />
          <Skeleton className="h-8 w-8 rounded-full" />
        </div>
        {/* Page skeleton */}
        <div className="flex-1 p-6 space-y-4">
          <Skeleton className="h-8 w-48" />
          <Skeleton className="h-4 w-72" />
          <div className="grid gap-4 md:grid-cols-2 lg:grid-cols-4 mt-6">
            {Array.from({ length: 4 }).map((_, i) => (
              <Skeleton key={i} className="h-24 w-full rounded-lg" />
            ))}
          </div>
        </div>
      </div>
    </div>
  );
}

export function AuthGuard({ children }: { children: React.ReactNode }) {
  const isAuthenticated = useAuthStore((s) => s.isAuthenticated);
  const navigate = useNavigate();

  useEffect(() => {
    if (!isAuthenticated) {
      navigate({ to: "/login" });
    }
  }, [isAuthenticated, navigate]);

  if (!isAuthenticated) return <AppShellSkeleton />;
  return <>{children}</>;
}
