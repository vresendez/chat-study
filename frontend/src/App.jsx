import { useEffect, useRef, useState } from "react";
import { api, streamChat } from "./api.js";

const STARTERS = [
  "Summarize the main arguments in a news story I paste in.",
  "Suggest five interview questions for a local city council reporter.",
  "Explain how to verify a viral photo before publishing it.",
];

const Icon = {
  download: (
    <svg viewBox="0 0 24 24" width="16" height="16" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
      <path d="M12 3v12" /><path d="M7 11l5 5 5-5" /><path d="M5 21h14" />
    </svg>
  ),
  trash: (
    <svg viewBox="0 0 24 24" width="16" height="16" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
      <path d="M3 6h18" /><path d="M8 6V4h8v2" /><path d="M19 6l-1 14H6L5 6" /><path d="M10 11v6" /><path d="M14 11v6" />
    </svg>
  ),
  plus: (
    <svg viewBox="0 0 24 24" width="16" height="16" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" aria-hidden="true">
      <path d="M12 5v14" /><path d="M5 12h14" />
    </svg>
  ),
  menu: (
    <svg viewBox="0 0 24 24" width="22" height="22" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" aria-hidden="true">
      <path d="M4 6h16" /><path d="M4 12h16" /><path d="M4 18h16" />
    </svg>
  ),
  send: (
    <svg viewBox="0 0 24 24" width="18" height="18" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
      <path d="M5 12h14" /><path d="M13 6l6 6-6 6" />
    </svg>
  ),
};

function Login({ onDone }) {
  const [identifier, setIdentifier] = useState("");
  const [consent, setConsent] = useState(false);
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);

  async function submit(e) {
    e.preventDefault();
    setError("");
    setBusy(true);
    try {
      await api.login(identifier, consent);
      onDone();
    } catch (err) {
      setError(err.message);
    } finally {
      setBusy(false);
    }
  }

  return (
    <main className="login">
      <form className="card" onSubmit={submit}>
        <img className="logo" src="/logo.png" alt="Public Tech Media Lab" />
        <h1>Newsroom <span>Chat Lab</span></h1>
        <p className="muted">Enter your participant code or email to begin.</p>
        <input
          id="identifier"
          placeholder="Code or email"
          value={identifier}
          onChange={(e) => setIdentifier(e.target.value)}
          autoFocus
        />
        <label className="check">
          <input type="checkbox" checked={consent} onChange={(e) => setConsent(e.target.checked)} />
          I agree to take part in this study.
        </label>
        {error && <p className="error">{error}</p>}
        <button id="login-btn" disabled={busy || !identifier.trim() || !consent}>
          {busy ? "Checking…" : "Start"}
        </button>
      </form>
    </main>
  );
}

