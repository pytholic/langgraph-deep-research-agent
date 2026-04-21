"""Utility functions for displaying messages and prompts in Jupyter notebooks."""

import json
from typing import Any

from langchain_core.messages import AIMessageChunk, BaseMessage
from langchain_core.runnables import RunnableConfig
from langgraph.pregel import Pregel
from langgraph.types import StreamMode
from rich.console import Console
from rich.panel import Panel
from rich.text import Text

console = Console()


def format_message_content(message: BaseMessage) -> str:
    """Convert message content to displayable string."""
    parts: list[str] = []
    tool_calls_processed = False

    if isinstance(message.content, str):
        parts.append(message.content)
    elif isinstance(message.content, list):
        for item in message.content:
            if item.get("type") == "text":
                parts.append(item["text"])
            elif item.get("type") == "tool_use":
                parts.append(f"\n🔧 Tool Call: {item['name']}")
                parts.append(f"   Args: {json.dumps(item['input'], indent=2, ensure_ascii=False)}")
                parts.append(f"   ID: {item.get('id', 'N/A')}")
                tool_calls_processed = True
    else:
        parts.append(str(message.content))

    if not tool_calls_processed and hasattr(message, "tool_calls") and message.tool_calls:
        for tool_call in message.tool_calls:
            parts.append(f"\n🔧 Tool Call: {tool_call['name']}")
            parts.append(f"   Args: {json.dumps(tool_call['args'], indent=2, ensure_ascii=False)}")
            parts.append(f"   ID: {tool_call['id']}")

    return "\n".join(parts)


def format_messages(messages: list[BaseMessage]) -> None:
    """Format and display a list of messages with Rich formatting."""
    for m in messages:
        msg_type = m.__class__.__name__.replace("Message", "")
        content = format_message_content(m)

        if msg_type == "Human":
            console.print(Panel(content, title="🧑 Human", border_style="blue"))
        elif msg_type == "Ai":
            console.print(Panel(content, title="🤖 Assistant", border_style="green"))
        elif msg_type == "Tool":
            console.print(Panel(content, title="🔧 Tool Output", border_style="yellow"))
        else:
            console.print(Panel(content, title=f"📝 {msg_type}", border_style="white"))


def show_prompt(prompt_text: str, title: str = "Prompt", border_style: str = "blue") -> None:
    """Display a prompt with rich formatting and XML tag highlighting.

    Args:
        prompt_text: The prompt string to display
        title: Title for the panel (default: "Prompt")
        border_style: Border color style (default: "blue")
    """
    formatted_text = Text(prompt_text)
    formatted_text.highlight_regex(r"<[^>]+>", style="bold blue")
    formatted_text.highlight_regex(r"##[^#\n]+", style="bold magenta")
    formatted_text.highlight_regex(r"###[^#\n]+", style="bold cyan")

    console.print(
        Panel(
            formatted_text,
            title=f"[bold green]{title}[/bold green]",
            border_style=border_style,
            padding=(1, 2),
        )
    )


async def stream_agent(
    agent: Pregel,
    query: dict[str, Any],
    config: RunnableConfig | None = None,
    streaming: bool = True,
) -> dict[str, Any]:
    """Run the agent and display output.

    Args:
        agent: Compiled LangGraph agent.
        query: Input dict passed to the agent.
        config: Optional LangGraph run config.
        streaming: If True, stream the final response token-by-token via the
            "messages" mode and suppress its duplicate in "updates". If False,
            display all output as formatted blocks via "updates" only.
    """
    current_state: dict[str, Any] = {}
    streaming_started = False
    stream_modes: list[StreamMode] = ["updates", "messages"] if streaming else ["updates", "values"]

    async for chunk in agent.astream(
        query,
        stream_mode=stream_modes,
        subgraphs=True,
        config=config,
        version="v2",
    ):
        chunk_type = chunk["type"]

        if chunk_type == "updates":
            event: dict[str, Any] = chunk["data"]
            graph_name: tuple[str, ...] = chunk["ns"]
            node, result = next(iter(event.items()))

            # In streaming mode, skip the "model" node update only when it is a
            # plain text response (no tool calls) — that content was already
            # streamed token-by-token via "messages". Planning/tool-dispatch
            # steps from "model" still have tool_calls and should be shown.
            if streaming and node == "model":
                msgs = result.get("messages", [])
                last = msgs[-1] if msgs else None
                if last is not None and hasattr(last, "tool_calls") and not last.tool_calls:
                    continue

            console.print(f"Graph: {graph_name[-1] if graph_name else 'root'}")
            console.print(f"Node: {node}")

            for key in result.keys():
                if "messages" in key:
                    format_messages(result[key])
                    break

        elif chunk_type == "messages":
            msg, metadata = chunk["data"]
            # Only stream tokens from the root orchestrator "model" node.
            # Skip tool call chunks — those are handled by "updates".
            # TODO: replace this heuristic (filtering "model" node + no tool_call_chunks)
            # with a dedicated terminal "format_response" node in the graph definition.
            # That gives a clean, unambiguous stream target for the UI.
            if (
                isinstance(msg, AIMessageChunk)
                and metadata["langgraph_node"] == "model"
                and not msg.tool_call_chunks
                and msg.content
            ):
                if not streaming_started:
                    console.print("\n[bold green]Final Response:[/bold green]")
                    streaming_started = True
                console.print(msg.content, end="")

        elif chunk_type == "values":
            current_state = chunk["data"]

    if streaming_started:
        console.print()

    return current_state
