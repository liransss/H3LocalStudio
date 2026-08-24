import { Boxes, GitBranch, LockKeyhole, Play } from "lucide-react";

export function SpacesPage() {
  return (
    <div className="spaces-page">
      <div className="spaces-grid-bg" />
      <div className="spaces-toolbar"><span><Boxes size={16} /> Untitled space</span><div><button disabled><Play size={14} /> Run workflow</button><button disabled>Save</button></div></div>
      <div className="node-ghost node-input"><span>INPUT</span><strong>Prompt</strong><p>A cinematic scene…</p><i /></div>
      <div className="node-link link-one" />
      <div className="node-ghost node-h3"><span>MINIMAX H3</span><strong>H3 Text to Video</strong><p>Balanced · 1344 × 768</p><i /></div>
      <div className="node-link link-two" />
      <div className="node-ghost node-output"><span>OUTPUT</span><strong>Video Preview</strong><div className="node-preview"><Play size={20} /></div></div>
      <div className="spaces-coming"><div><LockKeyhole size={22} /></div><span className="eyebrow">Coming later</span><h1>Spaces is architected,<br />not pretending.</h1><p>The workflow JSON API, validation, and storage are ready. The interactive canvas stays disabled while native H3 T2V completes hardware validation.</p><span className="spaces-principle"><GitBranch size={15} /> High-level creative graphs, not a ComfyUI clone</span></div>
    </div>
  );
}
