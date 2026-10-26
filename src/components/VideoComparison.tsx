import { useRef, useState } from "react";

/** The upscaled player is the playback clock; the original is a muted overlay. */
export function VideoComparison({ original, upscaled }: { original: string; upscaled: string }) {
  const [split, setSplit] = useState(50);
  const originalRef = useRef<HTMLVideoElement>(null);
  const upscaledRef = useRef<HTMLVideoElement>(null);
  const synchronize = () => {
    const source = upscaledRef.current;
    const target = originalRef.current;
    if (!source || !target) return;
    if (Math.abs(target.currentTime - source.currentTime) > 0.12) target.currentTime = source.currentTime;
    target.playbackRate = source.playbackRate;
  };
  return <div className="video-comparison">
    <video ref={upscaledRef} src={upscaled} controls playsInline preload="metadata"
      onPlay={() => { synchronize(); void originalRef.current?.play().catch(() => {}); }}
      onPause={() => originalRef.current?.pause()}
      onSeeked={synchronize} onTimeUpdate={synchronize} onRateChange={synchronize}
      onEnded={() => originalRef.current?.pause()} />
    <video ref={originalRef} className="comparison-original" src={original} muted playsInline preload="metadata" aria-hidden="true" tabIndex={-1}
      style={{ clipPath: `inset(0 ${100 - split}% 52px 0)`, pointerEvents: "none" }} onLoadedMetadata={synchronize} />
    <span className="comparison-label left">Original</span><span className="comparison-label right">Upscaled</span>
    <div className="comparison-divider" style={{ left: `${split}%` }} />
    <input className="comparison-range" type="range" min={0} max={100} value={split} onChange={(event) => setSplit(Number(event.target.value))} aria-label="Original and upscaled comparison split" aria-valuetext={`${split}% original, ${100 - split}% upscaled`} />
  </div>;
}
