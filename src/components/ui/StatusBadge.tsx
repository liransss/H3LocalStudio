interface StatusBadgeProps {
  ok: boolean;
  label: string;
  muted?: boolean;
}

export function StatusBadge({ ok, label, muted = false }: StatusBadgeProps) {
  return (
    <span className={`status-badge ${muted ? "status-muted" : ok ? "status-ok" : "status-warn"}`}>
      <span className="status-dot" />
      {label}
    </span>
  );
}

