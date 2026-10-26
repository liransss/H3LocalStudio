import * as Collapsible from "@radix-ui/react-collapsible";
import * as Switch from "@radix-ui/react-switch";
import { ChevronDown, Clapperboard, Gauge, Maximize2, Play, ShieldCheck, SlidersHorizontal, Sparkles, Video, WandSparkles, X } from "lucide-react";
import { useEffect, useMemo, useState } from "react";
import type { Generation, GenerationRequest, Job, Project, ReferenceSelection, SystemStatus } from "../types/api";
import { Button } from "../components/ui/Button";
import { ReferenceMediaSection } from "../components/ReferenceMediaSection";
import { mediaUrl } from "../services/api";

interface CreatePageProps {
  status: SystemStatus | null;
  projects: Project[];
  generations: Generation[];
  activeJob: Job | null;
  activeGeneration: Generation | null;
  initial: Generation | null;
  defaultUpscaler: GenerationRequest["upscaler"];
  onGenerate: (payload: GenerationRequest) => Promise<void>;
  onCancel: () => Promise<void>;
  onShowResult: (generation: Generation) => void;
}

const aspectRatios = ["16:9", "9:16", "1:1", "4:3", "3:4", "21:9"];
const durations = [4, 5, 8, 10, 15];

function h3Resolution(aspectRatio: string, quality: "preview" | "high"): string {
  const ratios: Record<string, [number, number]> = { "16:9": [16, 9], "9:16": [9, 16], "1:1": [1, 1], "4:3": [4, 3], "3:4": [3, 4], "21:9": [21, 9] };
  const [numerator, denominator] = ratios[aspectRatio] ?? ratios["16:9"];
  const ratio = numerator / denominator;
  const area = (quality === "preview" ? 0.30 : 0.98) * 1024 * 1024;
  const width = Math.max(32, Math.round(Math.sqrt(area * ratio) / 32) * 32);
  const height = Math.max(32, Math.round(Math.sqrt(area / ratio) / 32) * 32);
  return `${width}x${height}`;
}

