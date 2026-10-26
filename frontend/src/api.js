async function request(path, options = {}) {
  const res = await fetch(path, {
    credentials: "same-origin",
    headers: { "Content-Type": "application/json" },
    ...options,
  });
  if (!res.ok) {
    let detail = res.statusText;
    try {
      detail = (await res.json()).detail || detail;
    } catch {}
    const err = new Error(detail);
    err.status = res.status;
    throw err;
  }
  return res.json();
}

export const api = {
  login: (identifier, consent) =>
    request("/api/login", { method: "POST", body: JSON.stringify({ identifier, consent }) }),
  logout: () => request("/api/logout", { method: "POST" }),
  me: () => request("/api/me"),
  conversations: () => request("/api/conversations"),
  conversation: (id) => request(`/api/conversations/${id}`),
  deleteConversation: (id) => request(`/api/conversations/${id}`, { method: "DELETE" }),
  // fire-and-forget: record a UI interaction for the study dataset
  event: (type, conversation_id = null, detail = null) =>
    request("/api/event", { method: "POST", body: JSON.stringify({ type, conversation_id, detail }) }).catch(() => {}),
};

// POST /api/chat and read the server-sent events: {cid} {t} {error} {done}
export async function streamChat({ conversation_id, model, message }, onEvent) {
  const res = await fetch("/api/chat", {
    method: "POST",
    credentials: "same-origin",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ conversation_id, model, message }),
  });
  if (!res.ok) {
    let detail = res.statusText;
    try {
      detail = (await res.json()).detail || detail;
    } catch {}
    throw new Error(detail);
  }
  const reader = res.body.getReader();
  const dec = new TextDecoder();
  let buf = "";
  for (;;) {
    const { value, done } = await reader.read();
    if (done) break;
    buf += dec.decode(value, { stream: true });
    let i;
    while ((i = buf.indexOf("\n\n")) >= 0) {
      const chunk = buf.slice(0, i);
      buf = buf.slice(i + 2);
      if (chunk.startsWith("data: ")) onEvent(JSON.parse(chunk.slice(6)));
    }
  }
}
