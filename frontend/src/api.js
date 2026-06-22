const BASE = "/api";

export async function fetchBooks() {
  const r = await fetch(`${BASE}/books/`);
  if (!r.ok) throw new Error("Failed to fetch books");
  return r.json();
}

export async function uploadBook(formData) {
  const r = await fetch(`${BASE}/books/`, { method: "POST", body: formData });
  if (!r.ok) throw new Error("Upload failed");
  return r.json();
}

export async function deleteBook(id) {
  await fetch(`${BASE}/books/${id}`, { method: "DELETE" });
}

export async function retryBook(id) {
  const r = await fetch(`${BASE}/books/${id}/synthesize`, { method: "POST" });
  if (!r.ok) throw new Error("Retry failed");
  return r.json();
}

export function audioUrl(segmentId) {
  return `${BASE}/audio/${segmentId}`;
}
