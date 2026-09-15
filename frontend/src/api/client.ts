import { apiFetch, parseApiError } from "./errors";

export type LayerMode = "none" | "map" | "heatmap" | "both";

export interface JobStep {
  key: string;
  label: string;
  state: "pending" | "running" | "done" | "failed";
}

export interface JobStatus {
  job_id: string;
  status: string;
  stage?: string;
  stage_detail?: string;
  progress?: number;
  error?: string;
  steps?: JobStep[];
  artifacts?: Record<string, string>;
}

export interface JobListItem {
  job_id: string;
  filename: string;
  status: string;
  updated_at: string;
}

export interface JobSummary {
  job_id: string;
  filename: string;
  created_at: string;
  updated_at: string;
  artifacts: string[];
  has_results: boolean;
  frame_count: number;
  status: string;
}

export interface JobListResponse {
  jobs: JobListItem[];
  total: number;
}

const API_BASE = "http://localhost:8000";

export interface WatermarkRect {
  x: number;
  y: number;
  width: number;
  height: number;
}

export interface CreateJobOptions {
  useWatermarkZone?: boolean;
  watermarkRect?: WatermarkRect | null;
}

export interface ListJobsParams {
  limit?: number;
  offset?: number;
  q?: string;
}

export async function createJob(
  file: File,
  options: CreateJobOptions = {}
): Promise<{ job_id: string; status: string }> {
  const form = new FormData();
  form.append("file", file);
  form.append("use_watermark_zone", options.useWatermarkZone ? "1" : "0");
  if (options.watermarkRect) {
    const rect = options.watermarkRect;
    form.append("watermark_x", String(Math.round(rect.x)));
    form.append("watermark_y", String(Math.round(rect.y)));
    form.append("watermark_width", String(Math.round(rect.width)));
    form.append("watermark_height", String(Math.round(rect.height)));
  }
  const res = await apiFetch(`${API_BASE}/api/jobs`, {
    method: "POST",
    body: form
  });
  if (!res.ok) {
    throw new Error(await parseApiError(res, "Failed to create job"));
  }
  return res.json();
}

export async function listJobs(params: ListJobsParams = {}): Promise<JobListResponse> {
  const search = new URLSearchParams();
  if (params.limit != null) search.set("limit", String(params.limit));
  if (params.offset != null) search.set("offset", String(params.offset));
  if (params.q) search.set("q", params.q);
  const qs = search.toString();
  const res = await apiFetch(`${API_BASE}/api/jobs${qs ? `?${qs}` : ""}`);
  if (!res.ok) {
    throw new Error(await parseApiError(res, "Failed to list jobs"));
  }
  return res.json();
}

export async function getJobStatus(jobId: string): Promise<JobStatus> {
  const res = await apiFetch(`${API_BASE}/api/jobs/${jobId}`);
  if (!res.ok) {
    throw new Error(await parseApiError(res, "Failed to fetch job status"));
  }
  return res.json();
}

export async function cancelJob(jobId: string): Promise<void> {
  const res = await apiFetch(`${API_BASE}/api/jobs/${jobId}`, { method: "DELETE" });
  if (!res.ok) {
    throw new Error(await parseApiError(res, "Failed to cancel job"));
  }
}

export async function deleteJob(jobId: string): Promise<void> {
  const res = await apiFetch(`${API_BASE}/api/jobs/${jobId}`, { method: "DELETE" });
  if (!res.ok) {
    throw new Error(await parseApiError(res, "Failed to delete job"));
  }
}

export function artifactUrl(jobId: string, name: "map" | "heatmap" | "overlay" | "forest_overlay"): string {
  return `${API_BASE}/api/jobs/${jobId}/artifacts/${name}`;
}
