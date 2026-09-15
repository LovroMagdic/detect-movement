import { useCallback, useEffect, useMemo, useRef, useState } from "react";

import JobDetailPanel, { type LayerPrefs } from "./components/JobDetailPanel";
import JobHistorySidebar, { type PendingUploadItem } from "./components/JobHistorySidebar";
import UploadPanel from "./components/UploadPanel";
import {
  createJob,
  deleteJob,
  getJobStatus,
  listJobs,
  type JobListItem,
  type JobStatus,
  type WatermarkRect
} from "./api/client";
import { useConfirm } from "./context/ConfirmContext";
import { useToast } from "./context/ToastContext";

const PAGE_SIZE = 50;
const TERMINAL_STATUSES = new Set(["finished", "failed", "stopped", "canceled", "cancelled", "incomplete", "unknown"]);

const DEFAULT_LAYER_PREFS: LayerPrefs = {
  showImageLayer: true,
  showMaskLayer: true,
  showForestLayer: false
};

export default function App() {
  const { showError } = useToast();
  const { confirm } = useConfirm();

  const [historyJobs, setHistoryJobs] = useState<JobListItem[]>([]);
  const [historyTotal, setHistoryTotal] = useState(0);
  const [historyOffset, setHistoryOffset] = useState(0);
  const [historyLoading, setHistoryLoading] = useState(false);
  const [searchQuery, setSearchQuery] = useState("");
  const [selectedJobId, setSelectedJobId] = useState<string | null>(null);
  const [detailLoading, setDetailLoading] = useState(false);
  const [statusCache, setStatusCache] = useState<Record<string, JobStatus>>({});
  const [pollMeta, setPollMeta] = useState<Record<string, { startedAt: number; lastPolledAt: number | null }>>({});
  const [layerPrefs, setLayerPrefs] = useState<Record<string, LayerPrefs>>({});
  const [clockNow, setClockNow] = useState(Date.now());
  const searchDebounceRef = useRef<number | null>(null);
  const skipSearchDebounceRef = useRef(true);
  const historyFetchIdRef = useRef(0);
  const detailFetchIdRef = useRef(0);
  const toastedPollErrorsRef = useRef<Set<string>>(new Set());
  const toastedFailedJobsRef = useRef<Set<string>>(new Set());
  const prevStatusRef = useRef<Record<string, string>>({});
  const [listItemCache, setListItemCache] = useState<Record<string, JobListItem>>({});
  const [deletingJobIds, setDeletingJobIds] = useState<ReadonlySet<string>>(() => new Set());
  const [pendingUploads, setPendingUploads] = useState<PendingUploadItem[]>([]);
  const statusCacheRef = useRef(statusCache);
  const pendingUploadIds = useMemo(() => new Set(pendingUploads.map((p) => p.clientId)), [pendingUploads]);
  statusCacheRef.current = statusCache;

  const isPendingUploadSelection = selectedJobId != null && pendingUploadIds.has(selectedJobId);

  const selectedListItem = useMemo(() => {
    if (!selectedJobId || deletingJobIds.has(selectedJobId) || pendingUploadIds.has(selectedJobId)) {
      return null;
    }
    return historyJobs.find((j) => j.job_id === selectedJobId) ?? listItemCache[selectedJobId] ?? null;
  }, [historyJobs, selectedJobId, listItemCache, deletingJobIds, pendingUploadIds]);

  const selectedStatus = selectedJobId ? statusCache[selectedJobId] ?? null : null;
  const selectedLayerPrefs = selectedJobId
    ? (layerPrefs[selectedJobId] ?? DEFAULT_LAYER_PREFS)
    : DEFAULT_LAYER_PREFS;
  const selectedPollMeta = selectedJobId ? pollMeta[selectedJobId] : null;

  const sidebarJobs = useMemo(
    () =>
      historyJobs.map((job) => {
        const live = statusCache[job.job_id];
        if (!live) return job;
        return { ...job, status: live.status };
      }),
    [historyJobs, statusCache]
  );

  const pendingJobIds = useMemo(
    () =>
      historyJobs
        .filter((job) => {
          if (deletingJobIds.has(job.job_id)) return false;
          const st = (statusCache[job.job_id]?.status ?? job.status).toLowerCase();
          return !TERMINAL_STATUSES.has(st);
        })
        .map((job) => job.job_id),
    [historyJobs, statusCache, deletingJobIds]
  );

  const hasAnyPending = pendingJobIds.length > 0;
  const hasMoreHistory = historyJobs.length < historyTotal;

  const fetchHistory = useCallback(
    async (opts: { offset?: number; append?: boolean; q?: string } = {}) => {
      const offset = opts.offset ?? 0;
      const append = opts.append ?? false;
      const q = opts.q?.trim() || undefined;
      const fetchId = ++historyFetchIdRef.current;

      if (!append) {
        setHistoryJobs([]);
        setHistoryTotal(0);
      }
      setHistoryLoading(true);
      try {
        const res = await listJobs({ limit: PAGE_SIZE, offset, q });
        if (fetchId !== historyFetchIdRef.current) return;

        setHistoryTotal(res.total);
        setHistoryOffset(offset + res.jobs.length);
        setHistoryJobs((prev) => (append ? [...prev, ...res.jobs] : res.jobs));

        setListItemCache((prev) => {
          const next = { ...prev };
          for (const job of res.jobs) next[job.job_id] = job;
          return next;
        });

      } catch (loadErr) {
        if (fetchId !== historyFetchIdRef.current) return;
        showError((loadErr as Error).message);
      } finally {
        if (fetchId === historyFetchIdRef.current) {
          setHistoryLoading(false);
        }
      }
    },
    [showError]
  );

  const runSearch = useCallback(() => {
    if (searchDebounceRef.current) {
      window.clearTimeout(searchDebounceRef.current);
      searchDebounceRef.current = null;
    }
    void fetchHistory({ q: searchQuery });
  }, [fetchHistory, searchQuery]);

  const loadJobDetail = useCallback(
    async (jobId: string, opts?: { force?: boolean }) => {
      if (!opts?.force && statusCacheRef.current[jobId]) {
        setDetailLoading(false);
        return;
      }

      const fetchId = ++detailFetchIdRef.current;
      setDetailLoading(true);
      try {
        const nextStatus = await getJobStatus(jobId);
        if (fetchId !== detailFetchIdRef.current) return;
        setStatusCache((prev) => ({ ...prev, [jobId]: nextStatus }));
        toastedPollErrorsRef.current.delete(jobId);
        setHistoryJobs((prev) =>
          prev.map((j) => (j.job_id === jobId ? { ...j, status: nextStatus.status } : j))
        );
        setListItemCache((prev) => {
          const existing = prev[jobId];
          if (!existing) return prev;
          return { ...prev, [jobId]: { ...existing, status: nextStatus.status } };
        });
      } catch (statusErr) {
        if (fetchId !== detailFetchIdRef.current) return;
        showError((statusErr as Error).message);
      } finally {
        if (fetchId === detailFetchIdRef.current) {
          setDetailLoading(false);
        }
      }
    },
    [showError]
  );

  useEffect(() => {
    void fetchHistory();
  }, [fetchHistory]);

  useEffect(() => {
    if (skipSearchDebounceRef.current) {
      skipSearchDebounceRef.current = false;
      return;
    }
    if (searchDebounceRef.current) window.clearTimeout(searchDebounceRef.current);
    searchDebounceRef.current = window.setTimeout(() => {
      void fetchHistory({ q: searchQuery });
    }, 400);
    return () => {
      if (searchDebounceRef.current) window.clearTimeout(searchDebounceRef.current);
    };
  }, [searchQuery, fetchHistory]);

  useEffect(() => {
    if (!selectedJobId) {
      setDetailLoading(false);
      return;
    }
    if (pendingUploadIds.has(selectedJobId)) {
      return;
    }
    const fromList = historyJobs.find((j) => j.job_id === selectedJobId);
    if (fromList) {
      setListItemCache((prev) => ({ ...prev, [selectedJobId]: fromList }));
    }
    if (statusCacheRef.current[selectedJobId]) {
      setDetailLoading(false);
      return;
    }
    void loadJobDetail(selectedJobId);
  }, [selectedJobId, loadJobDetail, historyJobs, pendingUploadIds]);

  useEffect(() => {
    if (!hasAnyPending) return;
    const timer = window.setInterval(() => setClockNow(Date.now()), 1000);
    return () => window.clearInterval(timer);
  }, [hasAnyPending]);

  useEffect(() => {
    for (const [jobId, status] of Object.entries(statusCache)) {
      const normalized = status.status.toLowerCase();
      const prev = prevStatusRef.current[jobId];
      prevStatusRef.current[jobId] = normalized;

      if (normalized === "failed" && prev !== "failed" && status.error && !toastedFailedJobsRef.current.has(jobId)) {
        toastedFailedJobsRef.current.add(jobId);
        showError(status.error);
      }
    }
  }, [statusCache, showError]);

  useEffect(() => {
    if (!pendingJobIds.length) return;
    let cancelled = false;

    const tick = async () => {
      const updates = await Promise.all(
        pendingJobIds.map(async (jobId) => {
          try {
            const nextStatus = await getJobStatus(jobId);
            return { jobId, nextStatus, polledAt: Date.now(), pollError: null as string | null };
          } catch (pollErr) {
            return { jobId, nextStatus: null, polledAt: null, pollError: (pollErr as Error).message };
          }
        })
      );

      if (cancelled) return;

      setStatusCache((prev) => {
        const next = { ...prev };
        for (const u of updates) {
          if (u.nextStatus) next[u.jobId] = u.nextStatus;
        }
        return next;
      });

      for (const u of updates) {
        if (u.pollError) {
          if (!toastedPollErrorsRef.current.has(u.jobId)) {
            toastedPollErrorsRef.current.add(u.jobId);
            showError(u.pollError);
          }
        } else {
          toastedPollErrorsRef.current.delete(u.jobId);
        }
      }

      setPollMeta((prev) => {
        const next = { ...prev };
        for (const u of updates) {
          const existing = next[u.jobId] ?? { startedAt: Date.now(), lastPolledAt: null };
          next[u.jobId] = { ...existing, lastPolledAt: u.polledAt };
        }
        return next;
      });

      setHistoryJobs((prev) =>
        prev.map((job) => {
          const u = updates.find((item) => item.jobId === job.job_id);
          if (!u?.nextStatus) return job;
          return { ...job, status: u.nextStatus.status };
        })
      );
    };

    void tick();
    const timer = window.setInterval(() => void tick(), 1500);
    return () => {
      cancelled = true;
      window.clearInterval(timer);
    };
  }, [pendingJobIds.join("|"), showError]);

  function handleSelectJob(jobId: string) {
    if (pendingUploadIds.has(jobId) || deletingJobIds.has(jobId)) return;
    const item = historyJobs.find((j) => j.job_id === jobId);
    if (item) {
      setListItemCache((prev) => ({ ...prev, [jobId]: item }));
    }
    setSelectedJobId(jobId);
    if (statusCacheRef.current[jobId]) {
      setDetailLoading(false);
    } else {
      setDetailLoading(true);
    }
  }

  async function handleUpload(
    file: File,
    options: { useWatermarkZone: boolean; watermarkRect: WatermarkRect | null }
  ) {
    const clientId = `pending-${crypto.randomUUID()}`;
    setPendingUploads((prev) => [{ clientId, filename: file.name }, ...prev]);
    setSelectedJobId(clientId);
    setDetailLoading(true);

    try {
      const created = await createJob(file, options);
      const startedAt = Date.now();
      const newItem: JobListItem = {
        job_id: created.job_id,
        filename: file.name,
        updated_at: new Date(startedAt).toISOString(),
        status: created.status
      };
      setPendingUploads((prev) => prev.filter((p) => p.clientId !== clientId));
      setHistoryJobs((prev) => [newItem, ...prev.filter((j) => j.job_id !== created.job_id)]);
      setListItemCache((prev) => ({ ...prev, [created.job_id]: newItem }));
      setHistoryTotal((t) => t + 1);
      setSelectedJobId(created.job_id);
      setPollMeta((prev) => ({
        ...prev,
        [created.job_id]: { startedAt, lastPolledAt: null }
      }));
      setLayerPrefs((prev) => ({ ...prev, [created.job_id]: { ...DEFAULT_LAYER_PREFS } }));
      toastedPollErrorsRef.current.delete(created.job_id);
      toastedFailedJobsRef.current.delete(created.job_id);
    } catch (submitErr) {
      setPendingUploads((prev) => prev.filter((p) => p.clientId !== clientId));
      setSelectedJobId((current) => (current === clientId ? null : current));
      setDetailLoading(false);
      showError((submitErr as Error).message);
      throw submitErr;
    }
  }

  async function handleDeleteJob(jobId: string) {
    const item = historyJobs.find((j) => j.job_id === jobId) ?? listItemCache[jobId];
    const label = item?.filename ?? jobId;
    const ok = await confirm({
      title: "Delete from history?",
      message: `Delete "${label}"? This cannot be undone.`,
      confirmLabel: "Delete",
      cancelLabel: "Cancel",
      variant: "danger"
    });
    if (!ok) return;

    setDeletingJobIds((prev) => new Set(prev).add(jobId));
    setSelectedJobId((current) => (current === jobId ? null : current));
    if (selectedJobId === jobId) {
      setDetailLoading(false);
    }

    try {
      await deleteJob(jobId);
      setHistoryJobs((prev) => prev.filter((j) => j.job_id !== jobId));
      setHistoryTotal((t) => Math.max(0, t - 1));
      setStatusCache((prev) => {
        const next = { ...prev };
        delete next[jobId];
        return next;
      });
      setListItemCache((prev) => {
        const next = { ...prev };
        delete next[jobId];
        return next;
      });
      setPollMeta((prev) => {
        const next = { ...prev };
        delete next[jobId];
        return next;
      });
      setLayerPrefs((prev) => {
        const next = { ...prev };
        delete next[jobId];
        return next;
      });
      toastedPollErrorsRef.current.delete(jobId);
      toastedFailedJobsRef.current.delete(jobId);
      delete prevStatusRef.current[jobId];
    } catch (deleteErr) {
      showError((deleteErr as Error).message);
    } finally {
      setDeletingJobIds((prev) => {
        const next = new Set(prev);
        next.delete(jobId);
        return next;
      });
    }
  }

  function handleToggleLayer(kind: "image" | "mask" | "forest") {
    if (!selectedJobId) return;
    setLayerPrefs((prev) => {
      const current = prev[selectedJobId] ?? DEFAULT_LAYER_PREFS;
      if (kind === "image") return { ...prev, [selectedJobId]: { ...current, showImageLayer: !current.showImageLayer } };
      if (kind === "mask") return { ...prev, [selectedJobId]: { ...current, showMaskLayer: !current.showMaskLayer } };
      return { ...prev, [selectedJobId]: { ...current, showForestLayer: !current.showForestLayer } };
    });
  }

  return (
    <main className="app-shell">
      <header className="app-header">
        <h1>Forest Map</h1>
        <p className="status-subtle">Upload drone video, browse past runs, and inspect forest maps.</p>
      </header>

      <UploadPanel onSubmit={(file, opts) => void handleUpload(file, opts)} />

      <div className="workspace-layout">
        <JobHistorySidebar
          jobs={sidebarJobs}
          pendingUploads={pendingUploads}
          deletingJobIds={deletingJobIds}
          activeJobId={selectedJobId}
          searchQuery={searchQuery}
          onSearchChange={setSearchQuery}
          onSearchSubmit={runSearch}
          onSelect={handleSelectJob}
          onDelete={(jobId) => void handleDeleteJob(jobId)}
          onLoadMore={() => void fetchHistory({ offset: historyOffset, append: true, q: searchQuery })}
          hasMore={hasMoreHistory}
          loading={historyLoading}
        />

        <JobDetailPanel
          listItem={selectedListItem}
          status={selectedStatus}
          loading={detailLoading || isPendingUploadSelection}
          layerPrefs={selectedLayerPrefs}
          onToggleLayer={handleToggleLayer}
          onDelete={() => selectedJobId && void handleDeleteJob(selectedJobId)}
          clockNow={clockNow}
          startedAt={selectedPollMeta?.startedAt ?? null}
          lastPolledAt={selectedPollMeta?.lastPolledAt ?? null}
        />
      </div>
    </main>
  );
}
