import { useEffect, useRef, useState } from "react";
import { api } from "../../api";
import type { Job } from "../../types";
import type { CanvasDrawerNode } from "./types";

/** Polls the node's job (fast while running), auto-scrolls the log box and exposes cancel. */
export function useDrawerJob(node: CanvasDrawerNode | null) {
  const [job, setJob] = useState<Job | null>(null);
  const [loadingJob, setLoadingJob] = useState(false);
  const [stopping, setStopping] = useState(false);
  const logScrollRef = useRef<HTMLDivElement>(null);

  // poll job events when open
  useEffect(() => {
    if (!node?.jobId) {
      setJob(null);
      return;
    }
    let stop = false;
    setLoadingJob(true);

    const fetchJob = async () => {
      try {
        const j = await api.job(node.jobId!);
        if (!stop) {
          setJob(j);
          setLoadingJob(false);
        }
      } catch {
        if (!stop) setLoadingJob(false);
      }
    };

    fetchJob();

    const isRunning = node.status === "running" || node.status === "queued";
    if (isRunning) {
      const t = window.setInterval(fetchJob, 1200);
      return () => {
        stop = true;
        window.clearInterval(t);
      };
    }
    return () => {
      stop = true;
    };
  }, [node?.jobId, node?.status]);

  // auto scroll logs
  useEffect(() => {
    const el = logScrollRef.current;
    if (!el) return;
    const near = el.scrollHeight - el.scrollTop - el.clientHeight < 80;
    if (near) el.scrollTop = el.scrollHeight;
  }, [job?.events?.length]);

  const stopRetry = async () => {
    if (!node?.jobId) return;
    setStopping(true);
    try {
      await api.cancelJob(node.jobId);
    } catch {
      /* the next poll reflects the real state */
    } finally {
      setStopping(false);
    }
  };

  const clearJob = () => setJob(null);

  return { job, loadingJob, clearJob, logScrollRef, stopping, stopRetry };
}
