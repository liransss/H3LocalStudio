import { Clock3, MoreHorizontal, Play } from "lucide-react";
import { mediaUrl } from "../services/api";
import type { Generation } from "../types/api";

interface VideoCardProps {
  generation: Generation;
  onOpen: (generation: Generation) => void;
}

export function VideoCard({ generation, onOpen }: VideoCardProps) {
  const thumbnail = mediaUrl(generation.thumbnail_url);
  const readyVariants = new Set(
    generation.variants
      .filter((variant) => variant.status === "completed")
      .map((variant) => variant.variant),
  );
  return (
    <article className="video-card">
      <button className="video-card-open" aria-label={`Open ${generation.prompt}`} onClick={() => onOpen(generation)} />
      <div
        className="video-thumb"
        style={thumbnail ? { backgroundImage: `url(${thumbnail})` } : undefined}
      >
        {!thumbnail && (
          <div className="thumb-placeholder">
            <span>H3</span>
          </div>
        )}
        <span className="video-play" aria-hidden="true">
          <Play size={18} fill="currentColor" />
        </span>
        <span className={`card-status status-${generation.status}`}>
          {generation.is_mock ? "MOCK · " : ""}
          {generation.status}
        </span>
        <span className="mode-label">
          {generation.mode.toUpperCase()}
          {generation.references.length
            ? ` · ${generation.references.length} REF`
            : ""}
        </span>
        <span className="duration-label">
          {generation.parameters.duration}s
        </span>
      </div>
      <div className="video-card-body">
        <p>{generation.prompt}</p>
        <div className="variant-badges">
          <span>Original</span>
          {generation.mode === "r2v" ? <span>Ref2VA</span> : null}
          {readyVariants.has("flashvsr") ? <span>Fast 1080p</span> : null}
          {readyVariants.has("seedvr2") ? <span>Best 1080p</span> : null}
        </div>
        <div>
          <span>
            <Clock3 size={13} />{" "}
            {new Date(generation.created_at).toLocaleDateString()}
          </span>
          <MoreHorizontal size={17} />
        </div>
      </div>
    </article>
  );
}
