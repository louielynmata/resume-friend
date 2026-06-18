import type { GeneratePayload, GenerateResult, ModelFilesStatus } from "../types";

async function request<T>(path: string, options?: RequestInit): Promise<T> {
  const res = await fetch(path, {
    headers: { "Content-Type": "application/json" },
    ...options,
  });
  if (!res.ok) {
    const body = await res.json().catch(() => ({ detail: res.statusText }));
    throw new Error(body.detail ?? `HTTP ${res.status}`);
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

  generate: (payload: GeneratePayload) =>
    request<GenerateResult>("/api/generate", {
      method: "POST",
      body: JSON.stringify(payload),
    }),

  modelFiles: () => request<ModelFilesStatus>("/api/model-files"),

  notionStatus: () => request<{ configured: boolean }>("/api/notion/status"),
};
