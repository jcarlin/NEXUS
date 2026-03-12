import { createFileRoute, useNavigate } from "@tanstack/react-router";
import { useForm } from "react-hook-form";
import { z } from "zod";
import { zodResolver } from "@hookform/resolvers/zod";
import { useEffect, useState } from "react";
import { Eye, EyeOff, ExternalLink } from "lucide-react";
import { useAuthStore } from "@/stores/auth-store";
import { apiClient } from "@/api/client";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Alert, AlertDescription } from "@/components/ui/alert";
import { Separator } from "@/components/ui/separator";
import type { TokenResponse, User } from "@/types";

interface OIDCProviderInfo {
  enabled: boolean;
  provider_name: string;
  authorize_url: string;
}

interface SAMLProviderInfo {
  enabled: boolean;
  provider_name: string;
  login_url: string;
}

export const Route = createFileRoute("/login")({
  component: LoginPage,
});

const loginSchema = z.object({
  email: z.string().email("Invalid email address"),
  password: z.string().min(1, "Password is required"),
});

type LoginForm = z.infer<typeof loginSchema>;

function LoginPage() {
  const login = useAuthStore((s) => s.login);
  const navigate = useNavigate();
  const [error, setError] = useState<string | null>(null);
  const [showPassword, setShowPassword] = useState(false);
  const [ssoInfo, setSsoInfo] = useState<OIDCProviderInfo | null>(null);
  const [samlInfo, setSamlInfo] = useState<SAMLProviderInfo | null>(null);

  const {
    register,
    handleSubmit,
    formState: { errors, isSubmitting },
  } = useForm<LoginForm>({
    resolver: zodResolver(loginSchema),
  });

  useEffect(() => {
    fetch("/api/v1/auth/oidc/info")
      .then((res) => (res.ok ? res.json() : null))
      .then((data: OIDCProviderInfo | null) => {
        if (data?.enabled) setSsoInfo(data);
      })
      .catch(() => {
        /* SSO not available */
      });

    fetch("/api/v1/auth/saml/info")
      .then((res) => (res.ok ? res.json() : null))
      .then((data: SAMLProviderInfo | null) => {
        if (data?.enabled) setSamlInfo(data);
      })
      .catch(() => {
        /* SAML SSO not available */
      });
  }, []);

  async function onSubmit(data: LoginForm) {
    setError(null);
    try {
      const tokens = await apiClient<TokenResponse>({
        url: "/api/v1/auth/login",
        method: "POST",
        data,
      });

      // Temporarily set tokens so /auth/me call works
      useAuthStore.getState().setTokens(tokens.access_token, tokens.refresh_token);

      const user = await apiClient<User>({
        url: "/api/v1/auth/me",
        method: "GET",
      });

      login(tokens.access_token, tokens.refresh_token, user);
      navigate({ to: "/" });
    } catch (err) {
      setError(err instanceof Error ? err.message : "Login failed");
      useAuthStore.getState().logout();
    }
  }

  return (
    <div className="flex min-h-screen items-center justify-center bg-background">
      <Card className="w-full max-w-[400px] shadow-lg shadow-primary/5">
        <CardHeader className="space-y-1 text-center pb-8">
          <CardTitle className="text-3xl font-bold tracking-widest text-amber">
            NEXUS
          </CardTitle>
          <div className="mx-auto h-px w-12 bg-amber/40" />
          <CardDescription className="pt-2">
            Legal Document Intelligence Platform
          </CardDescription>
        </CardHeader>
        <CardContent>
          <form onSubmit={handleSubmit(onSubmit)} className="space-y-4">
            {error && (
              <Alert variant="destructive">
                <AlertDescription>{error}</AlertDescription>
              </Alert>
            )}

            <div className="space-y-2">
              <Label htmlFor="email">Email</Label>
              <Input
                id="email"
                type="email"
                placeholder="you@example.com"
                autoComplete="email"
                {...register("email")}
              />
              {errors.email && (
                <p className="text-xs text-destructive">{errors.email.message}</p>
              )}
            </div>

            <div className="space-y-2">
              <Label htmlFor="password">Password</Label>
              <div className="relative">
                <Input
                  id="password"
                  type={showPassword ? "text" : "password"}
                  autoComplete="current-password"
                  className="pr-10"
                  {...register("password")}
                />
                <button
                  type="button"
                  className="absolute right-3 top-1/2 -translate-y-1/2 text-muted-foreground hover:text-foreground"
                  onClick={() => setShowPassword((prev) => !prev)}
                  tabIndex={-1}
                  aria-label={showPassword ? "Hide password" : "Show password"}
                >
                  {showPassword ? <EyeOff className="h-4 w-4" /> : <Eye className="h-4 w-4" />}
                </button>
              </div>
              {errors.password && (
                <p className="text-xs text-destructive">{errors.password.message}</p>
              )}
            </div>

            <Button type="submit" className="w-full" disabled={isSubmitting}>
              {isSubmitting ? "Signing in..." : "Sign in"}
            </Button>
          </form>

          {(ssoInfo || samlInfo) && (
            <>
              <div className="relative my-6">
                <Separator />
                <span className="absolute left-1/2 top-1/2 -translate-x-1/2 -translate-y-1/2 bg-card px-2 text-xs text-muted-foreground">
                  or
                </span>
              </div>
              {ssoInfo && (
                <Button
                  variant="outline"
                  className="w-full"
                  asChild
                >
                  <a href={ssoInfo.authorize_url}>
                    <ExternalLink className="mr-2 h-4 w-4" />
                    Sign in with {ssoInfo.provider_name}
                  </a>
                </Button>
              )}
              {samlInfo && (
                <Button
                  variant="outline"
                  className={ssoInfo ? "mt-2 w-full" : "w-full"}
                  asChild
                >
                  <a href={samlInfo.login_url}>
                    <ExternalLink className="mr-2 h-4 w-4" />
                    Sign in with {samlInfo.provider_name}
                  </a>
                </Button>
              )}
            </>
          )}
        </CardContent>
      </Card>
    </div>
  );
}
