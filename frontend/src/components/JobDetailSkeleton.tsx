export default function JobDetailSkeleton() {
  return (
    <section className="job-detail-panel job-detail-skeleton" aria-hidden="true">
      <div className="job-detail-header">
        <div className="job-detail-skeleton-titles">
          <div className="skeleton skeleton-line skeleton-line-title-lg" />
          <div className="skeleton skeleton-line skeleton-line-short" />
        </div>
        <div className="skeleton skeleton-btn" />
      </div>
      <div className="status-card skeleton-status-card">
        <div className="skeleton skeleton-line" />
        <div className="skeleton skeleton-line" />
        <div className="skeleton skeleton-line skeleton-line-short" />
      </div>
      <div className="skeleton skeleton-viewer" />
    </section>
  );
}

