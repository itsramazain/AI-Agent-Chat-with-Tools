import React, { useEffect, useMemo, useRef, useState } from "react";
import {
  chat,
  createSession,
  getMessages,
  getToolCalls,
  listSessions,
} from "./api";

type Msg = {
  id?: number;
  role: "user" | "assistant";
  content: string;
  created_at?: string;
};
type Sess = { session_id: string; last_time?: string };

export default function App() {
  const [sessions, setSessions] = useState<Sess[]>([]);
  const [active, setActive] = useState<string>("");
  const [messages, setMessages] = useState<Msg[]>([]);
  const [input, setInput] = useState("");
  const [showTools, setShowTools] = useState(false);
  const [tools, setTools] = useState<any[]>([]);
  const chatRef = useRef<HTMLDivElement>(null);

  async function refreshSessions() {
    const s = await listSessions();
    setSessions(s);
  }

  async function loadSession(id: string) {
    setActive(id);
    const ms = await getMessages(id);
    setMessages(ms.filter((m: any) => m.role !== "system"));
    if (showTools) {
      const tc = await getToolCalls(id);
      setTools(tc);
    }
  }

  async function newSession() {
    const r = await createSession();
    await refreshSessions();
    await loadSession(r.session_id);
  }

  useEffect(() => {
    refreshSessions();
  }, []);

  useEffect(() => {
    chatRef.current?.scrollTo({
      top: chatRef.current.scrollHeight,
      behavior: "smooth",
    });
  }, [messages]);

  async function send() {
    const text = input.trim();
    if (!text || !active) return;

    setInput("");
    setMessages((m) => [...m, { role: "user", content: text }]);

    const resp = await chat(active, text);
    setMessages((m) => [...m, { role: "assistant", content: resp.reply }]);

    await refreshSessions();
    if (showTools) {
      const tc = await getToolCalls(active);
      setTools(tc);
    }
  }

  return (
    <div className="shell">
      <aside className="sidebar">
        <div className="card">
          <div style={{ fontWeight: 700, fontSize: 16 }}>
            Library Desk Agent
          </div>
          <div className="small">
            Local full-stack: React + FastAPI + SQLite
          </div>
        </div>

        <div className="row">
          <button className="btn" onClick={newSession}>
            New session
          </button>
          <button className="btn" onClick={() => setShowTools((v) => !v)}>
            {showTools ? "Hide tools" : "Show tools"}
          </button>
        </div>

        <div className="sessions card">
          {sessions.length === 0 && (
            <div className="small">No sessions yet. Create one.</div>
          )}
          {sessions.map((s) => (
            <div
              key={s.session_id}
              className={
                "sessionItem " + (active === s.session_id ? "active" : "")
              }
              onClick={() => loadSession(s.session_id)}
              title={s.session_id}
            >
              <div style={{ fontWeight: 650 }}>Session</div>
              <div className="small">{s.session_id.slice(0, 8)}…</div>
              {s.last_time && <div className="small">Last: {s.last_time}</div>}
            </div>
          ))}
        </div>

        {showTools && active && (
          <div className="card" style={{ overflow: "auto", maxHeight: 240 }}>
            <div style={{ fontWeight: 700, marginBottom: 8 }}>Tool calls</div>
            <button
              className="btn"
              onClick={async () => setTools(await getToolCalls(active))}
            >
              Refresh
            </button>
            <pre
              style={{ whiteSpace: "pre-wrap", fontSize: 12, marginTop: 10 }}
            >
              {JSON.stringify(tools, null, 2)}
            </pre>
          </div>
        )}
      </aside>

      <main className="main">
        <div className="chat" ref={chatRef}>
          {!active ? (
            <div className="card">
              <div style={{ fontWeight: 700 }}>Start</div>
              <div className="small">
                Create or select a session on the left.
              </div>
            </div>
          ) : (
            <>
              {messages.map((m, idx) => (
                <div key={idx} className={"msg " + m.role}>
                  <div>{m.content}</div>
                  {m.created_at && <div className="meta">{m.created_at}</div>}
                </div>
              ))}
            </>
          )}
        </div>

        <div className="composer">
          <div className="row">
            <input
              className="input"
              value={input}
              onChange={(e) => setInput(e.target.value)}
              placeholder={
                !active
                  ? "Create/select a session first…"
                  : "Ask about books, restocking, orders…"
              }
              disabled={!active}
              onKeyDown={(e) => {
                if (e.key === "Enter") send();
              }}
            />
            <button className="btn" onClick={send} disabled={!active}>
              Send
            </button>
          </div>
          <div className="small" style={{ marginTop: 8 }}>
            Try: “Restock The Pragmatic Programmer by 10 and list all books by
            Andrew Hunt.”
          </div>
        </div>
      </main>
    </div>
  );
}
