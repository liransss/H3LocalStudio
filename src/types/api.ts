export type Page = "home" | "create" | "spaces" | "projects" | "history" | "models" | "settings";

export type JobState =
  | "queued"
  | "preparing"
  | "running"
  | "post-processing"
  | "upscaling"
  | "completed"
  | "failed"
  | "upscale_failed"
  | "cancelled";

export interface GenerationParameters {
  duration: number;
  aspect_ratio: string;
  generation_resolution: string;
  final_resolution: "original" | "1080p" | "1440p" | "4k";
  upscaler: "original" | "flashvsr" | "seedvr2";
  steps: number;
  turbo: boolean;
  profile: "balanced" | "quality";
  quality: "preview" | "high";
  fps: number;
  audio_enabled: boolean;
}

export interface Generation {
  id: string;
  project_id: string | null;
  prompt: string;
  mode: "t2v" | "i2v" | "r2v";
  seed: number;
  status: JobState;
  progress: number;
  stage: string;
  parameters: GenerationParameters;
  references: ReferenceSnapshot[];
  original_url: string | null;
  output_url: string | null;
  thumbnail_url: string | null;
  variants: VideoVariant[];
  error_message: string | null;
  error_details: string | null;
  output_metadata: {
    width?: number;
    height?: number;
    fps?: number;
    duration?: number;
    audio_present?: boolean;
    audio_codec?: string | null;
    sample_rate?: number | null;
    channels?: number | null;
    workflow_family?: string;
    model_files?: string[];
    derived_prompt?: string;
    reference_map?: Array<Record<string, unknown>>;
    resource_telemetry?: Record<string, number | null>;
  };
  comfy_prompt_id: string | null;
  execution_seconds: number | null;
  model_manifest_version: string | null;
  is_mock: boolean;
  created_at: string;
  started_at: string | null;
  completed_at: string | null;
  updated_at: string;
}

export interface VideoVariant {
  generation_id?: string;
  variant: "original" | "flashvsr" | "seedvr2";
  provider_id: string;
  status: "completed" | "upscaling" | "upscale_failed" | "cancelled";
  url: string | null;
  width: number | null;
  height: number | null;
  fps: number | null;
  duration: number | null;
  audio_present: boolean;
  error_message: string | null;
  metadata: Record<string, unknown> & { execution_seconds?: number };
}

export interface Job {
  id: string;
  generation_id: string | null;
  kind: string;
  status: JobState;
  progress: number;
  stage: string;
  error_message: string | null;
  execution_metadata: Record<string, unknown>;
  created_at: string;
  started_at: string | null;
  completed_at: string | null;
  updated_at: string;
}

export interface Project {
  id: string;
  name: string;
  description: string;
  reference_count: number;
  created_at: string;
  updated_at: string;
}

export interface SystemStatus {
  app: { name: string; version: string; mock_mode: boolean };
  gpu: {
    available: boolean;
    name: string | null;
    vram_total_mb: number | null;
    vram_free_mb: number | null;
    vram_used_mb: number | null;
    cuda: boolean;
  };
  memory: { total_mb: number; available_mb: number };
  disk: { root: string; free_gb: number; total_gb: number };
  comfyui: { running: boolean; version: string | null; compatible: boolean | null; url: string; error: string | null };
  ffmpeg: { available: boolean; path: string | null };
  models: { minimax_h3: "ready" | "missing_models"; minimax_h3_ref2va: "ready" | "missing_models"; flashvsr: "ready" | "missing_models"; seedvr2: "ready" | "missing_models"; manifest_version: string | null };
  inference: { mode: "mock" | "local_gpu"; comfyui_mode: "managed" | "external"; profile: "balanced" | "low_vram" };
  upscaler: {
    available: boolean;
    provider: string | null;
    providers: Array<{ provider_id: "flashvsr" | "seedvr2"; display_name: string; available: boolean; models_ready: boolean; runtime_ready: boolean; reason: string | null; model_family: string }>;
  };
}

export interface LocalSettings {
  data_root: string;
  model_path: string;
  input_path: string;
  output_path: string;
  cache_path: string;
  comfyui_path: string | null;
  comfyui_host: string;
  comfyui_port: number;
  comfyui_mode: "managed" | "external";
  comfyui_profile: "balanced" | "low_vram";
  comfyui_auto_start: boolean;
  ffmpeg_path: string | null;
  default_profile?: "balanced" | "quality";
  default_final_resolution?: "original" | "1080p" | "1440p" | "4k";
  default_upscaler?: "original" | "flashvsr" | "seedvr2";
}

export interface GenerationRequest {
  prompt: string;
  project_id?: string;
  mode: "auto" | "t2v" | "i2v" | "r2v";
  duration: number;
  aspect_ratio: string;
  generation_resolution: string;
  final_resolution: "original" | "1080p" | "1440p" | "4k";
  upscaler: "original" | "flashvsr" | "seedvr2";
  seed: number | null;
  steps: number;
  turbo: boolean;
  profile: "balanced" | "quality";
  quality: "preview" | "high";
  fps: number;
  audio_enabled: boolean;
  references: Array<Pick<ReferenceSelection, "asset_id" | "media_type" | "role" | "notes">>;
}

export type ReferenceRole = "character" | "style" | "motion" | "camera" | "voice" | "environment" | "product" | "general" | "first_frame" | "last_frame";

export interface ReferenceAsset {
  id: string;
  sha256: string;
  filename: string;
  media_type: "image" | "video" | "audio";
  size_bytes: number;
  duration: number | null;
  width: number | null;
  height: number | null;
  audio_present: boolean;
  content_url: string;
  preview_url: string | null;
  metadata: Record<string, unknown>;
}

export interface ReferenceSelection extends ReferenceAsset {
  asset_id: string;
  role: ReferenceRole;
  notes: string;
}

export interface ReferenceSnapshot extends ReferenceSelection {
  order: number;
}

export interface ModelComponent {
  id: string;
  filename: string;
  model_dir: string;
  path: string;
  status: "missing" | "partial" | "invalid" | "installed" | "verified" | "downloading" | "verifying";
  size: number;
  bytes_present: number;
  sha256: string;
  source_repo: string;
  source_revision: string;
  compatible_families?: Array<"fl2va" | "ref2va">;
  shared?: boolean;
}

export interface ModelOperation {
  id: string;
  kind: "install" | "repair" | "verify";
  family: "fl2va" | "ref2va" | "flashvsr" | "seedvr2";
  status: "queued" | "running" | "cancelling" | "completed" | "failed" | "cancelled";
  bytes_done: number;
  total_bytes: number;
  current_file: string | null;
  message: string;
  error: string | null;
  created_at: string;
}

export interface ModelFamily {
  id: "fl2va" | "ref2va" | "flashvsr" | "seedvr2";
  name: string;
  status: "incomplete" | "installed" | "verified";
  installed: boolean;
  ready: boolean;
  verified: boolean;
  total_size: number;
  manifest_version: string;
  components: ModelComponent[];
  target_root: string;
  operation: ModelOperation | null;
  category?: "upscaler";
  runtime?: { ready: boolean; kind: string; version: string | null; path: string; dependency?: string | null; reason: string | null };
}
