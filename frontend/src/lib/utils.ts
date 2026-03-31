import { type ClassValue, clsx } from "clsx";
import { twMerge } from "tailwind-merge";

export function cn(...inputs: ClassValue[]) {
  return twMerge(clsx(inputs));
}

export function formatDate(date: string | Date): string {
  return new Date(date).toLocaleDateString("en-US", {
    month: "short",
    day: "numeric",
    year: "numeric",
  });
}

export function formatDateTime(date: string | Date): string {
  return new Date(date).toLocaleString("en-US", {
    month: "short",
    day: "numeric",
    year: "numeric",
    hour: "numeric",
    minute: "2-digit",
  });
}

export function formatNumber(n: number): string {
  return n.toLocaleString();
}

export function formatPercent(n: number, decimals = 0): string {
  return `${n.toFixed(decimals)}%`;
}

export function truncate(str: string, maxLength: number): string {
  if (str.length <= maxLength) return str;
  return str.slice(0, maxLength - 1) + "\u2026";
}

export function formatFileSize(bytes: number): string {
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(0)} KB`;
  if (bytes < 1024 * 1024 * 1024) return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
  return `${(bytes / (1024 * 1024 * 1024)).toFixed(2)} GB`;
}

export type DocumentViewType = "pdf" | "text" | "image" | "email" | "unknown";

const TEXT_EXTENSIONS = new Set(["txt", "csv", "md", "log", "json", "xml", "html", "htm", "yaml", "yml", "tsv"]);
const IMAGE_EXTENSIONS = new Set(["png", "jpg", "jpeg", "gif", "webp", "tiff", "tif", "bmp", "svg"]);

export function detectDocumentType(
  type: string | null | undefined,
  filename: string,
): DocumentViewType {
  const t = type?.toLowerCase()?.trim();

  if (t === "pdf") return "pdf";
  if (t === "text" || t === "txt" || t === "csv" || t === "markdown" || t === "html" || t === "xml" || t === "json" || t === "log") return "text";
  if (t === "image" || t === "png" || t === "jpg" || t === "jpeg" || t === "gif" || t === "webp" || t === "tiff") return "image";
  if (t === "email" || t === "eml") return "email";

  // Fallback to filename extension
  const ext = filename.split(".").pop()?.toLowerCase();
  if (!ext) return "unknown";

  if (ext === "pdf") return "pdf";
  if (TEXT_EXTENSIONS.has(ext)) return "text";
  if (IMAGE_EXTENSIONS.has(ext)) return "image";
  if (ext === "eml") return "email";

  return "unknown";
}
