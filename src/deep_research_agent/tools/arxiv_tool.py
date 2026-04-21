"""Arxiv search tool implementation.

Implements academic paper search using the Arxiv API,
and exposes a LangGraph-compatible @tool wrapper.

Created by @pytholic on 2026.04.15
"""

import base64
import functools
import os
import uuid
from typing import Annotated

import arxiv
from langchain_core.messages import ToolMessage
from langchain_core.tools import InjectedToolArg, InjectedToolCallId, tool
from langgraph.prebuilt import InjectedState
from langgraph.types import Command

from deep_research_agent.state import DeepAgentState
from deep_research_agent.tools.research import SearchResult, get_today_str


class ArxivSearchTool:
    """Academic paper search implementation using the Arxiv API."""

    def __init__(self) -> None:
        """Initialize the Arxiv search tool."""
        self._client = arxiv.Client()

    def search(
        self,
        query: str,
        max_results: int = 1,
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

        For now we will use abstract as the summary.
        TODO: Implement  llm-basedsummarization.

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
                    filename=self._make_filename(result.title),
                    raw_content="",
                )
            )

        return processed

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
def _get_arxiv_search_tool() -> ArxivSearchTool:
    """Get the arxiv search tool."""
    return ArxivSearchTool()


@tool(parse_docstring=True)
def arxiv_search(
    query: str,
    state: Annotated[DeepAgentState, InjectedState],
    tool_call_id: Annotated[str, InjectedToolCallId],
    max_results: Annotated[int, InjectedToolArg] = 1,
    sort_by: Annotated[arxiv.SortCriterion, InjectedToolArg] = arxiv.SortCriterion.SubmittedDate,
) -> Command:
    """Search Arxiv for academic papers and save results to files.

    Searches the Arxiv API for papers matching the query, saves full content
    to files for context offloading, and returns minimal summaries.

    Args:
        query: Search query to execute (paper title, topic, or keywords)
        state: Injected agent state for file storage
        tool_call_id: Injected tool call identifier
        max_results: Maximum number of results to return (default: 1)
        sort_by: Sort criterion for results (default: SubmittedDate)

    Returns:
        Command that saves full results to files and provides minimal summary
    """
    tool = _get_arxiv_search_tool()
    raw = tool.search(query, max_results=max_results, sort_by=sort_by)
    results = tool.process(raw)

    files = state.get("files", {})
    saved_files: list[str] = []
    summaries: list[str] = []

    for result in results:
        file_content = (
            f"# Arxiv Paper: {result.title}\n\n"
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
        f"📄 Found {len(results)} paper(s) for '{query}':\n\n"
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
