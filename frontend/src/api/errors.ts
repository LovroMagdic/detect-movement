const STATUS_FALLBACKS: Record<number, string> = {
  400: "Invalid request.",
  404: "Not found.",
  409: "Results are not ready yet.",
  500: "Server error — try again.",
  502: "Server unavailable — try again.",
  503: "Server unavailable — try again."
};

function formatDetail(detail: unknown): string | null {
  if (typeof detail === "string" && detail.trim()) {
    return detail.trim();
  }
  if (Array.isArray(detail)) {
    const parts = detail
      .map((item) => {
        if (typeof item === "string") return item;
        if (item && typeof item === "object" && "msg" in item) {
          return String((item as { msg: unknown }).msg);
        }
        return null;
      })
      .filter((p): p is string => !!p);
    if (parts.length) return parts.join("; ");
  }
  return null;
}

export async function parseApiError(res: Response, fallbackPrefix: string): Promise<string> {
  let detail: string | null = null;
  try {
    const body = await res.json();
    if (body && typeof body === "object" && "detail" in body) {
      detail = formatDetail((body as { detail: unknown }).detail);
    }
  } catch {
  }

  if (detail) return detail;

  const statusFallback = STATUS_FALLBACKS[res.status];
  if (statusFallback) return statusFallback;

  const statusText = res.statusText?.trim();
  if (statusText) return `${fallbackPrefix}: ${statusText}`;
  return `${fallbackPrefix} (${res.status})`;
}

export function networkErrorMessage(err: unknown, fallback: string): string {
  if (err instanceof TypeError) {
    const msg = err.message.toLowerCase();
    if (msg.includes("failed to fetch") || msg.includes("network")) {
      return "Cannot reach the server. Check that the API is running.";
    }
  }
  if (err instanceof Error && err.message.trim()) {
    return err.message;
  }
  return fallback;
}

export async function apiFetch(input: RequestInfo | URL, init?: RequestInit): Promise<Response> {
  try {
    return await fetch(input, init);
  } catch (err) {
    throw new Error(networkErrorMessage(err, "Network request failed."));
  }
}
