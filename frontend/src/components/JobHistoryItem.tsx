import type { JobListItem } from "../api/client";

interface JobHistoryItemProps {
  job: JobListItem;
  isActive: boolean;
  onSelect: () => void;
  onDelete: () => void;
}

function formatRelativeTime(iso: string): string {
  const date = new Date(iso);
  const diffMs = Date.now() - date.getTime();
  const minutes = Math.floor(diffMs / 60000);
  if (minutes < 1) return "just now";
  if (minutes < 60) return `${minutes}m ago`;
  const hours = Math.floor(minutes / 60);
  if (hours < 24) return `${hours}h ago`;
  const days = Math.floor(hours / 24);
  if (days < 7) return `${days}d ago`;
  return date.toLocaleDateString();
}

function statusLabel(status: string): string {
  const normalized = status.toLowerCase();
  if (normalized === "finished") return "Complete";
  if (normalized === "failed") return "Failed";
  if (normalized === "incomplete") return "Incomplete";
  if (["queued", "deferred", "scheduled", "started"].includes(normalized)) return "Running";
  return status;
}

function statusClass(status: string): string {
  const normalized = status.toLowerCase();
  if (normalized === "finished") return "ok";
  if (normalized === "failed") return "failed";
  if (normalized === "incomplete") return "muted";
  return "running";
}

export default function JobHistoryItem({ job, isActive, onSelect, onDelete }: JobHistoryItemProps) {
  return (
    <div
      className={`history-item ${isActive ? "active" : ""}`}
      role="button"
      tabIndex={0}
      onClick={onSelect}
      onKeyDown={(e) => {
        if (e.key === "Enter" || e.key === " ") {
          e.preventDefault();
          onSelect();
        }
      }}
    >
      <div className="history-item-content">
        <div className="history-thumb" aria-hidden>
          <span className="history-thumb-fallback">VID</span>
        </div>
        <div className="history-item-body">
          <span className="history-filename" title={job.filename}>
            {job.filename}
          </span>
          <span className="history-meta">
            <span className={`status-pill ${statusClass(job.status)}`}>{statusLabel(job.status)}</span>
            <span className="history-date">{formatRelativeTime(job.updated_at)}</span>
          </span>
        </div>
      </div>
      <button
        type="button"
        className="history-item-delete"
        onClick={(e) => {
          e.stopPropagation();
          onDelete();
        }}
        aria-label={`Delete ${job.filename}`}
        title="Delete from history"
      >
        x
      </button>
    </div>
  );
}
