"""Unit tests for ArxivSearchTool.process.

Created by @pytholic on 2026.04.21
"""

from unittest.mock import MagicMock

import arxiv
import pytest

from deep_research_agent.tools.arxiv_tool import ArxivSearchTool


@pytest.fixture
def tool() -> ArxivSearchTool:
    return ArxivSearchTool()


def _make_arxiv_result(title: str = "Test Paper", summary: str = "Abstract text") -> arxiv.Result:
    result = MagicMock(spec=arxiv.Result)
    result.title = title
    result.summary = summary
    result.entry_id = "https://arxiv.org/abs/2401.00001"
    return result


def test_process_maps_fields_correctly(tool: ArxivSearchTool) -> None:
    result = _make_arxiv_result(title="LLM Agents Survey", summary="We survey LLM agents.")

    processed = tool.process([result])

    assert len(processed) == 1
    assert processed[0].title == "LLM Agents Survey"
    assert processed[0].url == "https://arxiv.org/abs/2401.00001"
    assert processed[0].summary == "We survey LLM agents."
    assert processed[0].raw_content == ""


def test_process_empty_results_returns_empty_list(tool: ArxivSearchTool) -> None:
    assert tool.process([]) == []


def test_process_leaves_filename_empty_for_tool_level_assignment(tool: ArxivSearchTool) -> None:
    """Filenames are assigned at the tool-call level (arxiv_001.md etc), not in process()."""
    result = _make_arxiv_result(title="Some Paper")

    processed = tool.process([result])

    assert processed[0].filename == ""
