import { useCallback, useEffect, useRef, useState } from "react";
import { Layout } from "./components/Layout";
import { ResultPanel } from "./components/ResultPanel";
import { useJobProgress } from "./hooks/useJobProgress";
import { CreatePage } from "./pages/CreatePage";
import { HistoryPage } from "./pages/HistoryPage";
import { HomePage } from "./pages/HomePage";
import { ModelsPage } from "./pages/ModelsPage";
import { ProjectsPage } from "./pages/ProjectsPage";
import { SettingsPage } from "./pages/SettingsPage";
import { SpacesPage } from "./pages/SpacesPage";
import { api, ApiError } from "./services/api";
import type { Generation, GenerationRequest, Job, LocalSettings, Page, Project, SystemStatus } from "./types/api";

function App() {
  const [page, setPage] = useState<Page>("home");
  const [creationRevision, setCreationRevision] = useState(0);
  const [status, setStatus] = useState<SystemStatus | null>(null);
  const [generations, setGenerations] = useState<Generation[]>([]);
  const [projects, setProjects] = useState<Project[]>([]);
  const [activeJob, setActiveJob] = useState<Job | null>(null);
  const [activeGeneration, setActiveGeneration] = useState<Generation | null>(null);
  const [selectedGeneration, setSelectedGeneration] = useState<Generation | null>(null);
  const [reuseGeneration, setReuseGeneration] = useState<Generation | null>(null);
  const [backendError, setBackendError] = useState<string | null>(null);
  const [defaultUpscaler, setDefaultUpscaler] = useState<GenerationRequest["upscaler"]>("original");
  const autoUpscaleStarted = useRef(new Set<string>());

  const refreshStatus = useCallback(() => {
    void api.systemStatus().then((value) => { setStatus(value); setBackendError(null); }).catch(() => setBackendError("The local backend is not responding on 127.0.0.1:7331."));
  }, []);
  const refreshLibrary = useCallback(async () => {
    const [newGenerations, newProjects] = await Promise.all([api.generations(), api.projects()]);
    setGenerations(newGenerations);
    setProjects(newProjects);
  }, []);

  useEffect(() => {
    refreshStatus();
    void refreshLibrary().catch(() => setBackendError("Start the local backend to load projects and history."));
    void api.settings().then((settings) => setDefaultUpscaler(settings.default_upscaler ?? "original"));
  }, [refreshLibrary, refreshStatus]);

  useJobProgress(activeJob?.id ?? null, (job) => {
    setActiveJob(job);
    if (job.generation_id) {
      void api.generation(job.generation_id).then((generation) => {
        setActiveGeneration(generation);
        setSelectedGeneration((current) => current?.id === generation.id ? generation : current);
        if (["completed", "failed", "upscale_failed", "cancelled"].includes(job.status)) void refreshLibrary();
        if (
          job.kind === "generation" && job.status === "completed" &&
          generation.parameters.upscaler !== "original" &&
          !generation.variants.some((variant) => variant.variant === generation.parameters.upscaler && variant.status === "completed") &&
          !autoUpscaleStarted.current.has(generation.id)
        ) {
          autoUpscaleStarted.current.add(generation.id);
          void api.upscale(generation.id, generation.parameters.upscaler).then((upscaleJob) => {
            setActiveJob(upscaleJob);
            setActiveGeneration(generation);
          }).catch((error) => setBackendError(error instanceof Error ? error.message : "Could not start the selected AI upscale."));
        }
      });
    }
  });

  const generate = async (payload: GenerationRequest) => {
    try {
      const accepted = await api.createGeneration(payload);
      setActiveJob(accepted.job);
      setActiveGeneration(accepted.generation);
      setBackendError(null);
    } catch (error) {
      setBackendError(error instanceof Error ? error.message : "Could not start the local generation.");
      if (error instanceof ApiError && typeof error.detail === "object" && error.detail && "code" in error.detail && ["upscaler_unavailable", "ref2va_models_missing", "h3_models_missing"].includes(String(error.detail.code))) setPage("models");
    }
  };
  const cancel = async () => { if (activeJob) setActiveJob(await api.cancelJob(activeJob.id)); };
  const openGeneration = async (generation: Generation, target: "file" | "folder", variant: "original" | "flashvsr" | "seedvr2") => {
    try { await api.openGeneration(generation.id, target, variant); } catch (error) { setBackendError(error instanceof Error ? error.message : "Could not open the local output."); }
  };
  const deleteGeneration = async (generation: Generation) => {
    if (!window.confirm("Remove this generation from History? Output files are preserved.")) return;
    await api.deleteGeneration(generation.id);
    setSelectedGeneration(null);
    await refreshLibrary();
  };
  const reuse = (generation: Generation) => { setReuseGeneration(generation); setSelectedGeneration(null); setPage("create"); };
  const upscale = async (generation: Generation, provider: "flashvsr" | "seedvr2") => {
    try {
      const job = await api.upscale(generation.id, provider);
      setActiveJob(job);
      setActiveGeneration(generation);
      setSelectedGeneration(null);
      setPage("create");
    } catch (error) {
      setBackendError(error instanceof Error ? error.message : "Could not start the local AI upscale.");
      if (error instanceof ApiError && typeof error.detail === "object" && error.detail && "code" in error.detail && error.detail.code === "upscaler_unavailable") setPage("models");
    }
  };
  const createProject = async (name: string) => { await api.createProject(name); await refreshLibrary(); };

  const content = (() => {
    switch (page) {
      case "create": return <CreatePage key={reuseGeneration?.id ?? `fresh-${defaultUpscaler}-${creationRevision}`} status={status} projects={projects} generations={generations} activeJob={activeJob} activeGeneration={activeGeneration} initial={reuseGeneration} defaultUpscaler={defaultUpscaler} onGenerate={generate} onCancel={cancel} onShowResult={setSelectedGeneration} />;
      case "history": return <HistoryPage generations={generations} onOpen={setSelectedGeneration} />;
      case "projects": return <ProjectsPage projects={projects} generations={generations} onCreate={createProject} />;
      case "models": return <ModelsPage />;
      case "settings": return <SettingsPage status={status} onRefreshStatus={refreshStatus} onSettingsSaved={(settings: LocalSettings) => setDefaultUpscaler(settings.default_upscaler ?? "original")} />;
      case "spaces": return <SpacesPage />;
      default: return <HomePage status={status} generations={generations} onNavigate={setPage} onOpenGeneration={setSelectedGeneration} />;
    }
  })();

  return (
    <Layout onNewCreation={() => { setReuseGeneration(null); setCreationRevision((value) => value + 1); setPage("create"); }} page={page} onNavigate={(next) => { setPage(next); if (next !== "create") setReuseGeneration(null); }} status={status}>
      {backendError && <div className="connection-error"><span>{backendError}</span><button onClick={() => { refreshStatus(); void refreshLibrary(); }}>Retry</button></div>}
      {content}
      {selectedGeneration && <ResultPanel generation={selectedGeneration} status={status} onClose={() => setSelectedGeneration(null)} onReuse={reuse} onUpscale={upscale} onDelete={deleteGeneration} onOpen={openGeneration} onModels={() => { setSelectedGeneration(null); setPage("models"); }} />}
    </Layout>
  );
}

export default App;
