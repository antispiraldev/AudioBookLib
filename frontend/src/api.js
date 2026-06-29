const BASE = "/api";

async function parseError(r) {
  const body = await r.json().catch(() => ({}));
  const detail = body.detail;
  if (Array.isArray(detail)) return detail.map((e) => e.msg).join(", ");
  return detail || `Request failed (${r.status})`;
}

export async function fetchBooks() {
  const r = await fetch(`${BASE}/books/`);
  if (!r.ok) throw new Error(await parseError(r));
  return r.json();
}

export async function uploadBook(formData) {
  const r = await fetch(`${BASE}/books/`, { method: "POST", body: formData });
  if (!r.ok) throw new Error(await parseError(r));
  return r.json();
}

export async function deleteBook(id) {
  const r = await fetch(`${BASE}/books/${id}`, { method: "DELETE" });
  if (!r.ok) throw new Error(await parseError(r));
}

export async function updateBook(id, data) {
  const r = await fetch(`${BASE}/books/${id}`, {
    method: "PATCH",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(data),
  });
  if (!r.ok) throw new Error(await parseError(r));
  return r.json();
}

export async function retryBook(id) {
  const r = await fetch(`${BASE}/books/${id}/synthesize`, { method: "POST" });
  if (!r.ok) throw new Error(await parseError(r));
  return r.json();
}

export function audioUrl(segmentId) {
  return `${BASE}/audio/${segmentId}`;
}
