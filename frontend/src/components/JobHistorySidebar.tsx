import HistoryItemSkeleton from "./HistoryItemSkeleton";
import HistoryListSkeleton from "./HistoryListSkeleton";
import JobHistoryItem from "./JobHistoryItem";
import type { JobListItem } from "../api/client";

export interface PendingUploadItem {
  clientId: string;
  filename: string;
}

interface JobHistorySidebarProps {
  jobs: JobListItem[];
  pendingUploads: PendingUploadItem[];
  deletingJobIds: ReadonlySet<string>;
  activeJobId: string | null;
  searchQuery: string;
  onSearchChange: (value: string) => void;
  onSearchSubmit: () => void;
  onSelect: (jobId: string) => void;
  onDelete: (jobId: string) => void;
  onLoadMore: () => void;
  hasMore: boolean;
  loading: boolean;
}

export default function JobHistorySidebar({
  jobs,
  pendingUploads,
  deletingJobIds,
  activeJobId,
  searchQuery,
  onSearchChange,
  onSearchSubmit,
  onSelect,
  onDelete,
  onLoadMore,
  hasMore,
  loading
}: JobHistorySidebarProps) {
  return (
    <aside className="job-history-sidebar">
      <div className="history-sidebar-header">
        <h2 className="upload-panel-title">Job history</h2>
        <p className="status-subtle">Previous runs stored in the database</p>
      </div>
      <input
        type="search"
        className="history-search"
        placeholder="Search by filename..."
        value={searchQuery}
        onChange={(e) => onSearchChange(e.target.value)}
        onKeyDown={(e) => {
          if (e.key === "Enter") {
            e.preventDefault();
            onSearchSubmit();
          }
        }}
        aria-label="Search jobs"
      />
      <div className="history-list" role="list">
        {loading && <HistoryListSkeleton />}
        {!loading && jobs.length === 0 && pendingUploads.length === 0 && (
          <p className="status-subtle">
            {searchQuery.trim() ? "No jobs match your search." : "No jobs found. Upload a video to get started."}
          </p>
        )}
        {!loading &&
          pendingUploads.map((pending) => (
            <HistoryItemSkeleton
              key={pending.clientId}
              isActive={pending.clientId === activeJobId}
              label={`Uploading ${pending.filename}`}
            />
          ))}
        {!loading &&
          jobs.map((job) =>
            deletingJobIds.has(job.job_id) ? (
              <HistoryItemSkeleton key={job.job_id} label="Deleting job" />
            ) : (
              <JobHistoryItem
                key={job.job_id}
                job={job}
                isActive={job.job_id === activeJobId}
                onSelect={() => onSelect(job.job_id)}
                onDelete={() => onDelete(job.job_id)}
              />
            )
          )}
      </div>
      {hasMore && !loading && (
        <button type="button" className="history-load-more" onClick={onLoadMore}>
          Load more
        </button>
      )}
    </aside>
  );
}
