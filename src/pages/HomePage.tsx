import { ArrowRight, Cpu, HardDrive, Layers3, Play, Sparkles } from "lucide-react";
import type { Generation, Page, SystemStatus } from "../types/api";
import { VideoCard } from "../components/VideoCard";

interface HomePageProps {
  status: SystemStatus | null;
  generations: Generation[];
  onNavigate: (page: Page) => void;
  onOpenGeneration: (generation: Generation) => void;
}

export function HomePage({ status, generations, onNavigate, onOpenGeneration }: HomePageProps) {
  return (
    <div className="home-page">
      <section className="hero-panel">
        <div className="hero-orb orb-one" /><div className="hero-orb orb-two" />
        <div className="hero-copy">
          <span className="eyebrow"><Sparkles size={14} /> Local-first creation</span>
          <h1>Turn an idea into<br /><em>moving worlds.</em></h1>
          <p>Generate video with MiniMax H3 on your own NVIDIA GPU. Your prompts, media, and results stay on this PC.</p>
          <div className="hero-actions">
            <button className="hero-primary" onClick={() => onNavigate("create")}><Play size={17} fill="currentColor" /> Start creating</button>
            <button className="hero-secondary" onClick={() => onNavigate("history")}>View history <ArrowRight size={16} /></button>
          </div>
        </div>
        <div className="hero-art">
          <div className="film-frame frame-back"><span>LOCAL</span></div>
          <div className="film-frame frame-front"><div className="horizon"><div className="sun" /></div><span>H3 / 001</span></div>
        </div>
      </section>

      <section className="status-strip">
        <div><Cpu size={18} /><span><small>GPU</small>{status?.gpu.name ?? "Detecting…"}</span><b className={status?.gpu.available ? "ok" : "warn"}>{status?.gpu.available ? "Ready" : "Unavailable"}</b></div>
        <div><Layers3 size={18} /><span><small>MiniMax H3</small>{status?.models.minimax_h3 === "ready" ? "FL2VA stack ready" : "Models not installed"}</span><b className={status?.models.minimax_h3 === "ready" ? "ok" : "warn"}>{status?.models.minimax_h3 === "ready" ? "Ready" : "Missing"}</b></div>
        <div><HardDrive size={18} /><span><small>Local storage</small>{status ? `${status.disk.free_gb} GB free` : "Detecting…"}</span><b className="ok">Local</b></div>
      </section>

      <section className="section-block">
        <div className="section-heading"><div><span className="eyebrow">Your studio</span><h2>Recent generations</h2></div><button onClick={() => onNavigate("history")}>View all <ArrowRight size={15} /></button></div>
        {generations.length ? (
          <div className="video-grid">{generations.slice(0, 4).map((item) => <VideoCard key={item.id} generation={item} onOpen={onOpenGeneration} />)}</div>
        ) : (
          <div className="empty-gallery"><div><Sparkles size={24} /></div><h3>Your first frame starts here</h3><p>Create a local mock preview now, then connect ComfyUI when your H3 workflow is ready.</p><button onClick={() => onNavigate("create")}>Create a video</button></div>
        )}
      </section>
    </div>
  );
}
