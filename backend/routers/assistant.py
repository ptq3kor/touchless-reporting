import json
from typing import Optional

from fastapi import APIRouter
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from ..agents.config import NOT_CONFIGURED_MSG, is_configured

router = APIRouter(prefix="/api/assistant", tags=["assistant"])


class ChatMessage(BaseModel):
    role: str
    content: str


class ChatRequest(BaseModel):
    messages: list[ChatMessage]
    filters: Optional[dict] = None


class SummaryRequest(BaseModel):
    filters: Optional[dict] = None


def _sse(payload: dict) -> str:
    return f"data: {json.dumps(payload)}\n\n"


def _stream(gen_factory):
    async def event_stream():
        if not is_configured():
            yield _sse({"error": NOT_CONFIGURED_MSG})
            return
        try:
            async for delta in gen_factory():
                yield _sse({"delta": delta})
            yield _sse({"done": True})
        except Exception as exc:  # surface agent/transport failures to the client
            yield _sse({"error": f"Assistant error: {exc}"})

    return StreamingResponse(event_stream(), media_type="text/event-stream",
                             headers={"Cache-Control": "no-cache"})


@router.post("/chat")
def chat(req: ChatRequest):
    from ..agents import orchestrator

    msgs = [m.model_dump() for m in req.messages]
    return _stream(lambda: orchestrator.chat(msgs, req.filters))


@router.post("/generate-summary")
def generate_summary(req: SummaryRequest):
    from ..agents import orchestrator

    return _stream(lambda: orchestrator.generate_summary(req.filters))
