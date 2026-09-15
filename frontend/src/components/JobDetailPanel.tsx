import JobDetailSkeleton from "./JobDetailSkeleton";
import LayerViewer from "./LayerViewer";
import { artifactUrl, type JobListItem, type JobStatus } from "../api/client";

const TERMINAL_STATUSES = new Set(["finished", "failed", "stopped", "canceled", "cancelled", "incomplete", "unknown"]);

export interface LayerPrefs {
  showImageLayer: boolean;
  showMaskLayer: boolean;
  showForestLayer: boolean;
}

interface JobDetailPanelProps {
  listItem: JobListItem | null;
  status: JobStatus | null;
  loading: boolean;
  layerPrefs: LayerPrefs;
  onToggleLayer: (kind: "image" | "mask" | "forest") => void;
  onDelete: () => void;
  clockNow: number;
  startedAt: number | null;
  lastPolledAt: number | null;
}

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

function jobHasMapResults(status: JobStatus | null): boolean {
  if (!status || status.status.toLowerCase() !== "finished") return false;
  return Boolean(status.artifacts?.map);
}

export default function JobDetailPanel({
  listItem,
  status,
  loading,
  layerPrefs,
  onToggleLayer,
  onDelete,
  clockNow,
  startedAt,
  lastPolledAt
}: JobDetailPanelProps) {
  if (loading) {
    return <JobDetailSkeleton />;
  }

  if (!listItem) {
    return (
      <section className="job-detail-panel empty">
        <p className="status-subtle">Select a job from the history list to view status and results.</p>
      </section>
    );
  }

  const normalizedStatus = (status?.status ?? listItem.status).toLowerCase();
  const isDone = normalizedStatus === "finished";
  const isFailed = normalizedStatus === "failed";
  const isIncomplete = normalizedStatus === "incomplete";
  const isTerminal = TERMINAL_STATUSES.has(normalizedStatus);
  const isPending = !isTerminal;
  const statusText = status?.status ?? listItem.status;
  const hasResults = jobHasMapResults(status);
  const progressPct =
    status?.progress != null ? Math.max(0, Math.min(100, Math.round(status.progress * 100))) : null;
  const elapsedMs = startedAt ? clockNow - startedAt : 0;
  const heartbeatAgeMs = lastPolledAt ? clockNow - lastPolledAt : null;

  const mapUrl = artifactUrl(listItem.job_id, "map");
  const heatmapUrl = artifactUrl(listItem.job_id, "heatmap");
  const forestOverlayUrl = artifactUrl(listItem.job_id, "forest_overlay");

  return (
    <section className="job-detail-panel">
      <header className="job-detail-header">
        <div>
          <h2 className="job-detail-title">{listItem.filename}</h2>
          <p className="job-detail-id">{listItem.job_id}</p>
        </div>
        <button type="button" className="delete-job-btn" onClick={onDelete}>
          Delete
        </button>
      </header>

      <div className="status-card">
        <div>
          Status:{" "}
          <span className={`status-pill ${isDone ? "ok" : isFailed ? "failed" : isIncomplete ? "muted" : "running"}`}>
            {statusText}
          </span>
        </div>
        <div>Stage: {status?.stage ?? "-"}</div>
        <div>Detail: {status?.stage_detail ?? "-"}</div>
        {progressPct != null && <div>Progress: {progressPct}%</div>}
        {isPending && startedAt && (
          <div className="status-subtle">
            Elapsed: {formatDuration(elapsedMs)} | Last check:{" "}
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
      </div>

      {isPending && (
        <div className="viewer-placeholder processing-box">
          <div className="processing-line">
            <span className="pulse-dot" />
            Processing in worker...
          </div>
          <div className="progress-track">
            <div
              className={`progress-fill ${progressPct == null ? "indeterminate" : ""}`}
              style={progressPct != null ? { width: `${progressPct}%` } : undefined}
            />
          </div>
        </div>
      )}

      {isIncomplete && <div className="viewer-placeholder">No complete results yet for this job.</div>}

      {isDone && hasResults && (
        <div className="results-section">
          <div className="layer-buttons">
            <button
              type="button"
              className={layerPrefs.showImageLayer ? "toggle-active" : ""}
              onClick={() => onToggleLayer("image")}
            >
              Image
            </button>
            <button
              type="button"
              className={layerPrefs.showMaskLayer ? "toggle-active" : ""}
              onClick={() => onToggleLayer("mask")}
            >
              Dead Tree
            </button>
            <button
              type="button"
              className={layerPrefs.showForestLayer ? "toggle-active" : ""}
              onClick={() => onToggleLayer("forest")}
            >
              Segmentation
            </button>
          </div>
          {layerPrefs.showForestLayer && (
            <div className="segmentation-legend" aria-label="Segmentation class colors">
              <span className="legend-item legend-tree">Tree</span>
              <span className="legend-item legend-road">Road</span>
              <span className="legend-item legend-roof">Roof</span>
            </div>
          )}
          {!layerPrefs.showImageLayer && !layerPrefs.showMaskLayer && !layerPrefs.showForestLayer ? (
            <div className="viewer-placeholder">Enable a layer to display the result.</div>
          ) : (
            <LayerViewer
              mapUrl={mapUrl}
              heatmapUrl={heatmapUrl}
              forestOverlayUrl={forestOverlayUrl}
              showMap={layerPrefs.showImageLayer}
              showHeatmap={layerPrefs.showMaskLayer}
              showForest={layerPrefs.showForestLayer}
            />
          )}
        </div>
      )}
    </section>
  );
}