function Chat({ participant, models, onLogout }) {
  const [convs, setConvs] = useState([]);
  const [cid, setCid] = useState(null);
  const [messages, setMessages] = useState([]);
  const modelList = Array.isArray(models) ? models : Object.keys(models);
  const [model, setModel] = useState(modelList[0]);
  const [text, setText] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [menuOpen, setMenuOpen] = useState(false);
  const endRef = useRef(null);

  const loadConvs = () => api.conversations().then(setConvs).catch(() => {});
  useEffect(() => {
    loadConvs();
    api.event("page_view");
  }, []);
  useEffect(() => {
    endRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages]);

  async function open(id) {
    setCid(id);
    setError("");
    setMenuOpen(false);
    api.event("open_chat", id);
    setMessages(await api.conversation(id));
  }

  function newChat() {
    setCid(null);
    setMessages([]);
    setError("");
    setMenuOpen(false);
    api.event("new_chat");
  }

  async function remove(id) {
    if (!window.confirm("Delete this chat? It will disappear from your list.")) return;
    try {
      await api.deleteConversation(id);
      if (id === cid) {
        setCid(null);
        setMessages([]);
      }
      loadConvs();
    } catch (err) {
      setError(err.message);
    }
  }

  // Download any chat in the list as a .txt file
  async function download(id, title) {
    try {
      const msgs = id === cid ? messages : await api.conversation(id);
      const lines = msgs.map((m) => `${m.role === "user" ? "You" : m.model || "Assistant"}:\n${m.content}\n`);
      const blob = new Blob([lines.join("\n")], { type: "text/plain;charset=utf-8" });
      const a = document.createElement("a");
      a.href = URL.createObjectURL(blob);
      const safe = (title || "chat").replace(/[^a-z0-9]+/gi, "-").slice(0, 40).toLowerCase();
      a.download = `${safe || "chat"}-${id.slice(0, 6)}.txt`;
      a.click();
      URL.revokeObjectURL(a.href);
      api.event("download_chat", id);
    } catch (err) {
      setError(err.message);
    }
  }

  async function send(e, preset) {
    e?.preventDefault();
    const message = (preset ?? text).trim();
    if (!message || busy) return;
    setText("");
    setError("");
    setBusy(true);
    setMessages((m) => [...m, { role: "user", content: message }, { role: "assistant", content: "", model }]);
    try {
      await streamChat({ conversation_id: cid, model, message }, (ev) => {
        if (ev.cid) setCid(ev.cid);
        if (ev.t)
          setMessages((m) => {
            const copy = [...m];
            const last = copy[copy.length - 1];
            copy[copy.length - 1] = { ...last, content: last.content + ev.t };
            return copy;
          });
        if (ev.error) setError(ev.error);
      });
      loadConvs();
    } catch (err) {
      setError(err.message);
      setMessages((m) => m.filter((x, i) => !(i === m.length - 1 && !x.content)));
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="layout">
      <aside className={`sidebar ${menuOpen ? "open" : ""}`}>
        <div className="brand">
          <img src="/logo.png" alt="Public Tech Media Lab" />
          <b>Newsroom<br />Chat Lab</b>
        </div>
        <button id="new-chat" className="new" onClick={newChat}>{Icon.plus} New chat</button>
        <p className="side-title">Your chats</p>
        <ul>
          {convs.length === 0 && <li className="empty">No chats yet</li>}
          {convs.map((c) => (
            <li key={c.id} className={`conv ${c.id === cid ? "active" : ""}`}>
              <button className="title" onClick={() => open(c.id)} title={c.title}>
                {(c.title || "Untitled").slice(0, 40)}
              </button>
              <button className="icon" title="Download chat" aria-label="Download chat" onClick={() => download(c.id, c.title)}>
                {Icon.download}
              </button>
              <button className="icon del" title="Delete chat" aria-label="Delete chat" onClick={() => remove(c.id)}>
                {Icon.trash}
              </button>
            </li>
          ))}
        </ul>
        <div className="who">
          <span title={participant}>{participant}</span>
          <button className="link" id="logout-btn" onClick={onLogout}>Log out</button>
        </div>
      </aside>

      <section className="chat">
        <header>
          <button className="burger" aria-label="Open chat list" onClick={() => setMenuOpen((v) => !v)}>{Icon.menu}</button>
          <label htmlFor="model">Model</label>
          <select
            id="model"
            value={model}
            onChange={(e) => {
              setModel(e.target.value);
              api.event("model_change", cid, e.target.value);
            }}
          >
            {modelList.map((m) => (
              <option key={m}>{m}</option>
            ))}
          </select>
        </header>

        <div className="messages">
          {messages.length === 0 && (
            <div className="welcome">
              <img src="/logo.png" alt="" />
              <h2>How can I help today?</h2>
              <p className="muted">Pick a model above, then type a message or try one of these:</p>
              <div className="starters">
                {STARTERS.map((s) => (
                  <button key={s} className="starter" onClick={() => send(null, s)}>{s}</button>
                ))}
              </div>
            </div>
          )}
          {messages.map((m, i) => (
            <div key={i} className={`msg ${m.role}`}>
              {m.role === "assistant" && m.model && <small className="tag">{m.model}</small>}
              {m.content || (busy && i === messages.length - 1 ? <span className="dots"><i /><i /><i /></span> : "")}
            </div>
          ))}
          <div ref={endRef} />
        </div>

        {error && <p className="error bar">{error}</p>}
        <form className="composer" onSubmit={send}>
          <textarea
            id="message"
            rows={2}
            maxLength={8000}
            placeholder="Type your message… (Enter to send, Shift+Enter for a new line)"
            value={text}
            onChange={(e) => setText(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === "Enter" && !e.shiftKey) send(e);
            }}
          />
          <button id="send-btn" disabled={busy || !text.trim()} aria-label="Send">{Icon.send}<span>Send</span></button>
        </form>
      </section>
    </div>
  );
}

export default function App() {
  const [state, setState] = useState({ loading: true, me: null });

  const refresh = () =>
    api
      .me()
      .then((me) => setState({ loading: false, me }))
      .catch(() => setState({ loading: false, me: null }));

  useEffect(() => {
    refresh();
  }, []);

  if (state.loading) return <p className="muted center">Loading…</p>;
  if (!state.me) return <Login onDone={refresh} />;
  return (
    <Chat
      participant={state.me.participant}
      models={state.me.models}
      onLogout={async () => {
        await api.logout();
        setState({ loading: false, me: null });
      }}
    />
  );
}