export function CreatePage({ status, projects, generations, activeJob, activeGeneration, initial, defaultUpscaler, onGenerate, onCancel, onShowResult }: CreatePageProps) {
  const [prompt, setPrompt] = useState(initial?.prompt ?? "");
  const [mode, setMode] = useState<GenerationRequest["mode"]>(initial?.mode ?? "auto");
  const [aspect, setAspect] = useState(initial?.parameters.aspect_ratio ?? "16:9");
  const [duration, setDuration] = useState(initial?.parameters.duration ?? 5);
  const [quality, setQuality] = useState<"preview" | "high">(initial?.parameters.quality ?? "high");
  const [resolution, setResolution] = useState<GenerationRequest["final_resolution"]>(initial?.parameters.final_resolution ?? (status?.app.mock_mode ? "1080p" : "original"));
  const [upscaler, setUpscaler] = useState<GenerationRequest["upscaler"]>(initial?.parameters.upscaler ?? defaultUpscaler);
  const [audio, setAudio] = useState(initial?.parameters.audio_enabled ?? true);
  const [turbo, setTurbo] = useState(initial?.parameters.turbo ?? false);
  const [profile, setProfile] = useState<"balanced" | "quality">(initial?.parameters.profile ?? "balanced");
  const [steps, setSteps] = useState(initial?.parameters.steps ?? 20);
  const [seed, setSeed] = useState<string>(initial ? String(initial.seed) : "");
  const [projectId, setProjectId] = useState(initial?.project_id ?? projects[0]?.id ?? "");
  const [references, setReferences] = useState<ReferenceSelection[]>(() =>
    (initial?.references ?? []).map((reference) => ({ ...reference, asset_id: reference.asset_id ?? reference.id }))
  );
  const [advancedOpen, setAdvancedOpen] = useState(false);
  const [showMockBanner, setShowMockBanner] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);
  const [previewSelection, setPreviewSelection] = useState<Generation | null>(null);

  useEffect(() => {
    if (!projectId && projects.length) setProjectId(projects[0].id);
  }, [projectId, projects]);

  const isBusy = activeJob && !["completed", "failed", "upscale_failed", "cancelled"].includes(activeJob.status);
  const generationResolution = h3Resolution(aspect, quality);
  const previewGeneration = previewSelection ?? activeGeneration ?? generations.find((item) => item.original_url);
  const previewSource = mediaUrl(previewGeneration?.original_url ?? null);
  const modeLabel = ({ auto: "Auto", t2v: "Text to Video", i2v: "Image to Video", r2v: "Reference to Video" })[mode];
  const inferredMode = useMemo(() => {
    if (mode !== "auto") return mode;
    if (!references.length) return "t2v";
    const isFrameInput = references.length <= 2 && references.every((item) =>
      item.media_type === "image" && ["first_frame", "last_frame"].includes(item.role)
    );
    return isFrameInput ? "i2v" : "r2v";
  }, [mode, references]);

  const submit = async () => {
    if (submitting || isBusy) return;
    if (!prompt.trim()) {
      setError("Describe the video you want to create first.");
      return;
    }
    if (mode === "t2v" && references.length) {
      setError("Text-to-Video does not accept references. Choose Auto or a reference mode.");
      return;
    }
    if (mode === "i2v" && (references.length < 1 || references.length > 2 || references.some((item) => item.media_type !== "image"))) {
      setError("Image-to-Video needs one opening image and an optional ending image.");
      return;
    }
    if (mode === "r2v" && !references.length) {
      setError("Reference-to-Video needs at least one reference file.");
      return;
    }
    setError(null);
    setSubmitting(true);
    setPreviewSelection(null);
    try { await onGenerate({
      prompt,
      project_id: projectId || undefined,
      mode,
      duration,
      aspect_ratio: aspect,
      generation_resolution: generationResolution,
      final_resolution: status?.app.mock_mode ? resolution : upscaler === "original" ? "original" : "1080p",
      upscaler: status?.app.mock_mode ? "original" : upscaler,
      seed: seed ? Number(seed) : null,
      steps,
      turbo,
      profile,
      quality,
      fps: 24,
      audio_enabled: audio,
      references: references.map(({ asset_id, media_type, role, notes }) => ({ asset_id, media_type, role, notes })),
    }); } finally { setSubmitting(false); }
  };

  return (
    <div className="create-page">
      <div className="create-heading"><div><h1>Make your next scene.</h1><p>From a first thought to a final frame. All on your machine.</p></div><div className="privacy-note"><ShieldCheck size={14} /> Private by design</div></div>
      {status?.app.mock_mode && showMockBanner && <div className="mock-banner"><WandSparkles size={17} /><div><strong>Mock Mode is active</strong><span>Explore your workflow with a local test video. No AI inference runs in Mock Mode.</span></div><button aria-label="Dismiss mock information" onClick={() => setShowMockBanner(false)}><X size={15} /></button></div>}
      {status && !status.app.mock_mode ? <div className="local-banner"><WandSparkles size={17} /><div><strong>Local GPU Mode · Phase 4</strong><span>Native FL2VA and Ref2VA generation with optional FlashVSR or SeedVR2 1080p variants.</span></div></div> : null}

      <div className="create-grid">
        <section className="composer-card">
          <div className="panel-title"><span><WandSparkles size={17} /> Creative direction</span><span className="model-chip">MiniMax H3</span></div>
          <div className="field-heading"><label htmlFor="prompt">Prompt</label><span>{prompt.length} / 10,000</span></div>
          <textarea id="prompt" value={prompt} onChange={(event) => setPrompt(event.target.value)} placeholder="A cinematic close-up of a glass flower blooming at midnight, soft moonlight, slow camera orbit, delicate crystalline sound…" maxLength={10000} rows={6} onKeyDown={(event) => { if ((event.ctrlKey || event.metaKey) && event.key === "Enter") { event.preventDefault(); void submit(); } }} />
          <div className="prompt-tools"><span>Subject, motion, light, sound. Make it yours.</span><kbd>Ctrl + Enter</kbd></div>

          <ReferenceMediaSection projectId={projectId} value={references} onChange={setReferences} />
        </section>

        <aside className="settings-card">
          <div className="panel-title"><span><SlidersHorizontal size={16} /> Generation settings</span><span>24 fps</span></div>
          <div className="setting-group"><label>Project</label><select aria-label="Project" value={projectId} onChange={(event) => { setProjectId(event.target.value); setReferences([]); }}>{projects.map((project) => <option key={project.id} value={project.id}>{project.name}</option>)}</select></div>
          <div className="setting-group"><label>Generation mode</label><select aria-label="Generation mode" value={mode} onChange={(event) => setMode(event.target.value as GenerationRequest["mode"])}><option value="auto">Auto</option><option value="t2v">Text to Video</option><option value="i2v">Image to Video</option><option value="r2v">Reference to Video</option></select><small>Selected: {modeLabel}. This setup routes to {inferredMode.toUpperCase()}.</small></div>
          {inferredMode === "r2v" ? <div className="memory-warning"><strong>Reference-to-Video uses more memory</strong><span>Close memory-intensive apps and start with Preview for larger reference sets.</span>{status?.models.minimax_h3_ref2va !== "ready" ? <small>Ref2VA models must be installed on Models before generation.</small> : null}</div> : null}
          <div className="setting-group"><label>Aspect ratio</label><div className="choice-grid aspect-grid">{aspectRatios.map((value) => <button key={value} aria-pressed={aspect === value} className={aspect === value ? "selected" : ""} onClick={() => setAspect(value)}><i className={`ratio ratio-${value.replace(":", "-")}`} />{value}</button>)}</div></div>
          <div className="setting-group"><label>Duration</label><div className="choice-grid duration-grid">{durations.map((value) => <button key={value} aria-pressed={duration === value} className={duration === value ? "selected" : ""} onClick={() => setDuration(value)}>{value}s</button>)}</div></div>
          <div className="setting-group"><label>Output quality</label><div className="segment-control"><button aria-pressed={quality === "preview"} className={quality === "preview" ? "selected" : ""} onClick={() => setQuality("preview")}><span>Preview</span><small>Faster exploration</small></button><button aria-pressed={quality === "high"} className={quality === "high" ? "selected" : ""} onClick={() => setQuality("high")}><span>High quality</span><small>Full settings</small></button></div></div>
          <div className="setting-group"><div className="label-row"><label>Final output</label><span>Generation: {generationResolution.replace("x", " × ")}</span></div>{status?.app.mock_mode ? <><select aria-label="Final output" value={resolution} onChange={(event) => setResolution(event.target.value as GenerationRequest["final_resolution"])}><option value="original">Original · local mock</option><option value="1080p">1080p · FFmpeg mock resize</option></select><small>Mock Mode does not claim AI inference.</small></> : <div className="output-choice"><button className={upscaler === "original" ? "selected" : ""} onClick={() => setUpscaler("original")}><Video size={15} /><span>Original</span><small>Native H3 · no post-process</small></button><button className={upscaler === "flashvsr" ? "selected" : ""} onClick={() => setUpscaler("flashvsr")}><Gauge size={15} /><span>Fast 1080p</span><small>FlashVSR · {status?.models.flashvsr === "ready" ? "ready" : "install required"}</small></button><button className={upscaler === "seedvr2" ? "selected" : ""} onClick={() => setUpscaler("seedvr2")}><Sparkles size={15} /><span>Best Quality 1080p</span><small>SeedVR2 · {status?.models.seedvr2 === "ready" ? "ready" : "install required"}</small></button></div>}</div>
          <div className="toggle-row"><div><label>Native H3 audio</label><small>Dialogue, sound effects, and ambient audio</small></div><Switch.Root className="switch-root" aria-label="Native H3 audio" checked={audio} onCheckedChange={setAudio}><Switch.Thumb className="switch-thumb" /></Switch.Root></div>

          <Collapsible.Root open={advancedOpen} onOpenChange={setAdvancedOpen} className="advanced-settings">
            <Collapsible.Trigger><span>Advanced settings</span><ChevronDown size={16} className={advancedOpen ? "rotated" : ""} /></Collapsible.Trigger>
            <Collapsible.Content>
              <div className="setting-group"><label>Seed</label><input type="number" min="0" aria-label="Seed" value={seed} onChange={(event) => setSeed(event.target.value)} placeholder="Random" /></div>
              <div className="advanced-row"><div className="setting-group"><label>Steps</label><input type="number" min="1" max="100" aria-label="Steps" value={turbo ? (inferredMode === "r2v" ? 4 : 8) : steps} disabled={turbo} onChange={(event) => setSteps(Number(event.target.value))} /></div><div className="setting-group"><label>Generation profile</label><select aria-label="Generation profile" value={profile} onChange={(event) => setProfile(event.target.value as "balanced" | "quality")}><option value="balanced">Balanced</option><option value="quality">Quality</option></select></div></div>
              <div className="toggle-row compact"><div><label>Fast / Turbo</label><small>Uses the official {inferredMode === "r2v" ? "4-step Ref2VA" : "8-step FL2VA"} LoRA for speed.</small></div><Switch.Root className="switch-root" aria-label="Fast / Turbo" checked={turbo} onCheckedChange={setTurbo}><Switch.Thumb className="switch-thumb" /></Switch.Root></div>
            </Collapsible.Content>
          </Collapsible.Root>

        </aside>
        <section className="studio-preview" aria-label="Video preview">
          <div className="preview-heading"><span><Clapperboard size={17} /> Preview</span><span>{previewGeneration ? (previewGeneration.is_mock ? "Mock preview" : "Original H3") : "Your screening room"}</span></div>
          <div className={`preview-stage${isBusy ? " is-rendering" : ""}`}>
            {previewSource ? <video key={previewSource} src={previewSource} poster={mediaUrl(previewGeneration?.thumbnail_url ?? null) ?? undefined} controls playsInline loop preload="metadata" /> : <div className="preview-empty"><div className="viewfinder"><Clapperboard size={36} strokeWidth={1} /></div><h2>A little direction.<br />Endless possibilities.</h2><p>Write your scene, add references, and generate.<br />Your video will appear here.</p></div>}
            {isBusy ? <div className="preview-render-state" role="status"><span className="render-pulse" />{activeJob.stage}<strong>{Math.round(activeJob.progress * 100)}%</strong></div> : null}
          </div>
          <div className="preview-toolbar"><div><span>{previewGeneration?.parameters.aspect_ratio ?? aspect}</span><span>{previewGeneration?.parameters.duration ?? duration}s</span><span>24 fps</span></div>{previewGeneration?.original_url ? <button onClick={() => onShowResult(previewGeneration)}><Maximize2 size={14} /> Open result</button> : <span>Local output</span>}</div>
          {previewGeneration ? <p className="preview-caption">{previewGeneration.prompt}</p> : null}
          <div className="recent-heading"><h2>Recent creations</h2><span>{generations.length} in your library</span></div>
          {generations.length ? <div className="recent-filmstrip">{generations.slice(0, 4).map((item) => <button key={item.id} className={previewGeneration?.id === item.id ? "selected" : ""} onClick={() => setPreviewSelection(item)} aria-label={`Preview ${item.prompt}`} aria-pressed={previewGeneration?.id === item.id}><div>{item.thumbnail_url ? <img src={mediaUrl(item.thumbnail_url)!} alt="" /> : <Video size={24} />}<Play size={15} /><span>{item.parameters.duration}s</span></div><p>{item.prompt}</p></button>)}</div> : <div className="recent-empty"><Video size={18} /><p>Your creative library starts with your first video.<span>Every prompt and setting is saved locally.</span></p></div>}
        </section>
      </div>

      {!isBusy ? <footer className="creation-action-bar">
        <div className="creation-summary"><strong>{quality === "high" ? "High quality" : "Preview"} video</strong><span>{aspect} · {duration}s · {audio ? "Audio on" : "Silent"}</span></div>
        {error ? <div className="form-error" role="alert">{error}</div> : null}
        <button className="generate-button" onClick={() => void submit()} disabled={submitting || !status}><Sparkles size={18} />{submitting ? "Starting generation…" : status?.app.mock_mode ? "Generate mock video" : "Generate locally"}</button>
      </footer> : null}

      {activeJob && activeGeneration && (
        <section className={`progress-dock progress-${activeJob.status}`} aria-label="Generation progress">
          <div className="progress-icon"><span>{Math.round(activeJob.progress * 100)}</span><small>%</small></div>
          <div className="progress-copy"><div><strong>{activeJob.stage}</strong><span>{activeJob.status === "failed" ? activeJob.error_message : activeGeneration.prompt}</span></div><div className="progress-track" role="progressbar" aria-label="Generation" aria-valuemin={0} aria-valuemax={100} aria-valuenow={Math.round(activeJob.progress * 100)}><i style={{ width: `${activeJob.progress * 100}%` }} /></div></div>
          {activeJob.status === "completed" ? <Button variant="primary" onClick={() => onShowResult(activeGeneration)}>View result</Button> : ["failed", "upscale_failed"].includes(activeJob.status) ? <Button onClick={() => activeJob.kind === "upscale" ? onShowResult(activeGeneration) : void submit()}>{activeJob.kind === "upscale" ? "View original" : "Try again"}</Button> : activeJob.status === "cancelled" ? <span className="cancelled-label">Cancelled</span> : <Button variant="ghost" onClick={() => void onCancel()}>Cancel</Button>}
        </section>
      )}
    </div>
  );
}
