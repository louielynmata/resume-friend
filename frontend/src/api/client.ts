import type { ApiErrorPayload, ExtractJobMetaResult, GeneratePayload, GenerateResult, ModelFilesStatus } from "../types";

export class ApiError extends Error {
  status: number;
  payload: ApiErrorPayload;

  constructor(status: number, payload: ApiErrorPayload, fallbackMessage: string) {
    super(payload.message || payload.detail || fallbackMessage);
    this.name = "ApiError";
    this.status = status;
    this.payload = payload;
  }
}

async function request<T>(path: string, options?: RequestInit): Promise<T> {
  const res = await fetch(path, {
    headers: { "Content-Type": "application/json" },
    ...options,
  });
  if (!res.ok) {
    const body = await res.json().catch(() => ({ detail: res.statusText }));
    const payload: ApiErrorPayload =
      typeof body?.detail === "object" && body.detail !== null
        ? body.detail
        : { status_code: res.status, detail: body?.detail ?? res.statusText };
    throw new ApiError(res.status, payload, `HTTP ${res.status}`);
  }
  return res.json() as Promise<T>;
}

export const api = {
  health: () => request<{ status: string; owner: string }>("/api/health"),

  scrapeJob: (url: string) =>
    request<{ text: string; source_url: string }>("/api/scrape-job", {
      method: "POST",
      body: JSON.stringify({ url }),
    }),

  extractJobMeta: (text: string) =>
    request<ExtractJobMetaResult>("/api/extract-job-meta", {
      method: "POST",
      body: JSON.stringify({ text }),
    }),

  generate: (payload: GeneratePayload) =>
    request<GenerateResult>("/api/generate", {
      method: "POST",
      body: JSON.stringify(payload),
    }),

  modelFiles: () => request<ModelFilesStatus>("/api/model-files"),

  notionStatus: () => request<{ configured: boolean }>("/api/notion/status"),
};
