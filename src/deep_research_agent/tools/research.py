"""Shared research types, protocol, and utilities.

Defines the SearchToolProtocol that all search tool implementations must follow,
along with shared data types and utility functions.

Created by @pytholic on 2026.04.15
"""

from dataclasses import dataclass
from datetime import datetime
from typing import Protocol, runtime_checkable

from langchain_core.tools import tool
from pydantic import BaseModel, Field


class Summary(BaseModel):
    """LLM-structured output schema for content summarization."""

    filename: str = Field(description="Name of the file to store.")
    summary: str = Field(description="Key learnings from the content.")


@dataclass
class SearchResult:
    """Processed result from any search source."""

    title: str
    url: str
    summary: str
    filename: str
    raw_content: str


@runtime_checkable
class SearchToolProtocol(Protocol):
    """Protocol defining the interface for all search tool implementations."""

    def search(self, query: str, **kwargs: object) -> list[dict[str, object]]:
        """Execute a raw search query and return API results.

        Args:
            query: Search query string
            **kwargs: Source-specific search parameters

        Returns:
            Raw results from the search API
        """
        ...

    def process(self, results: list[dict[str, object]]) -> list[SearchResult]:
        """Process raw API results into standardized SearchResult objects.

        Calls summarize() internally for each result where applicable.

        Args:
            results: Raw results from search()

        Returns:
            List of processed SearchResult objects
        """
        ...

    def summarize(self, content: str) -> str | None:
        """Summarize raw content using an LLM.

        Args:
            content: Raw text content to summarize

        Returns:
            Summarized content string, or None if summarization is not applicable
        """
        ...


def append_searched_query(searched: list[str], query: str) -> tuple[list[str], str]:
    """Append a query to the searched list and return the updated list with a context footer.

    Args:
        searched: Queries already searched this session
        query: The query just executed

    Returns:
        Tuple of (updated_searched_list, footer_text_to_append_to_tool_message)
    """
    updated = [*searched, query]
    lines = "\n".join(f"- {q}" for q in updated)
    footer = (
        f"\n\n🔍 Queries searched this session:\n{lines}"
        "\n\nOnly search again if your next query covers genuinely different ground."
    )
    return updated, footer


def get_today_str() -> str:
    """Get current date in a human-readable format."""
    return datetime.now().strftime("%a %b %-d, %Y")


@tool(parse_docstring=True)
def think_tool(reflection: str) -> str:
    """Tool for strategic reflection on research progress and decision-making.

    Use this tool after each search to analyze results and plan next steps systematically.
    This creates a deliberate pause in the research workflow for quality decision-making.

    When to use:
    - After receiving search results: What key information did I find?
    - Before deciding next steps: Do I have enough to answer comprehensively?
    - When assessing research gaps: What specific information am I still missing?
    - Before concluding research: Can I provide a complete answer now?
    - How complex is the question: Have I reached the number of search limits?

    Reflection should address:
    1. Analysis of current findings - What concrete information have I gathered?
    2. Gap assessment - What crucial information is still missing?
    3. Quality evaluation - Do I have sufficient evidence/examples for a good answer?
    4. Strategic decision - Should I continue searching or provide my answer?

    Args:
        reflection: Your detailed reflection on research progress, findings, gaps, and next steps

    Returns:
        Confirmation that reflection was recorded for decision-making
    """
    return f"Reflection recorded: {reflection}"
