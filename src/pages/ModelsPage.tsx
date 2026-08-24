import {
  AlertTriangle,
  Ban,
  CheckCircle2,
  FolderOpen,
  HardDriveDownload,
  Layers3,
  RefreshCw,
  ShieldCheck,
} from "lucide-react";
import { Fragment, useCallback, useEffect, useState } from "react";
import { Button } from "../components/ui/Button";
import { api } from "../services/api";
import type { ModelFamily } from "../types/api";

function formatBytes(bytes: number): string {
  if (!bytes) return "0 B";
  const units = ["B", "KB", "MB", "GB", "TB"];
  const index = Math.min(Math.floor(Math.log(bytes) / Math.log(1024)), units.length - 1);
  return `${(bytes / 1024 ** index).toFixed(index > 2 ? 2 : 1)} ${units[index]}`;
}

function isActive(status?: string): boolean {
  return status === "queued" || status === "running" || status === "cancelling";
}

export function ModelsPage() {
  const [models, setModels] = useState<ModelFamily[]>([]);
  const [confirmation, setConfirmation] = useState<{ model: ModelFamily; repair: boolean } | null>(null);
  const [error, setError] = useState<string | null>(null);

  const refresh = useCallback(async () => {
    try {
      setModels(await api.models());
      setError(null);
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "Could not read the model manifest.");
    }
  }, []);

  useEffect(() => { void refresh(); }, [refresh]);
  const hasActiveOperation = models.some((model) => isActive(model.operation?.status));
  useEffect(() => {
    if (!hasActiveOperation) return;
    const timer = window.setInterval(() => void refresh(), 1000);
    return () => window.clearInterval(timer);
  }, [hasActiveOperation, refresh]);

  const startInstall = async () => {
    if (!confirmation) return;
    try {
      await api.installModels(confirmation.model.id, confirmation.repair);
      setConfirmation(null);
      await refresh();
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "The model download could not start.");
    }
  };

  const verify = async (model: ModelFamily) => {
    try {
      await api.verifyModels(model.id);
      await refresh();
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "Verification could not start.");
    }
  };

  return (
    <div className="library-page">
      <div className="page-title">
        <div><span className="eyebrow">Verified local assets</span><h1>Model manager</h1><p>Install checksum-pinned generation and AI upscaler assets into the managed ComfyUI runtime.</p></div>
        <Button icon={<FolderOpen size={15} />} onClick={() => void api.openModels()}>Open model folder</Button>
      </div>
      <div className="model-summary"><Layers3 size={22} /><div><strong>MiniMax H3 generation</strong><span>FL2VA handles text/frame generation · Ref2VA handles ordered image, video, and audio references</span></div><span className="phase-chip">Phase 4</span></div>
      {error ? <div className="form-error model-error">{error}</div> : null}

      {models.map((model) => {
        const operation = model.operation;
        const percent = operation?.total_bytes ? Math.min(100, operation.bytes_done / operation.total_bytes * 100) : 0;
        return (
          <Fragment key={model.id}>
          {model.id === "flashvsr" ? <div className="model-section-title"><span className="eyebrow">Upscalers</span><h2>1080p AI post-processing</h2><p>Fast uses FlashVSR v1.1. Best Quality uses native SeedVR2 with VRAM-aware temporal chunking.</p></div> : null}
          <article className="model-card model-family-card">
            <div className="model-family-head">
              <div className="model-icon"><HardDriveDownload size={25} /></div>
              <div className="model-info"><div><h3>{model.name}</h3><span className={model.installed ? "installed" : "missing"}>{model.verified ? <ShieldCheck size={14} /> : model.installed ? <CheckCircle2 size={14} /> : <AlertTriangle size={14} />}{model.status}</span></div><p>{formatBytes(model.total_size)} · manifest {model.manifest_version}</p>{model.runtime ? <small>{model.runtime.ready ? `Runtime ready · ${model.runtime.version ?? model.runtime.kind}` : model.runtime.reason}{model.runtime.dependency ? ` · ${model.runtime.dependency}` : ""}</small> : null}<code>{model.target_root}</code></div>
              <div className="model-actions">
                <Button disabled={Boolean(operation && isActive(operation.status))} icon={<HardDriveDownload size={15} />} onClick={() => setConfirmation({ model, repair: false })}>Install missing</Button>
                <Button disabled={!model.installed || Boolean(operation && isActive(operation.status))} icon={<ShieldCheck size={15} />} onClick={() => void verify(model)}>Verify</Button>
                <Button disabled={Boolean(operation && isActive(operation.status))} icon={<RefreshCw size={15} />} onClick={() => setConfirmation({ model, repair: true })}>Repair</Button>
              </div>
            </div>

            {operation ? (
              <div className={`model-operation operation-${operation.status}`}>
                <div><strong>{operation.message}</strong><span>{operation.current_file ?? operation.status}</span></div>
                <div className="progress-track"><i style={{ width: `${percent}%` }} /></div>
                <small>{formatBytes(operation.bytes_done)} / {formatBytes(operation.total_bytes)} · {percent.toFixed(1)}%</small>
                {operation.error ? <p>{operation.error}</p> : null}
                {isActive(operation.status) ? <Button variant="ghost" icon={<Ban size={14} />} onClick={() => void api.cancelModelOperation(operation.id).then(refresh)}>Cancel</Button> : null}
              </div>
            ) : null}

            <div className="model-components" role="table" aria-label={`${model.name} components`}>
              {model.components.map((component) => (
                <div className="model-component" role="row" key={component.id}>
                  <span className={`component-state state-${component.status}`} aria-label={component.status} />
                  <div><strong>{component.filename}</strong><small>{component.model_dir} · {formatBytes(component.size)}{component.shared ? " · shared with FL2VA/Ref2VA" : ` · ${model.id}-specific`}</small><code>{component.path}</code></div>
                  <span className={`component-label state-${component.status}`}>{component.status}</span>
                </div>
              ))}
            </div>
          </article>
          </Fragment>
        );
      })}

      <div className="honesty-card"><strong>Explicit, resumable downloads</strong><p>Downloads begin only after the confirmation below. Files use a visible <code>.part</code> suffix, resume when supported, and are atomically renamed only after their pinned SHA-256 checksum matches.</p></div>

      {confirmation ? (
        <div className="confirmation-backdrop" onMouseDown={(event) => event.target === event.currentTarget && setConfirmation(null)}>
          <section className="confirmation-dialog" role="dialog" aria-modal="true" aria-labelledby="install-title">
            <span className="eyebrow">Large local download</span>
            <h2 id="install-title">{confirmation.repair ? "Repair" : "Install"} {confirmation.model.name}?</h2>
            <p>This operation will download up to <strong>{formatBytes(confirmation.model.components.filter((component) => !["installed", "verified"].includes(component.status)).reduce((total, component) => total + Math.max(0, component.size - component.bytes_present), 0))}</strong>. Shared and other valid files are reused and checksum-verified.{confirmation.model.runtime && !confirmation.model.runtime.ready ? " The pinned provider runtime and compatible dependencies are also prepared inside managed ComfyUI." : ""}</p>
            <div className="install-file-list">{confirmation.model.components.filter((component) => !["installed", "verified"].includes(component.status)).map((component) => <div key={component.id}><span>{component.filename}</span><small>{formatBytes(Math.max(0, component.size - component.bytes_present))}</small></div>)}</div>
            <label>Target folder<code>{confirmation.model.target_root}</code></label>
            <div className="confirmation-actions"><Button onClick={() => setConfirmation(null)}>Cancel</Button><Button variant="primary" icon={<HardDriveDownload size={15} />} onClick={() => void startInstall()}>Confirm download</Button></div>
          </section>
        </div>
      ) : null}
    </div>
  );
}
