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

const API_BASE = "http://localhost:8000";

export async function createJob(file: File): Promise<{ job_id: string; status: string }> {
  const form = new FormData();
  form.append("file", file);
  const res = await fetch(`${API_BASE}/api/jobs`, {
    method: "POST",
    body: form
  });
  if (!res.ok) {
    throw new Error(`Failed to create job: ${res.statusText}`);
  }
  return res.json();
}

export async function getJobStatus(jobId: string): Promise<JobStatus> {
  const res = await fetch(`${API_BASE}/api/jobs/${jobId}`);
  if (!res.ok) {
    throw new Error(`Failed to fetch job status: ${res.statusText}`);
  }
  return res.json();
}

export function artifactUrl(jobId: string, name: "map" | "heatmap" | "overlay"): string {
  return `${API_BASE}/api/jobs/${jobId}/artifacts/${name}`;
}

