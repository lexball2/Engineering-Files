const BASE = "/api";

function errorMessage(data: unknown, fallback: string): string {
  if (!data || typeof data !== "object") return fallback;

  const detail = "detail" in data ? (data as { detail?: unknown }).detail : undefined;
  if (typeof detail === "string") return detail;

  if (Array.isArray(detail)) {
    const messages = detail
      .map((item) => {
        if (typeof item === "string") return item;
        if (item && typeof item === "object" && "msg" in item) {
          return String((item as { msg?: unknown }).msg || "");
        }
        return "";
      })
      .filter(Boolean);
    if (messages.length) return messages.join("；");
  }

  const message = "message" in data ? (data as { message?: unknown }).message : undefined;
  return typeof message === "string" ? message : fallback;
}

async function post(path: string, body?: unknown): Promise<Response> {
  const headers: Record<string, string> = { "Content-Type": "application/json" };
  const res = await fetch(`${BASE}${path}`, {
    method: "POST",
    headers,
    credentials: "same-origin",
    body: body ? JSON.stringify(body) : "{}",
  });
  if (res.status === 401) window.dispatchEvent(new Event("auth-expired"));
  if (!res.ok) {
    const data = await res.json().catch(() => ({}));
    throw new Error(errorMessage(data, `请求失败 (${res.status})`));
  }
  return res;
}

async function uploadFile(path: string, file: File): Promise<Response> {
  const form = new FormData();
  form.append("file", file);
  const res = await fetch(`${BASE}${path}`, {
    method: "POST",
    credentials: "same-origin",
    body: form,
  });
  if (res.status === 401) window.dispatchEvent(new Event("auth-expired"));
  if (!res.ok) {
    const data = await res.json().catch(() => ({}));
    throw new Error(errorMessage(data, "上传失败"));
  }
  return res;
}

export const api = {
  post: (path: string, body?: unknown) => post(path, body),
  upload: (path: string, file: File) => uploadFile(path, file),
};
