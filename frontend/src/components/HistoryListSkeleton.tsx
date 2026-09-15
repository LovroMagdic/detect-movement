import HistoryItemSkeleton from "./HistoryItemSkeleton";

export default function HistoryListSkeleton({ rows = 5 }: { rows?: number }) {
  return (
    <div className="history-list-skeleton" aria-hidden="true">
      {Array.from({ length: rows }, (_, i) => (
        <HistoryItemSkeleton key={i} />
      ))}
    </div>
  );
}
