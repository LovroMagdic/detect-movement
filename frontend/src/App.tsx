import { useEffect, useMemo, useRef, useState } from "react";

import LayerViewer from "./components/LayerViewer";
import { artifactUrl, createJob, getJobStatus, LayerMode, type JobStatus } from "./api/client";

function formatDuration(ms: number): string {
  const totalSeconds = Math.max(0, Math.floor(ms / 1000));
  const minutes = Math.floor(totalSeconds / 60);
  const seconds = totalSeconds % 60;
  if (minutes === 0) return `${seconds}s`;
  return `${minutes}m ${seconds}s`;
}

function stepGlyph(state: "pending" | "running" | "done" | "failed"): string {
  if (state === "done") return "OK";
  if (state === "running") return "...";
  if (state === "failed") return "ERR";
  return "--";
}

const TERMINAL_STATUSES = new Set(["finished", "failed", "stopped", "canceled", "cancelled"]);

export default function App() {
  const [file, setFile] = useState<File | null>(null);
  const [jobId, setJobId] = useState<string | null>(null);
  const [status, setStatus] = useState<JobStatus | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [layerMode, setLayerMode] = useState<LayerMode>("both");
  const [jobStartedAt, setJobStartedAt] = useState<number | null>(null);
  const [lastPolledAt, setLastPolledAt] = useState<number | null>(null);
  const [clockNow, setClockNow] = useState<number>(Date.now());
  const pollingRef = useRef<number | null>(null);

  const normalizedStatus = (status?.status ?? "").toLowerCase();
  const canStart = !!file;
  const isDone = normalizedStatus === "finished";
  const isFailed = normalizedStatus === "failed";
  const isTerminal = TERMINAL_STATUSES.has(normalizedStatus);
  const isPending = !!jobId && !isTerminal;
  const statusText = status?.status ?? "loading";
  const progressPct = status?.progress != null ? Math.max(0, Math.min(100, Math.round(status.progress * 100))) : null;
  const elapsedMs = jobStartedAt ? clockNow - jobStartedAt : 0;
  const heartbeatAgeMs = lastPolledAt ? clockNow - lastPolledAt : null;

  const mapUrl = useMemo(() => (jobId ? artifactUrl(jobId, "map") : ""), [jobId]);
  const heatmapUrl = useMemo(() => (jobId ? artifactUrl(jobId, "heatmap") : ""), [jobId]);

  useEffect(() => {
    if (!isPending) return;
    const timer = window.setInterval(() => setClockNow(Date.now()), 1000);
    return () => window.clearInterval(timer);
  }, [isPending]);

  useEffect(() => {
    if (!jobId) return;
    const tick = async () => {
      try {
        const s = await getJobStatus(jobId);
        setStatus(s);
        setLastPolledAt(Date.now());
        if (TERMINAL_STATUSES.has((s.status ?? "").toLowerCase())) {
          if (pollingRef.current) {
            window.clearInterval(pollingRef.current);
            pollingRef.current = null;
          }
        }
      } catch (e) {
        setError((e as Error).message);
      }
    };
    void tick();
    pollingRef.current = window.setInterval(() => void tick(), 1500);
    return () => {
      if (pollingRef.current) {
        window.clearInterval(pollingRef.current);
        pollingRef.current = null;
      }
    };
  }, [jobId]);

  async function onSubmit(e: React.FormEvent) {
    e.preventDefault();
    if (!file) return;
    setError(null);
    setStatus(null);
    setLastPolledAt(null);
    setClockNow(Date.now());
    const created = await createJob(file);
    setJobStartedAt(Date.now());
    setJobId(created.job_id);
  }

  return (
    <main className="app-shell">
      <h1>Detect Motion Map Pipeline</h1>
      <form className="upload-form" onSubmit={(e) => void onSubmit(e)}>
        <input
          type="file"
          accept="video/*"
          onChange={(e) => setFile(e.target.files?.[0] ?? null)}
        />
        <button disabled={!canStart} type="submit">
          Upload and Process
        </button>
      </form>

      {jobId && (
        <section className="status-card">
          <div>Job: {jobId}</div>
          <div>
            Status:{" "}
            <span className={`status-pill ${isDone ? "ok" : isFailed ? "failed" : "running"}`}>{statusText}</span>
          </div>
          <div>Stage: {status?.stage ?? "-"}</div>
          <div>Detail: {status?.stage_detail ?? "-"}</div>
          <div>Progress: {progressPct != null ? `${progressPct}%` : "-"}</div>
          {isPending && (
            <div className="status-subtle">
              Elapsed: {formatDuration(elapsedMs)} | Last backend check:{" "}
              {heartbeatAgeMs != null ? `${formatDuration(heartbeatAgeMs)} ago` : "waiting..."}
            </div>
          )}
          {!!status?.steps?.length && (
            <div className="steps-list">
              {status.steps.map((step) => (
                <div key={step.key} className={`step-row ${step.state}`}>
                  <span className="step-icon">{stepGlyph(step.state)}</span>
                  <span>{step.label}</span>
                </div>
              ))}
            </div>
          )}
          {status?.error && <div className="error">{status.error}</div>}
        </section>
      )}

      {error && <p className="error">{error}</p>}

      {isPending && (
        <section className="results-section">
          <div className="viewer-placeholder processing-box">
            <div className="processing-line">
              <span className="pulse-dot" />
              Job is processing in the worker container.
            </div>
            <div className="progress-track">
              <div
                className={`progress-fill ${progressPct == null ? "indeterminate" : ""}`}
                style={progressPct != null ? { width: `${progressPct}%` } : undefined}
              />
            </div>
            <div className="status-subtle">
              Stage: {status?.stage ?? "queued"} | {status?.stage_detail ?? "Working..."} | Polling every 1.5s.
              {heartbeatAgeMs != null ? ` Last successful poll ${formatDuration(heartbeatAgeMs)} ago.` : ""}
            </div>
          </div>
        </section>
      )}

      {isDone && (
        <section className="results-section">
          <div className="layer-buttons">
            <button onClick={() => setLayerMode("none")}>None</button>
            <button onClick={() => setLayerMode("map")}>Map</button>
            <button onClick={() => setLayerMode("heatmap")}>Heatmap</button>
            <button onClick={() => setLayerMode("both")}>Both</button>
          </div>
          {layerMode === "none" ? (
            <div className="viewer-placeholder">Layer mode is set to none.</div>
          ) : (
            <LayerViewer mapUrl={mapUrl} heatmapUrl={heatmapUrl} mode={layerMode} />
          )}
        </section>
      )}
    </main>
  );
}

