import { useAuthStore } from "@/stores/auth-store";
import { useAppStore } from "@/stores/app-store";
import { isTokenExpired, refreshAccessToken } from "@/lib/auth";
import type {
  Annotation,
  AnnotationCreate,
  AnnotationUpdate,
  PaginatedResponse,
} from "@/types";

type RequestConfig = {
  url: string;
  method: "GET" | "POST" | "PUT" | "PATCH" | "DELETE";
  headers?: Record<string, string>;
  params?: Record<string, string | number | boolean | undefined>;
  data?: unknown;
  signal?: AbortSignal;
};

async function getValidToken(): Promise<string | null> {
  const { accessToken, refreshToken, setTokens, logout } =
    useAuthStore.getState();
  if (!accessToken) return null;

  if (!isTokenExpired(accessToken)) return accessToken;

  if (!refreshToken) {
    logout();
    return null;
  }

  const result = await refreshAccessToken(refreshToken);
  if (!result) {
    logout();
    return null;
  }

  setTokens(result.access_token, result.refresh_token);
  return result.access_token;
}

export async function apiClient<T>(config: RequestConfig): Promise<T> {
  const token = await getValidToken();
  const matterId = useAppStore.getState().matterId;

  const headers: Record<string, string> = {
    "Content-Type": "application/json",
    ...config.headers,
  };

  if (token) {
    headers["Authorization"] = `Bearer ${token}`;
  }
  if (matterId) {
    headers["X-Matter-ID"] = matterId;
  }

  let url = config.url;
  if (config.params) {
    const searchParams = new URLSearchParams();
    for (const [key, value] of Object.entries(config.params)) {
      if (value !== undefined) {
        searchParams.set(key, String(value));
      }
    }
    const qs = searchParams.toString();
    if (qs) url += `?${qs}`;
  }

  const res = await fetch(url, {
    method: config.method,
    headers,
    body: config.data ? JSON.stringify(config.data) : undefined,
    signal: config.signal,
  });

  if (res.status === 401) {
    useAuthStore.getState().logout();
    window.location.href = "/login";
    throw new Error("Unauthorized");
  }

  if (!res.ok) {
    const error = await res.json().catch(() => ({ detail: res.statusText }));
    throw new Error(error.detail || `Request failed: ${res.status}`);
  }

  if (res.status === 204) return undefined as T;
  return res.json();
}

// --- Annotation API ---

export function fetchAnnotations(
  documentId: string,
  params?: { page_number?: number; offset?: number; limit?: number },
) {
  return apiClient<PaginatedResponse<Annotation>>({
    url: "/api/v1/annotations",
    method: "GET",
    params: { document_id: documentId, ...params },
  });
}

export function createAnnotation(data: AnnotationCreate) {
  return apiClient<Annotation>({
    url: "/api/v1/annotations",
    method: "POST",
    data,
  });
}

export function updateAnnotation(id: string, data: AnnotationUpdate) {
  return apiClient<Annotation>({
    url: `/api/v1/annotations/${id}`,
    method: "PATCH",
    data,
  });
}

export function deleteAnnotation(id: string) {
  return apiClient<void>({
    url: `/api/v1/annotations/${id}`,
    method: "DELETE",
  });
}
