"""Shared stream interpretation for the deep research agent.

Consumes raw LangGraph v2 stream chunks from `agent.astream()` and yields
structured, output-agnostic event dicts. Both the FastAPI server and the CLI
runner consume this single generator — eliminating interpretation duplication.

Created by @pytholic on 2026.04.24
"""

import sys
from collections.abc import Generator
from pathlib import Path
from typing import Any

from dotenv import load_dotenv
from langchain.agents import create_agent
from langchain.chat_models import init_chat_model
from langchain.messages import HumanMessage
from langchain.tools import tool
from langchain_core.messages import AIMessageChunk
from langgraph.pregel import Pregel

load_dotenv(override=True)

sys.path.insert(0, str(Path(__file__).parent))


@tool
def multiply(a: int, b: int) -> int:
    """Multiply a and b.

    Args:
        a: first int
        b: second int
    """
    return a * b


model_name = "gpt-4o-mini"
model = init_chat_model(model=model_name, temperature=0.0)
agent = create_agent(
    model=model,
    tools=[multiply],
    system_prompt="You are a helpful assistant that can multiply two numbers. Always use the multiply tool to multiply two numbers.",
)

query = HumanMessage(content="What is 2 * 3?")

# for chunk in agent.stream(
#     {"messages": [query]}, stream_mode=["updates", "values", "messages"], version="v2"
# ):
#     chunk_type: str = chunk["type"]
#     data = chunk.get("data")
#     ns: tuple[str, ...] = chunk.get("ns", ())

#     # for the main agent, filter and print only last message

#     if chunk_type == "values":
#         if not ns:  # belongs to the main agent
#             pass
#             # print(f"Data: {data}")

#     elif chunk_type == "updates":
#         node, result = next(iter(data.items()))

#         if node == "tools":
#             print(f"Node: {node}")
#             print(f"Result: {result}")

#     elif chunk_type == "messages":
#         msg, metadata = data
#         print(f"Msg: {msg}")
#         print(f"Metadata: {metadata}")
#         if (
#             isinstance(msg, AIMessageChunk)
#             and metadata.get("langgraph_node") == "model"
#             and not msg.tool_call_chunks
#             and msg.content
#         ):
#             print(f"Token: {msg.content}")


def stream_events(agent: Pregel, query: HumanMessage) -> Generator[dict[str, Any]]:
    """Stream events from the agent.

    Args:
        agent: The agent to stream events from.
        query: The query to send to the agent.

    Yields:
        A dictionary containing the event type and data.
    """
    for chunk in agent.stream(
        {"messages": [query]}, stream_mode=["updates", "values", "messages"], version="v2"
    ):
        chunk_type: str = chunk["type"]
        data = chunk.get("data")
        ns: tuple[str, ...] = chunk.get("ns", ())

        if chunk_type == "values":
            if not ns:  # belongs to the main agent
                pass
                # yield {"type": "values", "data": data}

        elif chunk_type == "updates":
            node, result = next(iter(data.items()))
            if node == "tools":
                yield {
                    "type": "updates",
                    "node": node,
                    "result": result.get("messages", []),
                    "tool_detail": _extract_tool_detail(result.get("messages", [])),
                }
            elif ns:
                pass
            else:
                chunk = _interpret_orchestrator_node(result)
                if chunk:
                    yield chunk

        elif chunk_type == "messages":
            msg, metadata = data
            if (
                isinstance(msg, AIMessageChunk)
                and metadata.get("langgraph_node") == "model"
                and not msg.tool_call_chunks
                and msg.content
            ):
                yield {"type": "output", "token": msg.content}

    yield {"type": "done"}


TOOL_RESULT_MAX_LINES = 6


def _extract_tool_detail(msgs: list[object]) -> str:
    """Extract a short detail string from the last tool result message."""
    if not msgs:
        return ""
    last = msgs[-1]
    content = getattr(last, "content", "")
    if isinstance(content, str) and content:
        lines = content.strip().splitlines()
        lines = lines[:TOOL_RESULT_MAX_LINES]

    if msgs and hasattr(msgs[-1], "name"):
        tool_name = getattr(msgs[-1], "name", None) or "tool"

    if tool_name and lines:
        return {
            "tool_name": tool_name,
            "detail": lines,
        }

    return ""


def _interpret_orchestrator_node(result: dict[str, Any]) -> dict[str, Any]:
    """Interpret the orchestrator node.

    Args:
        result: The result of the orchestrator node.

    Returns:
        A dictionary containing the content and tool calls.
    """
    root_msgs: list[object] = result.get("messages", [])
    last = root_msgs[-1] if root_msgs else None
    if last is None or (hasattr(last, "tool_calls") and not getattr(last, "tool_calls", None)):
        return None
    tool_calls: list[dict[str, Any]] = getattr(last, "tool_calls", [])
    return {
        "content": last.content,
        "tool_calls": tool_calls,
    }


for chunk in stream_events(agent, query):
    print(chunk)
