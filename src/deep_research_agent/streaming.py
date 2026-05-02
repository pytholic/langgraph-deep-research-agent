"""Shared stream interpretation for the deep research agent.

Consumes raw LangGraph v2 stream chunks from ``agent.astream()`` and yields
structured, output-agnostic event dicts. Both the FastAPI server and the CLI
runner consume this single generator — eliminating interpretation duplication.
"""

from collections.abc import AsyncGenerator
from datetime import datetime
from typing import Any

from langchain_core.messages import AIMessageChunk
from langgraph.pregel import Pregel
from langgraph.types import StreamMode

from deep_research_agent.sources import extract_sources

type StreamEvent = dict[str, Any]


def _extract_tool_detail(msgs: list[object]) -> str:
    """Extract a short detail string from the last tool result message."""
    if not msgs:
        return ""
    last = msgs[-1]
    content = getattr(last, "content", "")
    if isinstance(content, str) and content:
        lines = content.strip().splitlines()
        return "\n".join(lines[:6])
    return ""


def _interpret_tool_node(
    msgs: list[object],
    ts: str,
    node: str,
    graph: str,
) -> StreamEvent:
    """Build a trace event for a tool-node update."""
    tool_name = "tool"
    if msgs and hasattr(msgs[-1], "name"):
        tool_name = getattr(msgs[-1], "name", None) or "tool"
    return {
        "type": "trace",
        "event_type": "tool",
        "label": tool_name,
        "message": f"Called {tool_name}",
        "detail": _extract_tool_detail(msgs),
        "node": node,
        "graph": graph,
        "ts": ts,
    }


def _interpret_subagent_node(
    ns: tuple[str, ...],
    seen: set[tuple[str, ...]],
    ts: str,
    node: str,
    graph: str,
) -> StreamEvent:
    """Build a trace event for a subgraph update."""
    is_new = ns not in seen
    if is_new:
        seen.add(ns)
    return {
        "type": "trace",
        "event_type": "subagent",
        "label": f"research-agent #{len(seen)}",
        "message": "Sub-agent spawned" if is_new else "Sub-agent working",
        "node": node,
        "graph": graph,
        "ts": ts,
    }


def _interpret_orchestrator_node(
    result: dict[str, Any],
    ts: str,
    node: str,
    graph: str,
) -> StreamEvent | None:
    """Build a trace event for a root-graph orchestrator update.

    Returns ``None`` when the update carries no actionable information
    (e.g. a plain-text model response with no tool calls).
    """
    root_msgs: list[object] = result.get("messages", [])
    last = root_msgs[-1] if root_msgs else None
    # Empty tool_calls means the model wrote a plain text response with no tool dispatches —
    # which is the final answer turn. We filter it out as this is handled in the messages chunk.
    if last is None or (hasattr(last, "tool_calls") and not getattr(last, "tool_calls", None)):
        return None
    tool_calls: list[dict[str, Any]] = getattr(last, "tool_calls", [])
    names = ", ".join(tc["name"] for tc in tool_calls) if tool_calls else "planning"
    return {
        "type": "trace",
        "event_type": "agent",
        "label": "Orchestrator",
        "message": f"Dispatching: {names}",
        "node": node,
        "graph": graph,
        "ts": ts,
    }


