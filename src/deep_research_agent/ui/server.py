"""FastAPI server for the Research Agent UI."""

import asyncio
import json
import uuid
from collections.abc import AsyncGenerator
from datetime import datetime
from pathlib import Path
from typing import Any

from dotenv import load_dotenv
from fastapi import FastAPI
from fastapi.responses import StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

load_dotenv(override=True)

from deep_research_agent.agent import create_deep_research_agent  # noqa: E402
from deep_research_agent.sources import extract_sources  # noqa: E402

app = FastAPI()

STATIC_DIR = Path(__file__).parent / "static"

_run_queues: dict[str, asyncio.Queue[dict[str, Any] | None]] = {}

_SENTINEL = None


class RunRequest(BaseModel):
    """Request body for POST /api/run."""

    query: str
    model: str = "gpt-4o-mini"
    max_agents: int = 3
    max_iter: int = 3


def _extract_tool_detail(msgs: list[object]) -> str:
    """Extract a short detail string from tool result messages."""
    if not msgs:
        return ""
    last = msgs[-1]
    content = getattr(last, "content", "")
    if isinstance(content, str) and content:
        lines = content.strip().splitlines()
        return "\n".join(lines[:6])
    return ""


async def _stream_agent(run_id: str, req: RunRequest) -> None:
    """Background task: runs the agent and puts SSE events into the queue."""
    queue: asyncio.Queue[dict[str, Any] | None] = _run_queues[run_id]
    seen_subgraph_ns: set[tuple[str, ...]] = set()
    start = datetime.now()
    current_state: dict[str, Any] = {}

    try:
        agent = create_deep_research_agent(
            model_name=req.model,
            max_concurrent_research_units=req.max_agents,
            max_researcher_iterations=req.max_iter,
        )

        async for chunk in agent.astream(
            {"messages": [{"role": "user", "content": req.query}]},
            stream_mode=["updates", "messages", "values"],
            subgraphs=True,
            version="v2",
        ):
            chunk_type = chunk["type"]
            data = chunk.get("data")

            if chunk_type == "values":
                ns = chunk.get("ns", ())
                if not ns:
                    current_state = data

            elif chunk_type == "updates":
                graph_name = chunk["ns"]
                node, result = next(iter(data.items()))
                ts = datetime.now().strftime("%H:%M:%S.%f")[:-3]

                if node == "tools":
                    msgs = result.get("messages", [])
                    tool_name = "tool"
                    if msgs and hasattr(msgs[-1], "name"):
                        tool_name = msgs[-1].name or "tool"
                    detail = _extract_tool_detail(msgs)
                    await queue.put(
                        {
                            "type": "trace",
                            "event_type": "tool",
                            "label": tool_name,
                            "message": f"Called {tool_name}",
                            "detail": detail,
                            "ts": ts,
                        }
                    )

                elif graph_name and len(graph_name) > 0:
                    is_new = graph_name not in seen_subgraph_ns
                    if is_new:
                        seen_subgraph_ns.add(graph_name)
                    label = f"research-agent #{len(seen_subgraph_ns)}"
                    await queue.put(
                        {
                            "type": "trace",
                            "event_type": "subagent",
                            "label": label,
                            "message": "Sub-agent spawned" if is_new else "Sub-agent working",
                            "ts": ts,
                        }
                    )

                else:
                    root_msgs = result.get("messages", [])
                    last = root_msgs[-1] if root_msgs else None
                    if last is None or (hasattr(last, "tool_calls") and not last.tool_calls):
                        continue
                    tool_calls = getattr(last, "tool_calls", [])
                    names = ", ".join(tc["name"] for tc in tool_calls) if tool_calls else "planning"
                    await queue.put(
                        {
                            "type": "trace",
                            "event_type": "agent",
                            "label": "Orchestrator",
                            "message": f"Dispatching: {names}",
                            "ts": ts,
                        }
                    )

            elif chunk_type == "messages":
                from langchain_core.messages import AIMessageChunk

                msg, metadata = data
                if (
                    isinstance(msg, AIMessageChunk)
                    and metadata.get("langgraph_node") == "model"
                    and not msg.tool_call_chunks
                    and msg.content
                ):
                    await queue.put({"type": "digest", "token": msg.content})

        files = current_state.get("files") or {}
        sources = extract_sources(files)
        if sources:
            await queue.put({"type": "sources", "sources": sources})

        duration = (datetime.now() - start).total_seconds()
        await queue.put(
            {
                "type": "done",
                "duration_s": duration,
                "run_date": start.strftime("%b %d, %H:%M"),
            }
        )

    except Exception as exc:
        await queue.put({"type": "error", "message": str(exc)})
    finally:
        await queue.put(_SENTINEL)


async def _sse_generator(run_id: str) -> AsyncGenerator[str]:
    """Reads from the run queue and yields SSE-formatted strings."""
    queue: asyncio.Queue[dict[str, Any] | None] | None = _run_queues.get(run_id)
    if queue is None:
        yield f"data: {json.dumps({'type': 'error', 'message': 'run not found'})}\n\n"
        return

    while True:
        event: dict[str, Any] | None = await queue.get()
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
