import { ArrowDown, ArrowUp, FileImage, Film, GripVertical, Music2, Plus, Upload, X } from "lucide-react";
import { useEffect, useRef, useState } from "react";
import { api, mediaUrl } from "../services/api";
import type { ReferenceAsset, ReferenceRole, ReferenceSelection } from "../types/api";

const LIMITS = { image: 9, video: 3, audio: 3 } as const;
const EXTENSIONS = {
  image: [".png", ".jpg", ".jpeg", ".webp"],
  video: [".mp4", ".mov", ".webm", ".mkv"],
  audio: [".wav", ".mp3", ".m4a", ".flac"],
} as const;
const ROLE_OPTIONS: Array<[ReferenceRole, string]> = [
  ["general", "General"], ["character", "Character"], ["style", "Style"], ["motion", "Motion"],
  ["camera", "Camera"], ["voice", "Voice"], ["environment", "Environment"], ["product", "Product"],
  ["first_frame", "Opening frame"], ["last_frame", "Ending frame"],
];

interface ReferenceMediaSectionProps {
  projectId: string;
  value: ReferenceSelection[];
  onChange: (references: ReferenceSelection[]) => void;
}

function typeForFile(file: File): ReferenceAsset["media_type"] | null {
  const filename = file.name.toLowerCase();
  for (const [mediaType, extensions] of Object.entries(EXTENSIONS)) {
    if (extensions.some((extension) => filename.endsWith(extension))) return mediaType as ReferenceAsset["media_type"];
  }
  return null;
}

function selection(asset: ReferenceAsset): ReferenceSelection {
  return { ...asset, asset_id: asset.id, role: "general", notes: "" };
}

function formatDuration(duration: number | null): string {
  return duration == null ? "" : `${duration.toFixed(1)} sec`;
}

function ReferencePreview({ reference }: { reference: ReferenceSelection }) {
  const preview = mediaUrl(reference.preview_url ?? (reference.media_type === "image" ? reference.content_url : null));
  if (preview) return <img src={preview} alt={`Preview of ${reference.filename}`} />;
  return reference.media_type === "audio" ? <Music2 size={25} /> : <Film size={25} />;
}

