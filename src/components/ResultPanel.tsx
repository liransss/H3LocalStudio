import {
  Copy,
  ExternalLink,
  FileImage,
  Film,
  FolderOpen,
  Gauge,
  Maximize2,
  Music2,
  RotateCcw,
  Sparkles,
  Trash2,
} from "lucide-react";
import { useEffect, useMemo, useRef, useState } from "react";
import { mediaUrl } from "../services/api";
import type { Generation, SystemStatus } from "../types/api";
import { Button } from "./ui/Button";
import { VideoComparison } from "./VideoComparison";

type VariantId = "original" | "flashvsr" | "seedvr2";

interface ResultPanelProps {
  generation: Generation;
  status: SystemStatus | null;
  onClose: () => void;
  onReuse: (generation: Generation) => void;
  onUpscale: (generation: Generation, provider: "flashvsr" | "seedvr2") => void;
  onDelete: (generation: Generation) => void;
  onOpen: (
    generation: Generation,
    target: "file" | "folder",
    variant: VariantId,
  ) => void;
  onModels: () => void;
}

const LABELS: Record<VariantId, { title: string; short: string }> = {
  original: { title: "Original H3", short: "Original" },
  flashvsr: { title: "Fast 1080p · FlashVSR", short: "Fast 1080p" },
  seedvr2: { title: "Best Quality 1080p · SeedVR2", short: "Best 1080p" },
};

