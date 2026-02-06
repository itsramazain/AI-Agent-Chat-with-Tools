import os
import uuid
from pathlib import Path
from typing import Any, Dict, List, Optional

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from dotenv import load_dotenv

from server.db import init_db, tx
from server.agent import build_agent

load_dotenv()

ROOT = Path(__file__).resolve().parents[1]
SCHEMA = ROOT / "db" / "schema.sql"
SEED = ROOT / "db" / "seed.sql"
PROMPT_FILE = ROOT / "prompts" / "system.txt"

app = FastAPI(title="Library Desk Agent")

# local dev CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# init DB on startup
@app.on_event("startup")
def startup():
    init_db(str(SCHEMA), str(SEED))

    system_prompt = PROMPT_FILE.read_text(encoding="utf-8")
    if not os.getenv("OPENAI_API_KEY"):
        print("WARNING: OPENAI_API_KEY not set. Set it in .env to enable the agent.")
    app.state.agent = build_agent(system_prompt)

class CreateSessionResp(BaseModel):
    session_id: str

@app.post("/api/sessions", response_model=CreateSessionResp)
def create_session():
    return {"session_id": str(uuid.uuid4())}

@app.get("/api/sessions")
def list_sessions():
    with tx() as conn:
        rows = conn.execute(
            "SELECT session_id, MAX(created_at) AS last_time FROM messages GROUP BY session_id ORDER BY last_time DESC"
        ).fetchall()
    return [{"session_id": r["session_id"], "last_time": r["last_time"]} for r in rows]

@app.get("/api/sessions/{session_id}/messages")
def get_messages(session_id: str):
    with tx() as conn:
        rows = conn.execute(
            "SELECT id, role, content, created_at FROM messages WHERE session_id = ? ORDER BY id ASC",
            (session_id,),
        ).fetchall()
    return [dict(r) for r in rows]

@app.get("/api/sessions/{session_id}/tool-calls")
def get_tool_calls(session_id: str):
    with tx() as conn:
        rows = conn.execute(
            "SELECT id, name, args_json, result_json, created_at FROM tool_calls WHERE session_id = ? ORDER BY id ASC",
            (session_id,),
        ).fetchall()
    return [dict(r) for r in rows]

class ChatReq(BaseModel):
    session_id: str
    message: str

class ChatResp(BaseModel):
    reply: str

def _insert_message(session_id: str, role: str, content: str) -> None:
    with tx() as conn:
        conn.execute(
            "INSERT INTO messages(session_id, role, content) VALUES (?,?,?)",
            (session_id, role, content),
        )

@app.post("/api/chat", response_model=ChatResp)
def chat(req: ChatReq):
    if not req.session_id:
        raise HTTPException(status_code=400, detail="session_id required")
    if not req.message.strip():
        raise HTTPException(status_code=400, detail="message required")

    _insert_message(req.session_id, "user", req.message)

    agent = app.state.agent
    try:
        # Provide chat history from DB to agent
        with tx() as conn:
            rows = conn.execute(
                "SELECT role, content FROM messages WHERE session_id = ? ORDER BY id ASC LIMIT 30",
                (req.session_id,),
            ).fetchall()
        chat_history = []
        for r in rows:
            if r["role"] == "system":
                continue
            if r["role"] == "user":
                from langchain_core.messages import HumanMessage
                chat_history.append(HumanMessage(content=r["content"]))
            elif r["role"] == "assistant":
                from langchain_core.messages import AIMessage
                chat_history.append(AIMessage(content=r["content"]))

        result = agent.invoke({"input": req.message, "chat_history": chat_history})

        reply = str(result.get("output", "")).strip()
        if not reply:
            reply = "I couldn't produce a response. Try rephrasing your request."

    except Exception as e:
        reply = f"Sorry—something went wrong while processing that: {e}"

    _insert_message(req.session_id, "assistant", reply)
    return {"reply": reply}
