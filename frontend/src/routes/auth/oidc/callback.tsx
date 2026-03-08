import { createFileRoute, useNavigate } from "@tanstack/react-router";
import { useEffect, useState } from "react";
import { useAuthStore } from "@/stores/auth-store";
import { apiClient } from "@/api/client";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Alert, AlertDescription } from "@/components/ui/alert";
import type { User } from "@/types";

interface OIDCCallbackResponse {
  access_token: string;
  refresh_token: string;
  token_type: string;
  expires_in: number;
  is_new_user: boolean;
}

export const Route = createFileRoute("/auth/oidc/callback")({
  component: OIDCCallbackPage,
});

function OIDCCallbackPage() {
  const loginStore = useAuthStore((s) => s.login);
  const navigate = useNavigate();
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    const params = new URLSearchParams(window.location.search);
    const code = params.get("code");
    const state = params.get("state");

    if (!code) {
      setError("Missing authorization code from SSO provider");
      return;
    }

    async function handleCallback() {
      try {
        const tokens = await apiClient<OIDCCallbackResponse>({
          url: "/api/v1/auth/oidc/callback",
          method: "GET",
          params: { code: code!, state: state ?? "" },
        });

        // Set tokens so /auth/me call works
        useAuthStore.getState().setTokens(tokens.access_token, tokens.refresh_token);

        const user = await apiClient<User>({
          url: "/api/v1/auth/me",
          method: "GET",
        });

        loginStore(tokens.access_token, tokens.refresh_token, user);
        navigate({ to: "/" });
      } catch (err) {
        setError(err instanceof Error ? err.message : "SSO authentication failed");
        useAuthStore.getState().logout();
      }
    }

    handleCallback();
  }, [loginStore, navigate]);

  return (
    <div className="flex min-h-screen items-center justify-center bg-background">
      <Card className="w-full max-w-[400px] shadow-lg shadow-primary/5">
        <CardHeader className="space-y-1 text-center pb-8">
          <CardTitle className="text-3xl font-bold tracking-widest text-amber">
            NEXUS
          </CardTitle>
          <div className="mx-auto h-px w-12 bg-amber/40" />
          <CardDescription className="pt-2">
            {error ? "Authentication failed" : "Completing SSO sign-in..."}
          </CardDescription>
        </CardHeader>
        <CardContent>
          {error ? (
            <Alert variant="destructive">
              <AlertDescription>{error}</AlertDescription>
            </Alert>
          ) : (
            <div className="flex justify-center py-8">
              <div className="h-8 w-8 animate-spin rounded-full border-4 border-primary border-t-transparent" />
            </div>
          )}
        </CardContent>
      </Card>
    </div>
  );
}
