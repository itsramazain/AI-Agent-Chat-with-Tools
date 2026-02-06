const API = "http://localhost:8000/api";

export async function listSessions() {
  const r = await fetch(`${API}/sessions`);
  return r.json();
}
export async function createSession() {
  const r = await fetch(`${API}/sessions`, { method: "POST" });
  return r.json();
}
export async function getMessages(session_id: string) {
  const r = await fetch(`${API}/sessions/${session_id}/messages`);
  return r.json();
}
export async function chat(session_id: string, message: string) {
  const r = await fetch(`${API}/chat`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ session_id, message }),
  });
  return r.json();
}
export async function getToolCalls(session_id: string) {
  const r = await fetch(`${API}/sessions/${session_id}/tool-calls`);
  return r.json();
}
