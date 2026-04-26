"""Utility functions for displaying messages and prompts in Jupyter notebooks."""

import json
from typing import Any

from langchain_core.messages import BaseMessage
from langchain_core.runnables import RunnableConfig
from langgraph.pregel import Pregel
from rich.console import Console
from rich.live import Live
from rich.markdown import Markdown
from rich.panel import Panel
from rich.table import Table
from rich.text import Text

from deep_research_agent.streaming import stream_events

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
    """Run the agent and display output via Rich console.

    Args:
        agent: Compiled LangGraph agent.
        query: Input dict passed to the agent.
        config: Optional LangGraph run config (currently unused, reserved for
            future passthrough to ``stream_events``).
        streaming: If True, stream the final response token-by-token.
    """
    _ = config
    digest_buf: list[str] = []
    sources_data: list[dict[str, Any]] = []
    final_state: dict[str, Any] = {}
    live: Live | None = None

    # Display the user's query
    user_content = ""
    msgs = query.get("messages", [])
    if msgs:
        first = msgs[0]
        user_content = first.get("content", "") if isinstance(first, dict) else str(first)
    if user_content:
        show_prompt(user_content, title="Query", border_style="blue")

    async for event in stream_events(
        agent,
        query,
        streaming=streaming,
        include_raw_messages=True,
    ):
        ev_type = event["type"]

        if ev_type == "trace":
            messages = event.get("raw_messages", [])
            console.print(f"Graph: {event.get('graph', 'root')}")
            console.print(f"Node: {event.get('node', event.get('label', 'unknown'))}")
            if messages:
                # Format the messages for display
                format_messages(messages)
            else:
                # Fallback to the compact single-line format:
                # "12:34:56 Orchestrator: Dispatching: task"
                label = event.get("label", "")
                message = event.get("message", "")
                console.print(f"[dim]{event.get('ts', '')}[/dim] {label}: {message}")

        elif ev_type == "digest":
            digest_buf.append(event["token"])
            if live is None:
                console.print()
                live = Live(console=console, refresh_per_second=8)
                live.start()
            live.update(_digest_panel("".join(digest_buf)))

        elif ev_type == "sources":
            sources_data = event["sources"]

        elif ev_type == "done":
            pass

        elif ev_type == "final_state":
            final_state = event.get("state", {})

        elif ev_type == "error":
            console.print(f"\n[bold red]Error:[/bold red] {event['message']}")

    if live is not None:
        live.update(_digest_panel("".join(digest_buf)))
        live.stop()

    if sources_data:
        _print_sources(sources_data)

    return final_state


def _digest_panel(md_text: str) -> Panel:
    """Build the streaming digest panel from accumulated markdown."""
    return Panel(
        Markdown(md_text),
        title="[bold green]Final Response[/bold green]",
        border_style="green",
        padding=(1, 2),
    )


def _print_sources(sources: list[dict[str, Any]]) -> None:
    """Display extracted sources as a Rich table."""
    if not sources:
        return

    table = Table(title="Sources", show_lines=True, title_style="bold cyan", title_justify="left")
    table.add_column("#", style="dim", width=3)
    table.add_column("Type", width=5)
    table.add_column("Title", min_width=30)
    table.add_column("URL", style="dim")

    for i, src in enumerate(sources, 1):
        badge = "[blue]arXiv[/blue]" if src["source_type"] == "arxiv" else "[green]web[/green]"
        table.add_row(str(i), badge, str(src["title"]), str(src["url"]))

    console.print()
    console.print(table)
