interface JwtPayload {
  sub: string;
  role: string;
  type: string;
  exp: number;
}

export function parseJwt(token: string): JwtPayload | null {
  try {
    const base64Url = token.split(".")[1];
    if (!base64Url) return null;
    const base64 = base64Url.replace(/-/g, "+").replace(/_/g, "/");
    const payload = JSON.parse(atob(base64));
    return payload as JwtPayload;
  } catch {
    return null;
  }
}

export function isTokenExpired(token: string, bufferSeconds = 30): boolean {
  const payload = parseJwt(token);
  if (!payload) return true;
  const now = Math.floor(Date.now() / 1000);
  return payload.exp < now + bufferSeconds;
}

export async function refreshAccessToken(refreshToken: string): Promise<{
  access_token: string;
  refresh_token: string;
} | null> {
  try {
    const res = await fetch("/api/v1/auth/refresh", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ refresh_token: refreshToken }),
    });
    if (!res.ok) return null;
    return await res.json();
  } catch {
    return null;
  }
}
