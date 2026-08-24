import type {
  Generation,
  GenerationRequest,
  Job,
  LocalSettings,
  ModelFamily,
  ModelOperation,
  Project,
  ReferenceAsset,
  SystemStatus,
} from "../types/api";

const explicitBase = import.meta.env.VITE_API_URL as string | undefined;
export const API_ROOT = explicitBase ?? (location.protocol.startsWith("http") ? "/api" : "http://127.0.0.1:7331/api");

export function mediaUrl(path: string | null): string | null {
  if (!path) return null;
  if (path.startsWith("http")) return path;
  const root = API_ROOT.endsWith("/api") ? API_ROOT.slice(0, -4) : "";
  return `${root}${path}`;
}

export class ApiError extends Error {
  constructor(message: string, public readonly status: number, public readonly detail?: unknown) {
    super(message);
  }
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const headers = new Headers(init?.headers);
  if (!(init?.body instanceof FormData)) headers.set("Content-Type", "application/json");
  const response = await fetch(`${API_ROOT}${path}`, {
    ...init,
    headers,
  });
  if (!response.ok) {
    let message = `Local API request failed (${response.status})`;
    let detail: unknown;
    try {
      const payload = (await response.json()) as {
        detail?: string | { message?: string } | Array<{ msg: string }>;
      };
      detail = payload.detail;
      if (typeof payload.detail === "string") message = payload.detail;
      else if (Array.isArray(payload.detail)) message = payload.detail.map((item) => item.msg).join(" · ");
      else if (payload.detail?.message) message = payload.detail.message;
    } catch {
      // Keep the status-based fallback.
    }
    throw new ApiError(message, response.status, detail);
  }
  if (response.status === 204) return undefined as T;
  return response.json() as Promise<T>;
}

export const api = {
  health: () => request<{ status: string; version: string; mock_mode: boolean }>("/health"),
  systemStatus: () => request<SystemStatus>("/system/status"),
  projects: () => request<Project[]>("/projects"),
  createProject: (name: string, description = "") =>
    request<Project>("/projects", { method: "POST", body: JSON.stringify({ name, description }) }),
  referenceAssets: (projectId: string) =>
    request<ReferenceAsset[]>(`/projects/${projectId}/reference-assets`),
  uploadReference: (projectId: string, file: File) => {
    const body = new FormData();
    body.append("upload", file);
    return request<ReferenceAsset>(`/projects/${projectId}/reference-assets`, { method: "POST", body });
  },
  generations: (search = "") =>
    request<Generation[]>(`/generations${search ? `?search=${encodeURIComponent(search)}` : ""}`),
  generation: (id: string) => request<Generation>(`/generations/${id}`),
  createGeneration: (payload: GenerationRequest) =>
    request<{ generation: Generation; job: Job }>("/generations", { method: "POST", body: JSON.stringify(payload) }),
  deleteGeneration: (id: string) => request<void>(`/generations/${id}`, { method: "DELETE" }),
  job: (id: string) => request<Job>(`/jobs/${id}`),
  cancelJob: (id: string) => request<Job>(`/jobs/${id}/cancel`, { method: "POST" }),
  upscale: (id: string, provider: "flashvsr" | "seedvr2") =>
    request<Job>(`/generations/${id}/upscale`, { method: "POST", body: JSON.stringify({ resolution: "1080p", provider }) }),
  openGeneration: (id: string, target: "file" | "folder", variant: "original" | "flashvsr" | "seedvr2" = "original") =>
    request<{ opened: boolean }>(`/generations/${id}/open`, { method: "POST", body: JSON.stringify({ target, variant }) }),
  settings: () => request<LocalSettings>("/settings"),
  saveSettings: (settings: Partial<LocalSettings>) =>
    request<{ saved: boolean; restart_required: boolean }>("/settings", { method: "PATCH", body: JSON.stringify(settings) }),
  models: () => request<ModelFamily[]>("/models"),
  installModels: (family: ModelFamily["id"], repair = false) =>
    request<ModelOperation>("/models/install", {
      method: "POST",
      body: JSON.stringify({ family, repair, confirmed: true }),
    }),
  verifyModels: (family: ModelFamily["id"]) =>
    request<ModelOperation>("/models/verify", { method: "POST", body: JSON.stringify({ family }) }),
  modelOperation: (id: string) => request<ModelOperation>(`/models/operations/${id}`),
  cancelModelOperation: (id: string) =>
    request<ModelOperation>(`/models/operations/${id}/cancel`, { method: "POST" }),
  openModels: () => request<{ opened: boolean }>("/models/open", { method: "POST" }),
  startComfyUI: () => request<SystemStatus["comfyui"]>("/comfyui/start", { method: "POST" }),
  stopComfyUI: () => request<{ stopped: boolean }>("/comfyui/stop", { method: "POST" }),
  updateComfyUI: () => request<{ updated: boolean; message: string }>("/comfyui/update", { method: "POST" }),
};

export function jobWebSocketUrl(jobId: string): string {
  const httpRoot = API_ROOT.startsWith("http") ? API_ROOT : `${location.origin}${API_ROOT}`;
  return `${httpRoot.replace(/^http/, "ws")}/jobs/${jobId}/ws`;
}
