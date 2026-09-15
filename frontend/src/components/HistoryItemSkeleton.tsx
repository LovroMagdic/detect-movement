interface HistoryItemSkeletonProps {
  isActive?: boolean;
  label?: string;
}

export default function HistoryItemSkeleton({ isActive = false, label = "Loading job" }: HistoryItemSkeletonProps) {
  return (
    <div
      className={`history-item history-item-skeleton${isActive ? " active" : ""}`}
      role="listitem"
      aria-busy="true"
      aria-label={label}
    >
      <div className="history-skeleton-row history-item-skeleton-inner">
        <div className="skeleton skeleton-thumb" />
        <div className="history-skeleton-body">
          <div className="skeleton skeleton-line skeleton-line-title" />
          <div className="skeleton skeleton-line skeleton-line-short" />
        </div>
      </div>
    </div>
  );
}