export function ReferenceMediaSection({ projectId, value, onChange }: ReferenceMediaSectionProps) {
  const [library, setLibrary] = useState<ReferenceAsset[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [uploading, setUploading] = useState(false);
  const [draggedIndex, setDraggedIndex] = useState<number | null>(null);
  const imageInput = useRef<HTMLInputElement>(null);
  const videoInput = useRef<HTMLInputElement>(null);
  const audioInput = useRef<HTMLInputElement>(null);

  useEffect(() => {
    let active = true;
    if (!projectId) {
      setLibrary([]);
      return () => { active = false; };
    }
    void api.referenceAssets(projectId)
      .then((assets) => { if (active) setLibrary(assets); })
      .catch((reason) => { if (active) setError(reason instanceof Error ? reason.message : "Could not load project references."); });
    return () => { active = false; };
  }, [projectId]);

  const validateAddition = (mediaType: ReferenceAsset["media_type"], pending = 1): string | null => {
    if (value.length + pending > 12) return "Reference-to-Video supports no more than 12 combined files.";
    const current = value.filter((item) => item.media_type === mediaType).length;
    if (current + pending > LIMITS[mediaType]) return `You can use up to ${LIMITS[mediaType]} ${mediaType} references.`;
    return null;
  };

  const addAsset = (asset: ReferenceAsset) => {
    if (value.some((item) => item.asset_id === asset.id)) return;
    const message = validateAddition(asset.media_type);
    if (message) { setError(message); return; }
    setError(null);
    onChange([...value, selection(asset)]);
  };

  const uploadFiles = async (files: File[]) => {
    if (!projectId || !files.length) return;
    setUploading(true);
    setError(null);
    try {
      const next = [...value];
      for (const file of files) {
        const mediaType = typeForFile(file);
        if (!mediaType) throw new Error(`${file.name} is not a supported image, video, or audio file.`);
        const typeCount = next.filter((item) => item.media_type === mediaType).length;
        if (next.length >= 12 || typeCount >= LIMITS[mediaType]) {
          throw new Error(next.length >= 12
            ? "Reference-to-Video supports no more than 12 combined files."
            : `You can use up to ${LIMITS[mediaType]} ${mediaType} references.`);
        }
        const asset = await api.uploadReference(projectId, file);
        if (!next.some((item) => item.asset_id === asset.id)) next.push(selection(asset));
        setLibrary((current) => [asset, ...current.filter((item) => item.id !== asset.id)]);
      }
      onChange(next);
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "Reference upload failed.");
    } finally {
      setUploading(false);
    }
  };

  const move = (from: number, to: number) => {
    if (to < 0 || to >= value.length || from === to) return;
    const next = [...value];
    const [item] = next.splice(from, 1);
    next.splice(to, 0, item);
    onChange(next);
  };

  const update = (index: number, fields: Partial<Pick<ReferenceSelection, "role" | "notes">>) => {
    onChange(value.map((item, itemIndex) => itemIndex === index ? { ...item, ...fields } : item));
  };

  const unused = library.filter((asset) => !value.some((item) => item.asset_id === asset.id));

  return (
    <div className="reference-block">
      <div className="field-heading"><label>Reference media</label><span>{value.length} / 12 files</span></div>
      <div
        className={`dropzone reference-dropzone${uploading ? " uploading" : ""}`}
        onDragOver={(event) => event.preventDefault()}
        onDrop={(event) => { event.preventDefault(); if (event.dataTransfer.files.length) void uploadFiles(Array.from(event.dataTransfer.files)); }}
      >
        <div className="drop-icons"><FileImage size={20} /><Film size={20} /><Music2 size={20} /></div>
        <strong>{uploading ? "Validating and importing locally…" : "Drop image, video, or audio references"}</strong>
        <span>PNG/JPG/WEBP · MP4/MOV/WEBM/MKV · WAV/MP3/M4A/FLAC</span>
        <div className="reference-add-buttons">
          <button type="button" onClick={() => imageInput.current?.click()}><Plus size={13} /> Add image</button>
          <button type="button" onClick={() => videoInput.current?.click()}><Plus size={13} /> Add video</button>
          <button type="button" onClick={() => audioInput.current?.click()}><Plus size={13} /> Add audio</button>
        </div>
        <input ref={imageInput} hidden type="file" multiple accept={EXTENSIONS.image.join(",")} onChange={(event) => { void uploadFiles(Array.from(event.target.files ?? [])); event.currentTarget.value = ""; }} />
        <input ref={videoInput} hidden type="file" multiple accept={EXTENSIONS.video.join(",")} onChange={(event) => { void uploadFiles(Array.from(event.target.files ?? [])); event.currentTarget.value = ""; }} />
        <input ref={audioInput} hidden type="file" multiple accept={EXTENSIONS.audio.join(",")} onChange={(event) => { void uploadFiles(Array.from(event.target.files ?? [])); event.currentTarget.value = ""; }} />
      </div>

      {error ? <div className="reference-error">{error}</div> : null}
      {value.length ? <div className="reference-list" aria-label="Selected reference order">
        {value.map((reference, index) => (
          <article
            className="reference-card"
            key={reference.asset_id}
            draggable
            onDragStart={() => setDraggedIndex(index)}
            onDragEnd={() => setDraggedIndex(null)}
            onDragOver={(event) => event.preventDefault()}
            onDrop={(event) => { event.preventDefault(); if (draggedIndex != null) move(draggedIndex, index); setDraggedIndex(null); }}
          >
            <div className="reference-order"><GripVertical size={14} /><span>{index + 1}</span></div>
            <div className={`reference-preview preview-${reference.media_type}`}><ReferencePreview reference={reference} /><span>{reference.media_type}</span></div>
            <div className="reference-copy"><strong title={reference.filename}>{reference.filename}</strong><small>{formatDuration(reference.duration) || (reference.width ? `${reference.width} × ${reference.height}` : "Local asset")}</small><input aria-label={`Notes for ${reference.filename}`} value={reference.notes} onChange={(event) => update(index, { notes: event.target.value })} placeholder="Optional guidance note" maxLength={500} /></div>
            <select aria-label={`Role for ${reference.filename}`} value={reference.role} onChange={(event) => update(index, { role: event.target.value as ReferenceRole })}>{ROLE_OPTIONS.map(([role, label]) => <option key={role} value={role}>{label}</option>)}</select>
            <div className="reference-actions"><button type="button" aria-label={`Move ${reference.filename} up`} disabled={index === 0} onClick={() => move(index, index - 1)}><ArrowUp size={13} /></button><button type="button" aria-label={`Move ${reference.filename} down`} disabled={index === value.length - 1} onClick={() => move(index, index + 1)}><ArrowDown size={13} /></button><button type="button" aria-label={`Remove ${reference.filename}`} onClick={() => onChange(value.filter((_, itemIndex) => itemIndex !== index))}><X size={13} /></button></div>
          </article>
        ))}
      </div> : null}

      {unused.length ? <div className="reference-library"><span><Upload size={13} /> Reuse from this project</span><div>{unused.slice(0, 8).map((asset) => <button type="button" key={asset.id} onClick={() => addAsset(asset)}><span>{asset.media_type}</span>{asset.filename}</button>)}</div></div> : null}
      <small className="reference-hint">Order and roles are stored with every generation. Timed references must be 2–15 seconds.</small>
    </div>
  );
}
