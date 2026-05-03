"""Arxiv search tool implementation.

Implements academic paper search using the Arxiv API,
and exposes a LangGraph-compatible @tool wrapper.

Created by @pytholic on 2026.04.15
"""

import functools
from typing import Annotated, Final

import arxiv
from langchain_core.messages import ToolMessage
from langchain_core.tools import InjectedToolArg, InjectedToolCallId, tool
from langgraph.prebuilt import InjectedState
from langgraph.types import Command

from deep_research_agent.state import DeepAgentState
from deep_research_agent.tools.research import SearchResult, append_searched_query, get_today_str

ARXIV_PAGE_SIZE: Final[int] = 5
ARXIV_DELAY_SECONDS: Final[float] = 3.0
ARXIV_NUM_RETRIES: Final[int] = 0


class ArxivSearchTool:
    """Academic paper search implementation using the Arxiv API."""

    def __init__(self) -> None:
        """Initialize the Arxiv search tool."""
        self._client = arxiv.Client(
            page_size=ARXIV_PAGE_SIZE,
            delay_seconds=ARXIV_DELAY_SECONDS,
            num_retries=ARXIV_NUM_RETRIES,
        )

    def search(
        self,
        query: str,
        max_results: int = 3,
        sort_by: arxiv.SortCriterion = arxiv.SortCriterion.Relevance,
    ) -> list[arxiv.Result]:
        """Execute an Arxiv paper search.

        Args:
            query: Search query string
            max_results: Maximum number of results to return
            sort_by: Sort criterion for results
            **kwargs: Source-specific search parameters (e.g. max_results, categories)

        Returns:
            Raw results list from the Arxiv API
        """
        search = arxiv.Search(
            query=query,
            max_results=max_results,
            sort_by=sort_by,
        )
        return list(self._client.results(search))

    def process(self, results: list[arxiv.Result]) -> list[SearchResult]:
        """Process raw Arxiv results into SearchResult objects.

        Args:
            results: Raw results from search()

        Returns:
            List of processed SearchResult objects
        """
        processed: list[SearchResult] = []

        for result in results:
            processed.append(
                SearchResult(
                    title=result.title,
                    url=result.entry_id,
                    summary=result.summary,
                    filename="",
                    raw_content="",
                )
            )

        return processed


@functools.lru_cache(maxsize=1)
def _get_arxiv_search_tool() -> ArxivSearchTool:
    """Get the arxiv search tool."""
    return ArxivSearchTool()


@tool(parse_docstring=True)
def arxiv_search(
    query: str,
    state: Annotated[DeepAgentState, InjectedState],
    tool_call_id: Annotated[str, InjectedToolCallId],
    max_results: Annotated[int, InjectedToolArg] = 3,
    sort_by: Annotated[arxiv.SortCriterion, InjectedToolArg] = arxiv.SortCriterion.Relevance,
) -> Command:
    """Search Arxiv for academic papers and save results to files.

    Searches the Arxiv API for papers matching the query, saves full content
    to files for context offloading, and returns minimal summaries.

    Args:
        query: Search query to execute (paper title, topic, or keywords)
        state: Injected agent state for file storage
        tool_call_id: Injected tool call identifier
        max_results: Maximum number of results to return (default: 3)
        sort_by: Sort criterion for results (default: Relevance)

    Returns:
        Command that saves full results to files and provides minimal summary
    """
    searched_queries = state.get("searched_queries", [])

    tool = _get_arxiv_search_tool()
    try:
        raw = tool.search(query, max_results=max_results, sort_by=sort_by)
    except arxiv.HTTPError as exc:
        err_msg = f"Arxiv API request failed (HTTP {exc.status}). "
        if exc.status == 429:
            err_msg += (
                "Rate limited: space out arxiv_search calls (~1 request per 3s per API terms). "
            )
        err_msg += "Try a narrower query or continue with web search only."
        return Command(
            update={
                "messages": [ToolMessage(err_msg, tool_call_id=tool_call_id)],
            }
        )

    results = tool.process(raw)

    files = dict(state.get("files", {}))
    prefix = state.get("file_prefix", "")
    file_tag = f"{prefix}_arxiv" if prefix else "arxiv"
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
        )
        files[filename] = file_content
        saved_files.append(filename)
        summaries.append(f"- {filename}: {result.title}")

    updated_searched, searched_footer = append_searched_query(searched_queries, query)
    file_list = "\n".join(f"  - {f}" for f in saved_files)
    summary_text = (
        f"📄 Found {len(results)} paper(s) for '{query}':\n\n"
        + "\n".join(summaries)
        + f"\n\nSaved files:\n{file_list}"
        + searched_footer
    )

    return Command(
        update={
            "files": files,
            "searched_queries": updated_searched,
            "messages": [ToolMessage(summary_text, tool_call_id=tool_call_id)],
        }
    )
