import {
  Boxes,
  Clock3,
  FolderKanban,
  Home,
  Layers3,
  Plus,
  Settings,
  Sparkles,
} from "lucide-react";
import { useEffect, useRef, type ReactNode } from "react";
import type { Page, SystemStatus } from "../types/api";
import { StatusBadge } from "./ui/StatusBadge";

const navItems: Array<{ id: Page; label: string; icon: typeof Home }> = [
  { id: "home", label: "Home", icon: Home },
  { id: "create", label: "Create", icon: Sparkles },
  { id: "spaces", label: "Spaces", icon: Boxes },
  { id: "projects", label: "Projects", icon: FolderKanban },
  { id: "history", label: "History", icon: Clock3 },
  { id: "models", label: "Models", icon: Layers3 },
];

interface LayoutProps {
  page: Page;
  onNavigate: (page: Page) => void;
  onNewCreation: () => void;
  status: SystemStatus | null;
  children: ReactNode;
}

export function Layout({ page, onNavigate, onNewCreation, status, children }: LayoutProps) {
  const contentRef = useRef<HTMLElement>(null);
  useEffect(() => { contentRef.current?.scrollTo({ top: 0 }); }, [page]);
  return (
    <div className="app-shell">
      <aside className="sidebar">
        <button
          className="brand"
          onClick={() => onNavigate("home")}
          aria-label="H3 Local Studio home"
        >
          <span className="brand-mark">H3</span>
          <span className="brand-copy">
            <strong>Local Studio</strong>
            <small>Your private creative suite</small>
          </span>
        </button>
        <nav className="main-nav" aria-label="Main navigation">
          {navItems.map(({ id, label, icon: Icon }) => (
            <button
              key={id}
              aria-label={label}
              aria-current={page === id ? "page" : undefined}
              title={label}
              className={page === id ? "active" : ""}
              onClick={() => onNavigate(id)}
            >
              <Icon size={19} strokeWidth={1.8} />
              <span>{label}</span>
            </button>
          ))}
        </nav>
        <div className="sidebar-bottom">
          <button
            className={page === "settings" ? "active" : ""}
            aria-label="Settings"
            aria-current={page === "settings" ? "page" : undefined}
            onClick={() => onNavigate("settings")}
          >
            <Settings size={19} strokeWidth={1.8} />
            <span>Settings</span>
          </button>
          <div className="engine-card">
            <div className="engine-icon">
              <Layers3 size={18} />
            </div>
            <div>
              <span>Local engine</span>
              <small>{status?.gpu.name ?? "Checking hardware"}</small>
            </div>
            <span
              className={`engine-light ${status?.gpu.available ? "online" : ""}`}
            />
          </div>
        </div>
      </aside>
      <section className="workspace">
        <header className="topbar">
          <div className="mode-tabs">
            <button
              className={page === "create" ? "active" : ""}
              onClick={() => onNavigate("create")}
            >
              Studio
            </button>
            <button
              className={page === "spaces" ? "active" : ""}
              onClick={() => onNavigate("spaces")}
            >
              Spaces
            </button>
          </div>
          <div className="topbar-actions">
            {status ? (
              <StatusBadge
                ok
                label={status.app.mock_mode ? "Mock Mode" : "Local GPU Mode"}
                muted={status.app.mock_mode}
              />
            ) : null}
            <StatusBadge
              ok={Boolean(status?.comfyui.running)}
              label={
                status?.comfyui.running ? "ComfyUI online" : "ComfyUI offline"
              }
            />
            <button className="new-create" onClick={() => { onNewCreation(); contentRef.current?.scrollTo({ top: 0 }); }}>
              <Plus size={17} /> New creation
            </button>
          </div>
        </header>
        <main className="page-content" ref={contentRef}>{children}</main>
      </section>
    </div>
  );
}
