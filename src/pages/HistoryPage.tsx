import { Search, SlidersHorizontal, Sparkles } from "lucide-react";
import { useMemo, useState } from "react";
import { VideoCard } from "../components/VideoCard";
import type { Generation } from "../types/api";

interface HistoryPageProps {
  generations: Generation[];
  onOpen: (generation: Generation) => void;
}

export function HistoryPage({ generations, onOpen }: HistoryPageProps) {
  const [search, setSearch] = useState("");
  const [mode, setMode] = useState("all");
  const filtered = useMemo(() => generations.filter((item) => (mode === "all" || item.mode === mode) && item.prompt.toLowerCase().includes(search.toLowerCase())), [generations, mode, search]);
  return (
    <div className="library-page">
      <div className="page-title"><div><span className="eyebrow">Local library</span><h1>Generation history</h1><p>Every prompt, seed, setting, and output stays reproducible.</p></div><div className="history-count">{generations.length}<small>generations</small></div></div>
      <div className="filter-bar"><label><Search size={16} /><input value={search} onChange={(event) => setSearch(event.target.value)} placeholder="Search prompts…" /></label><div className="filter-pills"><SlidersHorizontal size={15} />{["all", "t2v", "i2v", "r2v"].map((value) => <button key={value} className={mode === value ? "active" : ""} onClick={() => setMode(value)}>{value === "all" ? "All" : value.toUpperCase()}</button>)}</div></div>
      {filtered.length ? <div className="video-grid large">{filtered.map((item) => <VideoCard key={item.id} generation={item} onOpen={onOpen} />)}</div> : <div className="empty-gallery"><div><Sparkles size={24} /></div><h3>No generations found</h3><p>Try another filter or create your first local video.</p></div>}
    </div>
  );
}