export function ResultPanel({
  generation,
  status,
  onClose,
  onReuse,
  onUpscale,
  onDelete,
  onOpen,
  onModels,
}: ResultPanelProps) {
  const variants = useMemo(
    () => new Map(generation.variants.map((item) => [item.variant, item])),
    [generation.variants],
  );
  const initialVariant =
    generation.parameters.upscaler !== "original" &&
    variants.get(generation.parameters.upscaler)?.url
      ? generation.parameters.upscaler
      : "original";
  const [selected, setSelected] = useState<VariantId>(initialVariant);
  const [compare, setCompare] = useState(false);
  const [copyState, setCopyState] = useState("Copy");
  const dialogRef = useRef<HTMLElement>(null);
  const closeRef = useRef(onClose);
  closeRef.current = onClose;
  useEffect(() => {
    const previousFocus = document.activeElement as HTMLElement | null;
    const dialog = dialogRef.current;
    dialog?.querySelector<HTMLButtonElement>("button")?.focus();
    const onKeyDown = (event: KeyboardEvent) => {
      if (event.key === "Escape") closeRef.current();
      if (event.key !== "Tab" || !dialog) return;
      const focusable = Array.from(dialog.querySelectorAll<HTMLElement>('button:not(:disabled), a[href], input, video[controls], [tabindex="0"]')).filter((item) => item.getClientRects().length);
      const first = focusable[0];
      const last = focusable[focusable.length - 1];
      if (event.shiftKey && document.activeElement === first) { event.preventDefault(); last?.focus(); }
      else if (!event.shiftKey && document.activeElement === last) { event.preventDefault(); first?.focus(); }
    };
    document.addEventListener("keydown", onKeyDown);
    return () => { document.removeEventListener("keydown", onKeyDown); previousFocus?.focus(); };
  }, []);
  const selectedVariant = variants.get(selected) ?? variants.get("original");
  const source = mediaUrl(selectedVariant?.url ?? generation.original_url);
  const providerStatus = (provider: "flashvsr" | "seedvr2") =>
    status?.upscaler.providers.find((item) => item.provider_id === provider);
  const dimensions =
    selectedVariant?.width && selectedVariant.height
      ? `${selectedVariant.width} × ${selectedVariant.height}`
      : generation.parameters.generation_resolution.replace("x", " × ");
  const selectedMetadata = selectedVariant?.metadata ?? {};
  const originalSource = mediaUrl(variants.get("original")?.url ?? generation.original_url);
  const comparisonVariant = selected !== "original" ? selected : (["seedvr2", "flashvsr"] as const).find((variant) => variants.get(variant)?.status === "completed" && variants.get(variant)?.url);
  const comparisonSource = comparisonVariant ? mediaUrl(variants.get(comparisonVariant)?.url ?? null) : null;
  const copyPrompt = async () => {
    try { await navigator.clipboard.writeText(generation.prompt); setCopyState("Copied"); }
    catch { setCopyState("Could not copy"); }
  };
  const telemetry = generation.output_metadata.resource_telemetry as
    | Record<string, number | null>
    | undefined;

  const chooseVariant = (variant: VariantId) => {
    const existing = variants.get(variant);
    if (variant === "original" || existing?.url) {
      setSelected(variant);
      return;
    }
    const provider = variant as "flashvsr" | "seedvr2";
    if (!providerStatus(provider)?.available) onModels();
    else onUpscale(generation, provider);
  };

  return (
    <div
      className="result-backdrop"
      onMouseDown={(event) => event.target === event.currentTarget && onClose()}
    >
      <section
        className="result-panel"
        ref={dialogRef}
        role="dialog"
        aria-modal="true"
        aria-label="Generation result"
      >
        <div className="result-head">
          <div>
            <span className="eyebrow">Generation result</span>
            <h2>
              {generation.status === "upscaling"
                ? "Creating your 1080p variant"
                : "Your video is ready"}
            </h2>
          </div>
          <button onClick={onClose} aria-label="Close result">
            ×
          </button>
        </div>
        <div
          className="variant-selector"
          role="group"
          aria-label="Video version"
        >
          {(Object.keys(LABELS) as VariantId[]).map((variant) => {
            const item = variants.get(variant);
            const provider =
              variant === "original" ? null : providerStatus(variant);
            const state =
              item?.status === "completed"
                ? "ready"
                : item?.status === "upscaling"
                  ? "working"
                  : provider?.available
                    ? "available"
                    : "install";
            return (
              <button
                key={variant}
                aria-pressed={selected === variant}
                className={selected === variant ? "selected" : ""}
                onClick={() => chooseVariant(variant)}
              >
                <span>{LABELS[variant].short}</span>
                <small>{state}</small>
              </button>
            );
          })}
        </div>
        {comparisonSource && originalSource ? <div className="compare-toolbar"><button aria-pressed={compare} onClick={() => setCompare((value) => !value)}>{compare ? "Single video" : "Compare original / upscaled"}</button><span>{compare ? "Drag the divider. Playback stays synchronized." : "Inspect detail with synchronized playback."}</span></div> : null}
        <div className="result-grid">
          <div className="result-player">
            {compare && comparisonSource && originalSource ? <VideoComparison key={comparisonSource} original={originalSource} upscaled={comparisonSource} /> : source ? (
              <video key={source} src={source} controls loop autoPlay />
            ) : (
              <div className="empty-player">
                <Sparkles size={30} />
                <span>Video is not available</span>
              </div>
            )}
            <span className="resolution-chip">
              {LABELS[selected].title} · {dimensions}
            </span>
            <Maximize2 className="player-corner" size={17} />
          </div>
          <aside className="result-details">
            <div className="detail-prompt">
              <span>Prompt</span>
              <p tabIndex={0}>{generation.prompt}</p>
              <button onClick={copyPrompt}>
                <Copy size={14} /> <span role="status">{copyState}</span>
              </button>
            </div>
            {generation.references.length ? (
              <details className="references-used" open>
                <summary>
                  References used <span>{generation.references.length}</span>
                </summary>
                <div>
                  {generation.references.map((reference) => {
                    const preview = mediaUrl(
                      reference.preview_url ??
                        (reference.media_type === "image"
                          ? reference.content_url
                          : null),
                    );
                    const Icon =
                      reference.media_type === "image"
                        ? FileImage
                        : reference.media_type === "video"
                          ? Film
                          : Music2;
                    return (
                      <a
                        key={`${reference.asset_id}-${reference.order}`}
                        href={mediaUrl(reference.content_url) ?? undefined}
                        target="_blank"
                        rel="noreferrer"
                      >
                        <span className="used-reference-preview">
                          {preview ? (
                            <img src={preview} alt="" />
                          ) : (
                            <Icon size={15} />
                          )}
                        </span>
                        <span>
                          <strong>
                            {reference.order + 1}. {reference.filename}
                          </strong>
                          <small>
                            {reference.role.replace("_", " ")}
                            {reference.duration
                              ? ` · ${reference.duration.toFixed(1)} sec`
                              : ""}
                          </small>
                        </span>
                      </a>
                    );
                  })}
                </div>
              </details>
            ) : null}
            <dl>
              <div>
                <dt>Version</dt>
                <dd>{LABELS[selected].short}</dd>
              </div>
              <div>
                <dt>Mode</dt>
                <dd>{generation.mode.toUpperCase()}</dd>
              </div>
              <div>
                <dt>Seed</dt>
                <dd>{generation.seed}</dd>
              </div>
              <div>
                <dt>Dimensions</dt>
                <dd>{dimensions}</dd>
              </div>
              <div>
                <dt>FPS</dt>
                <dd>
                  {selectedVariant?.fps ?? generation.output_metadata.fps ?? 24}
                </dd>
              </div>
              <div>
                <dt>Duration</dt>
                <dd>
                  {(
                    selectedVariant?.duration ??
                    generation.output_metadata.duration ??
                    generation.parameters.duration
                  ).toFixed(2)}{" "}
                  sec
                </dd>
              </div>
              <div>
                <dt>Audio</dt>
                <dd>
                  {(selectedVariant?.audio_present ??
                  generation.output_metadata.audio_present)
                    ? "Original AAC preserved"
                    : "Not present"}
                </dd>
              </div>
              {typeof selectedMetadata.execution_seconds === "number" ? (
                <div>
                  <dt>Upscale time</dt>
                  <dd>{selectedMetadata.execution_seconds.toFixed(1)} sec</dd>
                </div>
              ) : null}
              {selected === "original" &&
              generation.execution_seconds != null ? (
                <div>
                  <dt>H3 execution</dt>
                  <dd>{generation.execution_seconds.toFixed(1)} sec</dd>
                </div>
              ) : null}
              {selected === "original" &&
              telemetry?.peak_vram_used_gb != null ? (
                <div>
                  <dt>Peak VRAM</dt>
                  <dd>{telemetry.peak_vram_used_gb.toFixed(2)} GB</dd>
                </div>
              ) : null}
              {selected === "original" &&
              telemetry?.peak_system_ram_used_gb != null ? (
                <div>
                  <dt>Peak RAM</dt>
                  <dd>{telemetry.peak_system_ram_used_gb.toFixed(2)} GB</dd>
                </div>
              ) : null}
              <div>
                <dt>Date</dt>
                <dd>{new Date(generation.created_at).toLocaleString()}</dd>
              </div>
            </dl>
            {generation.status === "upscale_failed" ? (
              <div className="upscale-error">
                Upscale failed: {generation.error_message}. The original remains
                available.
              </div>
            ) : null}
            {generation.is_mock ? (
              <div className="mock-note">
                Mock Mode uses a local FFmpeg preview. AI upscaler actions still
                require installed local models.
              </div>
            ) : null}
          </aside>
        </div>
        <div className="result-actions">
          <Button
            icon={<ExternalLink size={16} />}
            onClick={() => onOpen(generation, "file", selected)}
          >
            Open file
          </Button>
          <Button
            icon={<FolderOpen size={16} />}
            onClick={() => onOpen(generation, "folder", selected)}
          >
            Open folder
          </Button>
          <Button
            icon={<RotateCcw size={16} />}
            onClick={() => onReuse(generation)}
          >
            Reuse settings
          </Button>
          {selected === "original" ? (
            <Button
              variant="primary"
              icon={<Gauge size={16} />}
              onClick={() => chooseVariant("flashvsr")}
            >
              {providerStatus("flashvsr")?.available
                ? "Fast 1080p"
                : "Install Fast"}
            </Button>
          ) : null}
          {selected === "original" ? (
            <Button
              variant="primary"
              icon={<Sparkles size={16} />}
              onClick={() => chooseVariant("seedvr2")}
            >
              {providerStatus("seedvr2")?.available
                ? "Best 1080p"
                : "Install Best"}
            </Button>
          ) : null}
          <Button
            variant="danger"
            className="result-delete"
            icon={<Trash2 size={16} />}
            onClick={() => onDelete(generation)}
          >
            Delete
          </Button>
        </div>
      </section>
    </div>
  );
}
