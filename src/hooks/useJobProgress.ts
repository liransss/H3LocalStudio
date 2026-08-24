import { useEffect, useRef } from "react";
import { api, jobWebSocketUrl } from "../services/api";
import type { Job } from "../types/api";

const terminalStates = new Set(["completed", "failed", "cancelled"]);

export function useJobProgress(jobId: string | null, onProgress: (job: Job) => void): void {
  const callback = useRef(onProgress);
  callback.current = onProgress;

  useEffect(() => {
    if (!jobId) return;
    let closed = false;
    let polling: number | undefined;
    const startPolling = () => {
      if (polling || closed) return;
      polling = window.setInterval(async () => {
        try {
          const job = await api.job(jobId);
          callback.current(job);
          if (terminalStates.has(job.status)) {
            window.clearInterval(polling);
            polling = undefined;
          }
        } catch {
          // The connection banner owns backend availability messaging.
        }
      }, 1000);
    };

    let socket: WebSocket | undefined;
    try {
      socket = new WebSocket(jobWebSocketUrl(jobId));
      socket.onmessage = (event) => callback.current(JSON.parse(event.data) as Job);
      socket.onerror = startPolling;
      socket.onclose = startPolling;
    } catch {
      startPolling();
    }

    return () => {
      closed = true;
      socket?.close();
      if (polling) window.clearInterval(polling);
    };
  }, [jobId]);
}

