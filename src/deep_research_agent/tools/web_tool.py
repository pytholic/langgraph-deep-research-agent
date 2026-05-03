"""Tavily web search tool implementation.

Implements SearchToolProtocol for web search using the Tavily API,
and exposes a LangGraph-compatible @tool wrapper.

Created by @pytholic on 2026.04.15
"""

import functools
from typing import Annotated, Literal

from langchain_core.messages import HumanMessage, ToolMessage
from langchain_core.tools import InjectedToolArg, InjectedToolCallId, tool
from langchain_ollama import ChatOllama
from langgraph.prebuilt import InjectedState
from langgraph.types import Command
from tavily import TavilyClient

from deep_research_agent.prompts.summarize import SUMMARIZE_WEB_SEARCH
from deep_research_agent.state import DeepAgentState
from deep_research_agent.tools.research import SearchResult, append_searched_query, get_today_str


class TavilySearchTool:
    """Web search implementation using the Tavily API."""

    def __init__(self, summarization_model_name: str = "gemma4:e2b") -> None:
        """Initialize the Tavily search tool.

        Args:
            summarization_model_name: LLM model to use for content summarization
        """
        self._client = TavilyClient()
        # self._summarization_model = init_chat_model(model=summarization_model_name)
        self._summarization_model = ChatOllama(model=summarization_model_name, num_ctx=65536)

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

    def process(
        self, results: list[dict[str, object]], *, summarize: bool = False
    ) -> list[SearchResult]:
        """Process raw Tavily results into SearchResult objects.

        By default uses Tavily's content snippet as the summary (fast, non-blocking).
        Set ``summarize=True`` to invoke LLM-based summarization (slow, serializes on Ollama).

        Args:
            results: Raw results from search()
            summarize: Whether to run LLM summarization (default False for parallelism)

        Returns:
            List of processed SearchResult objects
        """
        processed: list[SearchResult] = []

        for result in results:
            raw_content = str(result.get("raw_content") or result.get("content", ""))
            summary_text: str

            if summarize and raw_content:
                summarized = self.summarize(raw_content)
                summary_text = summarized if summarized else raw_content[:1000]
            else:
                content_snippet = str(result.get("content", ""))
                summary_text = content_snippet if content_snippet else raw_content[:1000]

            processed.append(
                SearchResult(
                    title=str(result.get("title", "")),
                    url=str(result.get("url", "")),
                    summary=summary_text,
                    filename="",
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
            result = self._summarization_model.invoke(
                [
                    HumanMessage(
                        content=SUMMARIZE_WEB_SEARCH.format(
                            webpage_content=content, date=get_today_str()
                        )
                    )
                ]
            )
            text = result.content
            if isinstance(text, str):
                return text
            if isinstance(text, list):
                return "\n".join(
                    str(b.get("text", "")) if isinstance(b, dict) else str(b) for b in text
                )
            return str(text)
        except Exception:
            return None


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
    searched_queries = state.get("searched_queries", [])

    tool = _get_web_search_tool()
    raw = tool.search(query, max_results=max_results, topic=topic)
    results = tool.process(raw)

    files = dict(state.get("files", {}))
    prefix = state.get("file_prefix", "")
    file_tag = f"{prefix}_web" if prefix else "web"
    existing = sum(1 for k in files if k.startswith(f"{file_tag}_"))
    saved_files: list[str] = []
    summaries: list[str] = []

    for i, result in enumerate(results):
        filename = f"{file_tag}_{existing + i + 1:03d}.md"
        file_content = (
            f"# {result.title}\n\n"
            f"**URL:** {result.url}\n"
            f"**Query:** {query}\n"
            f"**Date:** {get_today_str()}\n\n"
            f"## Summary\n{result.summary}\n\n"
            f"## Raw Content\n{result.raw_content or 'No raw content available'}\n"
        )
        files[filename] = file_content
        saved_files.append(filename)
        summaries.append(f"- {filename}: {result.title}")

    updated_searched, searched_footer = append_searched_query(searched_queries, query)

    file_list = "\n".join(f"  - {f}" for f in saved_files)
    summary_text = (
        f"🔍 Found {len(results)} result(s) for '{query}':\n\n"
        + "\n".join(summaries)
        + f"\n\nn📄 Saved files:\n{file_list}"
        + searched_footer
    )

    return Command(
        update={
            "files": files,
            "searched_queries": updated_searched,
            "messages": [ToolMessage(summary_text, tool_call_id=tool_call_id)],
        }
    )
