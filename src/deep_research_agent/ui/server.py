"""FastAPI server for the Research Agent UI."""

import asyncio
import json
import uuid
from collections.abc import AsyncGenerator
from pathlib import Path

from dotenv import load_dotenv
from fastapi import FastAPI
from fastapi.responses import StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

load_dotenv(override=True)

from deep_research_agent.agent import create_deep_research_agent  # noqa: E402
from deep_research_agent.streaming import StreamEvent, stream_events  # noqa: E402

app = FastAPI()

STATIC_DIR = Path(__file__).parent / "static"

_run_queues: dict[str, asyncio.Queue[StreamEvent | None]] = {}

_SENTINEL = None


class RunRequest(BaseModel):
    """Request body for POST /api/run."""

    query: str
    model: str = "gemma4:e2b"
    max_agents: int = 3
    max_iter: int = 3


async def _stream_agent(run_id: str, req: RunRequest) -> None:
    """Background task: runs the agent and puts SSE events into the queue."""
    queue = _run_queues[run_id]

    agent = create_deep_research_agent(
        model_name=req.model,
        max_concurrent_research_units=req.max_agents,
        max_researcher_iterations=req.max_iter,
    )

    async for event in stream_events(
        agent,
        {"messages": [{"role": "user", "content": req.query}]},
    ):
        await queue.put(event)

    await queue.put(_SENTINEL)


async def _sse_generator(run_id: str) -> AsyncGenerator[str]:
    """Reads from the run queue and yields SSE-formatted strings."""
    queue: asyncio.Queue[StreamEvent | None] | None = _run_queues.get(run_id)
    if queue is None:
        yield f"data: {json.dumps({'type': 'error', 'message': 'run not found'})}\n\n"
        return

    while True:
        event: StreamEvent | None = await queue.get()
        if event is _SENTINEL:
            break
        yield f"data: {json.dumps(event)}\n\n"
        await asyncio.sleep(0)

    _run_queues.pop(run_id, None)


@app.post("/api/run")
async def start_run(req: RunRequest) -> dict[str, str]:
    """Start a research run and return its run_id."""
    run_id = str(uuid.uuid4())[:8]
    _run_queues[run_id] = asyncio.Queue()
    task = asyncio.create_task(_stream_agent(run_id, req))
    task.add_done_callback(lambda t: t.exception() if not t.cancelled() else None)
    return {"run_id": run_id}


@app.get("/api/stream/{run_id}")
async def stream_run(run_id: str) -> StreamingResponse:
    """Stream SSE events for a running research job."""
    return StreamingResponse(
        _sse_generator(run_id),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
        },
    )


# Serve static files (index.html etc.)
app.mount("/", StaticFiles(directory=str(STATIC_DIR), html=True), name="static")
