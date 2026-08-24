import * as Switch from "@radix-ui/react-switch";
import { Cpu, Database, FolderOpen, HardDrive, Play, RefreshCw, Save, Server, Square, TerminalSquare } from "lucide-react";
import { useEffect, useState } from "react";
import { Button } from "../components/ui/Button";
import { StatusBadge } from "../components/ui/StatusBadge";
import { api } from "../services/api";
import type { LocalSettings, SystemStatus } from "../types/api";

interface SettingsPageProps {
  status: SystemStatus | null;
  onRefreshStatus: () => void;
  onSettingsSaved: (settings: LocalSettings) => void;
}

export function SettingsPage({ status, onRefreshStatus, onSettingsSaved }: SettingsPageProps) {
  const [settings, setSettings] = useState<LocalSettings | null>(null);
  const [message, setMessage] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  useEffect(() => { void api.settings().then(setSettings); }, []);

  const update = <K extends keyof LocalSettings>(key: K, value: LocalSettings[K]) => {
    setSettings((current) => current ? { ...current, [key]: value } : current);
  };
  const save = async () => {
    if (!settings) return;
    const result = await api.saveSettings(settings);
    onSettingsSaved(settings);
    setMessage(result.restart_required ? "Saved. Restart the local backend to apply runtime, connection, or storage changes." : "Settings saved locally.");
    onRefreshStatus();
  };
  const runtimeAction = async (action: "start" | "stop" | "update") => {
    setBusy(true);
    try {
      if (action === "start") await api.startComfyUI();
      else if (action === "stop") await api.stopComfyUI();
      else await api.updateComfyUI();
      setMessage(action === "update" ? "Managed ComfyUI updated. Restart it before the next generation." : `Managed ComfyUI ${action === "start" ? "started" : "stopped"}.`);
      onRefreshStatus();
    } catch (reason) {
      setMessage(reason instanceof Error ? reason.message : `Could not ${action} ComfyUI.`);
    } finally {
      setBusy(false);
    }
  };

  if (!settings) return <div className="loading-page">Loading local settings…</div>;
  const managed = settings.comfyui_mode === "managed";
  return (
    <div className="settings-page">
      <div className="page-title"><div><span className="eyebrow">Configuration</span><h1>Settings</h1><p>Paths and services are local to this Windows machine.</p></div><Button variant="primary" icon={<Save size={16} />} onClick={() => void save()}>Save changes</Button></div>
      {message ? <div className="settings-message">{message}</div> : null}
      <div className="settings-layout">
        <nav><a href="#storage"><Database size={16} /> Storage</a><a href="#hardware"><Cpu size={16} /> Hardware</a><a href="#inference"><Server size={16} /> Inference</a><a href="#comfyui"><TerminalSquare size={16} /> ComfyUI & FFmpeg</a></nav>
        <div className="settings-sections">
          <section id="storage">
            <div className="settings-section-head"><div className="settings-section-icon"><HardDrive size={18} /></div><div><h2>Storage</h2><p>Large files remain outside the source repository.</p></div></div>
            <div className="form-grid"><label className="full"><span>Application data root</span><div className="path-input"><input value={settings.data_root} onChange={(event) => update("data_root", event.target.value)} /><button disabled title="Use an absolute Windows path"><FolderOpen size={16} /></button></div></label><label><span>Models</span><input value={settings.model_path} readOnly /></label><label><span>Outputs</span><input value={settings.output_path} readOnly /></label><label><span>Inputs</span><input value={settings.input_path} readOnly /></label><label><span>Cache</span><input value={settings.cache_path} readOnly /></label></div>
          </section>

          <section id="hardware">
            <div className="settings-section-head"><div className="settings-section-icon"><Cpu size={18} /></div><div><h2>Detected hardware</h2><p>Live local hardware information from Windows.</p></div><button className="text-button" onClick={onRefreshStatus}>Refresh</button></div>
            <div className="hardware-grid"><div><small>GPU</small><strong>{status?.gpu.name ?? "Not detected"}</strong><StatusBadge ok={Boolean(status?.gpu.available)} label={status?.gpu.cuda ? "CUDA available" : "Unavailable"} /></div><div><small>Video memory</small><strong>{status?.gpu.vram_total_mb ? `${(status.gpu.vram_total_mb / 1024).toFixed(1)} GB` : "—"}</strong><span>{status?.gpu.vram_used_mb != null ? `${(status.gpu.vram_used_mb / 1024).toFixed(1)} GB used · ${(status.gpu.vram_free_mb! / 1024).toFixed(1)} GB free` : "No reading"}</span></div><div><small>System RAM</small><strong>{status ? `${(status.memory.total_mb / 1024).toFixed(0)} GB` : "—"}</strong><span>{status ? `${(status.memory.available_mb / 1024).toFixed(1)} GB available` : "No reading"}</span></div><div><small>Disk</small><strong>{status ? `${status.disk.free_gb} GB free` : "—"}</strong><span>{status?.disk.root}</span></div></div>
          </section>

          <section id="inference">
            <div className="settings-section-head"><div className="settings-section-icon"><Server size={18} /></div><div><h2>Inference defaults</h2><p>Choose native H3 output or an optional Phase 3 AI-upscaled 1080p variant.</p></div></div>
            <div className="form-grid"><label><span>ComfyUI memory profile</span><select value={settings.comfyui_profile} onChange={(event) => update("comfyui_profile", event.target.value as LocalSettings["comfyui_profile"])}><option value="balanced">Balanced · native management</option><option value="low_vram">Low VRAM · --lowvram</option></select></label><label><span>Default output variant</span><select value={settings.default_upscaler ?? "original"} onChange={(event) => update("default_upscaler", event.target.value as LocalSettings["default_upscaler"])}><option value="original">Original · native H3</option><option value="flashvsr">Fast 1080p · FlashVSR</option><option value="seedvr2">Best Quality 1080p · SeedVR2</option></select><small>Upscalers run after H3 unloads and never replace the original.</small></label></div>
          </section>

          <section id="comfyui">
            <div className="settings-section-head"><div className="settings-section-icon"><TerminalSquare size={18} /></div><div><h2>ComfyUI & FFmpeg</h2><p>Native MiniMax H3 requires ComfyUI 0.30.0 or newer.</p></div><StatusBadge ok={Boolean(status?.comfyui.running && status.comfyui.compatible !== false)} label={status?.comfyui.running ? (status.comfyui.compatible === false ? "Update required" : `Connected${status.comfyui.version ? ` · ${status.comfyui.version}` : ""}`) : "Offline"} /></div>
            <div className="form-grid"><label><span>Runtime ownership</span><select value={settings.comfyui_mode} onChange={(event) => update("comfyui_mode", event.target.value as LocalSettings["comfyui_mode"])}><option value="managed">Managed by H3 Local Studio</option><option value="external">External · never modify automatically</option></select></label><label><span>Launch profile</span><select value={settings.comfyui_profile} onChange={(event) => update("comfyui_profile", event.target.value as LocalSettings["comfyui_profile"])}><option value="balanced">Balanced</option><option value="low_vram">Low VRAM</option></select></label><label className="full"><span>ComfyUI installation path</span><input value={settings.comfyui_path ?? ""} onChange={(event) => update("comfyui_path", event.target.value)} placeholder="F:\AI\H3LocalStudio\runtime\ComfyUI" /></label><label><span>Host</span><input value={settings.comfyui_host} onChange={(event) => update("comfyui_host", event.target.value)} /></label><label><span>Port</span><input type="number" value={settings.comfyui_port} onChange={(event) => update("comfyui_port", Number(event.target.value))} /></label><label className="full"><span>FFmpeg executable</span><input value={settings.ffmpeg_path ?? status?.ffmpeg.path ?? ""} onChange={(event) => update("ffmpeg_path", event.target.value)} /><small>{status?.ffmpeg.available ? "FFmpeg and sibling FFprobe will be used for output validation" : "Not found"}</small></label></div>
            <div className="toggle-row"><div><label>Start managed ComfyUI automatically</label><small>Starts as a hidden child process and writes stdout/stderr to logs/comfyui.log.</small></div><Switch.Root className="switch-root" checked={settings.comfyui_auto_start} disabled={!managed} onCheckedChange={(value) => update("comfyui_auto_start", value)}><Switch.Thumb className="switch-thumb" /></Switch.Root></div>
            <div className="runtime-actions"><Button disabled={!managed || busy || Boolean(status?.comfyui.running)} icon={<Play size={15} />} onClick={() => void runtimeAction("start")}>Start</Button><Button disabled={!managed || busy || !status?.comfyui.running} icon={<Square size={14} />} onClick={() => void runtimeAction("stop")}>Stop</Button><Button disabled={!managed || busy || Boolean(status?.comfyui.running)} icon={<RefreshCw size={15} />} onClick={() => void runtimeAction("update")}>Update ComfyUI</Button></div>
          </section>

          <section className="about-section"><div><span className="brand-mark small">H3</span><div><h3>H3 Local Studio</h3><p>Version 0.1.0 · Phase 3 local AI upscaling</p></div></div><span>Local-first. Offline-capable after model installation.</span></section>
        </div>
      </div>
    </div>
  );
}
