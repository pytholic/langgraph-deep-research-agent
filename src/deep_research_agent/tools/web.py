"""Tavily web search tool implementation.

Implements SearchToolProtocol for web search using the Tavily API,
and exposes a LangGraph-compatible @tool wrapper.

Created by @pytholic on 2026.04.15
"""

import base64
import functools
import os
import uuid
from typing import Annotated, Literal

from langchain.chat_models import init_chat_model
from langchain_core.messages import HumanMessage, ToolMessage
from langchain_core.tools import InjectedToolArg, InjectedToolCallId, tool
from langgraph.prebuilt import InjectedState
from langgraph.types import Command
from tavily import TavilyClient

from deep_research_agent.prompts.summarize import SUMMARIZE_WEB_SEARCH
from deep_research_agent.state import DeepAgentState
from deep_research_agent.tools.research import SearchResult, Summary, get_today_str


class TavilySearchTool:
    """Web search implementation using the Tavily API."""

    def __init__(self, summarization_model_name: str = "gpt-4o-mini") -> None:
        """Initialize the Tavily search tool.

        Args:
            summarization_model_name: LLM model to use for content summarization
        """
        self._client = TavilyClient()
        self._summarization_model = init_chat_model(model=summarization_model_name)

    def search(
        self,
        query: str,
        max_results: int = 1,
        topic: Literal["general", "news", "finance"] = "general",
        **kwargs: object,
    ) -> list[dict[str, object]]:
        """Execute a Tavily web search.

        Args:
            query: Search query string
            max_results: Maximum number of results to return
            topic: Topic filter for search results
            **kwargs: Unused

        Returns:
            Raw results list from the Tavily API
        """
        response = self._client.search(
            query=query,
            max_results=max_results,
            topic=topic,
            include_raw_content=True,
        )
        return response["results"]  # type: ignore[return-value]

    def process(self, results: list[dict[str, object]]) -> list[SearchResult]:
        """Process raw Tavily results into SearchResult objects.

        Summarizes raw content where available, falls back to Tavily's snippet.

        Args:
            results: Raw results from search()

        Returns:
            List of processed SearchResult objects
        """
        processed: list[SearchResult] = []

        for result in results:
            raw_content = str(result.get("raw_content") or result.get("content", ""))
            summary_text: str

            if raw_content:
                summarized = self.summarize(raw_content)
                summary_text = summarized if summarized else raw_content[:1000]
                filename = self._make_filename("search_result.md")
            else:
                summary_text = str(result.get("content", "No content available."))
                filename = self._make_filename("search_result.md")

            processed.append(
                SearchResult(
                    title=str(result.get("title", "")),
                    url=str(result.get("url", "")),
                    summary=summary_text,
                    filename=filename,
                    raw_content=raw_content,
                )
            )

        return processed

    def summarize(self, content: str) -> str | None:
        """Summarize webpage content using the configured LLM.

        Args:
            content: Raw webpage content to summarize

        Returns:
            Summary string, or None if summarization fails
        """
        try:
            structured_model = self._summarization_model.with_structured_output(Summary)
            result = structured_model.invoke(
                [
                    HumanMessage(
                        content=SUMMARIZE_WEB_SEARCH.format(
                            webpage_content=content, date=get_today_str()
                        )
                    )
                ]
            )
            summary = result if isinstance(result, Summary) else None
            return summary.summary if summary else None
        except Exception:
            return None

    def _make_filename(self, base: str) -> str:
        """Generate a unique filename from a base name.

        Args:
            base: Base filename (may or may not include extension)

        Returns:
            Unique filename with uid suffix
        """
        uid = base64.urlsafe_b64encode(uuid.uuid4().bytes).rstrip(b"=").decode("ascii")[:8]
        name, ext = os.path.splitext(base)
        return f"{name}_{uid}{ext or '.md'}"


@functools.lru_cache(maxsize=1)
def _get_web_search_tool() -> TavilySearchTool:
    """Get the web search tool."""
    return TavilySearchTool()


@tool(parse_docstring=True)
def tavily_search(
    query: str,
    state: Annotated[DeepAgentState, InjectedState],
    tool_call_id: Annotated[str, InjectedToolCallId],
    max_results: Annotated[int, InjectedToolArg] = 1,
    topic: Annotated[Literal["general", "news", "finance"], InjectedToolArg] = "general",
) -> Command:
    """Search the web and save detailed results to files while returning minimal context.

    Performs web search and saves full content to files for context offloading.
    Returns only essential information to help the agent decide on next steps.

    Args:
        query: Search query to execute
        state: Injected agent state for file storage
        tool_call_id: Injected tool call identifier
        max_results: Maximum number of results to return (default: 1)
        topic: Topic filter - 'general', 'news', or 'finance' (default: 'general')

    Returns:
        Command that saves full results to files and provides minimal summary
    """
    tool = _get_web_search_tool()
    raw = tool.search(query, max_results=max_results, topic=topic)
    results = tool.process(raw)

    files = state.get("files", {})
    saved_files: list[str] = []
    summaries: list[str] = []

    for result in results:
        file_content = (
            f"# Search Result: {result.title}\n\n"
            f"**URL:** {result.url}\n"
            f"**Query:** {query}\n"
            f"**Date:** {get_today_str()}\n\n"
            f"## Summary\n{result.summary}\n\n"
            f"## Raw Content\n{result.raw_content or 'No raw content available'}\n"
        )
        files[result.filename] = file_content
        saved_files.append(result.filename)
        summaries.append(f"- {result.filename}: {result.summary}...")

    summary_text = (
        f"🔍 Found {len(results)} result(s) for '{query}':\n\n"
        + "\n".join(summaries)
        + f"\n\n📄 Files saved: {', '.join(saved_files)}"
        + "\n\n💡 Use read_file() to access full details when needed."
    )

    return Command(
        update={
            "files": files,
            "messages": [ToolMessage(summary_text, tool_call_id=tool_call_id)],
        }
    )