async def stream_events(
    agent: Pregel,
    input_data: dict[str, Any],
    *,
    streaming: bool = True,
    include_raw_messages: bool = False,
) -> AsyncGenerator[StreamEvent]:
    """Interpret raw LangGraph stream chunks into structured UI events.

    Yields dicts with a ``"type"`` key — one of ``"trace"``, ``"digest"``,
    ``"sources"``, ``"done"``, or ``"error"``.

    Args:
        agent: Compiled LangGraph agent.
        input_data: Input dict passed to ``agent.astream()``.
        streaming: If True, include the ``"messages"`` stream mode for
            token-by-token digest output.
        include_raw_messages: If True, attach LangChain message objects to
            trace events for local renderers. Keep False for JSON/SSE consumers.
    """
    seen_subgraph_ns: set[tuple[str, ...]] = set()
    current_state: dict[str, Any] = {}
    start = datetime.now()
    # Track whether the root tools node has fired at least once.
    # Only stream digest tokens after tools have executed — this prevents
    # intermediate model turns (planning, todo reads) from leaking into
    # the digest. The final answer always comes after at least one tool round.
    root_tools_executed = False

    stream_modes: list[StreamMode] = (
        ["updates", "messages", "values"] if streaming else ["updates", "values"]
    )

    try:
        async for chunk in agent.astream(
            input_data,
            stream_mode=stream_modes,
            subgraphs=True,
            version="v2",
        ):
            chunk_type: str = chunk["type"]
            data: Any = chunk.get("data")
            ns: tuple[str, ...] = chunk.get("ns", ())

            if chunk_type == "values":
                # Full state snapshot after each step. We only track the root
                # agent's state (ns == ()) to extract state["files"] for source
                # extraction after the stream ends.
                # Ref: https://docs.langchain.com/oss/python/langgraph/persistence#checkpoint-namespace
                if not ns:  # belongs to the main agent
                    current_state = data

            elif chunk_type == "updates":
                # Fires once per node after it completes. Used for trace events:
                # the full AIMessage is available here, so we can read tool_calls
                # to emit "Dispatching: <tool>" rows in the UI.
                node, result = next(iter(data.items()))
                ts = datetime.now().strftime("%H:%M:%S.%f")[:-3]
                graph = ns[-1] if ns else "root"

                if node == "tools":
                    if not ns:
                        root_tools_executed = True
                    # ToolMessage available — extract tool name and result preview.
                    event = _interpret_tool_node(result.get("messages", []), ts, node, graph)
                    if include_raw_messages:
                        event["raw_messages"] = result.get("messages", [])
                    yield event

                elif ns:
                    # Non-empty namespace means this update came from a subgraph
                    # (a spawned research sub-agent), not the root orchestrator.
                    event = _interpret_subagent_node(ns, seen_subgraph_ns, ts, node, graph)
                    if include_raw_messages:
                        event["raw_messages"] = result.get("messages", [])
                    yield event

                else:
                    # Root orchestrator step — emit a trace row only when the
                    # AIMessage contains tool_calls (i.e. the agent is dispatching).
                    event = _interpret_orchestrator_node(result, ts, node, graph)
                    if event is not None:
                        if include_raw_messages:
                            event["raw_messages"] = result.get("messages", [])
                        yield event

            elif chunk_type == "messages":
                # Fires token-by-token during generation. We only stream
                # digest tokens when ALL of these hold:
                #  1. Root graph (ns is empty — NOT a subgraph)
                #  2. Model node generating text
                #  3. No tool_call_chunks (not a tool-dispatch turn)
                #  4. Root tools have executed at least once (not an early
                #     planning turn before any research has happened)
                # NOTE: metadata["langgraph_ns"] is unreliable (always None).
                # The chunk-level `ns` tuple is the authoritative namespace source.
                msg, metadata = data
                if (
                    isinstance(msg, AIMessageChunk)
                    and not ns
                    and metadata.get("langgraph_node") == "model"
                    and not msg.tool_call_chunks
                    and msg.content
                    and root_tools_executed
                ):
                    yield {"type": "digest", "token": msg.content}

        files: dict[str, str] = current_state.get("files") or {}
        sources = extract_sources(files)
        if sources:
            yield {"type": "sources", "sources": sources}

        duration = (datetime.now() - start).total_seconds()
        yield {
            "type": "done",
            "duration_s": duration,
            "run_date": start.strftime("%b %d, %H:%M"),
        }

        if include_raw_messages:
            yield {"type": "final_state", "state": current_state}

    except Exception as exc:
        yield {"type": "error", "message": str(exc)}
