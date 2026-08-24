import { FolderKanban, Plus, Sparkles } from "lucide-react";
import { useState } from "react";
import type { Generation, Project } from "../types/api";

interface ProjectsPageProps {
  projects: Project[];
  generations: Generation[];
  onCreate: (name: string) => Promise<void>;
}

export function ProjectsPage({ projects, generations, onCreate }: ProjectsPageProps) {
  const [adding, setAdding] = useState(false);
  const [name, setName] = useState("");
  const submit = async () => {
    if (!name.trim()) return;
    await onCreate(name.trim());
    setName("");
    setAdding(false);
  };
  return (
    <div className="library-page">
      <div className="page-title"><div><span className="eyebrow">Organize</span><h1>Projects</h1><p>Group creative work without duplicating local models.</p></div><button className="hero-primary small" onClick={() => setAdding(true)}><Plus size={16} /> New project</button></div>
      {adding && <div className="inline-create"><FolderKanban size={19} /><input autoFocus value={name} onChange={(event) => setName(event.target.value)} onKeyDown={(event) => event.key === "Enter" && void submit()} placeholder="Project name" /><button onClick={() => void submit()}>Create</button><button onClick={() => setAdding(false)}>Cancel</button></div>}
      <div className="project-grid">{projects.map((project, index) => { const count = generations.filter((item) => item.project_id === project.id).length; return <article className="project-card" key={project.id}><div className={`project-cover cover-${index % 4}`}><Sparkles size={22} /><span>{String(index + 1).padStart(2, "0")}</span></div><div><h3>{project.name}</h3><p>{project.description || "Local creative project"}</p><span>{count} {count === 1 ? "generation" : "generations"} · {project.reference_count} reusable {project.reference_count === 1 ? "reference" : "references"}</span></div></article>; })}</div>
    </div>
  );
}
