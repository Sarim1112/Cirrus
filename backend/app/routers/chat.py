"""Advisor chat. Replies stream as Server-Sent Events: progress first, then the verified answer."""

import json
from collections.abc import Iterator

from fastapi import APIRouter, Depends
from fastapi.responses import StreamingResponse
from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from ..advisor.orchestrator import TurnResult, run_turn
from ..advisor.providers import get_provider
from ..config import get_settings
from ..db import get_db, open_session
from ..deps import current_user, enforce_limit
from ..models import ChatMessage, User
from ..schemas import ChatBody
from ..services import load_context

router = APIRouter(prefix="/api/chat", tags=["chat"])

STARTERS = [
    "Where can I cut back?",
    "What's safe to spend?",
    "Can I afford a $1,500 trip by March?",
    "What if I halve food delivery?",
    "Show my subscriptions",
    "Anything unusual lately?",
]


def _message(row: ChatMessage) -> dict:
    return {
        "id": row.id,
        "role": row.role,
        "content": row.content,
        "meta": row.meta or {},
        "created_at": row.created_at.isoformat() + "Z",
    }


@router.get("/status")
def status(_user: User = Depends(current_user)):
    provider = get_provider()
    return {
        "mode": "local_ai" if provider.available() else "built_in",
        "model": get_settings().ollama_model if provider.available() else None,
        "starters": STARTERS,
    }


@router.get("/messages")
def messages(user: User = Depends(current_user), db: Session = Depends(get_db)):
    rows = (
        db.execute(
            select(ChatMessage)
            .where(ChatMessage.user_id == user.id)
            .order_by(ChatMessage.created_at.desc())
            .limit(100)
        )
        .scalars()
        .all()
    )
    return {"messages": [_message(r) for r in reversed(rows)]}


@router.delete("/messages", status_code=204)
def clear_messages(user: User = Depends(current_user), db: Session = Depends(get_db)):
    db.execute(delete(ChatMessage).where(ChatMessage.user_id == user.id))
    db.commit()


def _event(name: str, payload: dict) -> str:
    return f"event: {name}\ndata: {json.dumps(payload, default=str)}\n\n"


def _stream_turn(user_id: str, message: str) -> Iterator[str]:
    """Runs with its own session, because a streaming body outlives the request's dependencies."""
    with open_session() as db:
        user = db.get(User, user_id)
        ctx = load_context(db, user)
        recent = (
            db.execute(
                select(ChatMessage)
                .where(ChatMessage.user_id == user_id)
                .order_by(ChatMessage.created_at.desc())
                .limit(6)
            )
            .scalars()
            .all()
        )
        history = [{"role": m.role, "content": m.content} for m in reversed(recent)]
        db.add(ChatMessage(user_id=user_id, role="user", content=message, meta={}))
        db.commit()

        result: TurnResult | None = None
        for event in run_turn(ctx, message, get_provider(), history):
            if event["type"] == "status":
                yield _event("status", {"text": event["text"]})
            else:
                result = event["result"]

        row = ChatMessage(
            user_id=user_id, role="assistant", content=result.text, meta=result.as_meta()
        )
        db.add(row)
        db.commit()
        yield _event("final", _message(row))


@router.post("")
def send_message(body: ChatBody, user: User = Depends(current_user)):
    enforce_limit(f"chat:{user.id}", 30, 60)
    return StreamingResponse(
        _stream_turn(user.id, body.message.strip()),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache, no-transform", "X-Accel-Buffering": "no"},
    )
