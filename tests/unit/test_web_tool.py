"""Unit tests for TavilySearchTool.process.

Created by @pytholic on 2026.04.16
"""

import os

import pytest
from pytest_mock import MockerFixture

from deep_research_agent.tools.web_tool import TavilySearchTool


@pytest.fixture
def tool(mocker: MockerFixture) -> TavilySearchTool:
    mocker.patch.dict(os.environ, {"TAVILY_API_KEY": "test-key", "OPENAI_API_KEY": "test-key"})
    mocker.patch("deep_research_agent.tools.web_tool.TavilyClient")
    mocker.patch("deep_research_agent.tools.web_tool.init_chat_model")
    return TavilySearchTool()


@pytest.mark.parametrize(
    ("raw_result", "summarize_return", "expected_summary_prefix"),
    [
        pytest.param(
            {"title": "Test Page", "url": "https://example.com", "raw_content": "full content"},
            "LLM summary",
            "LLM summary",
            id="raw_content_present_uses_llm_summary",
        ),
        pytest.param(
            {"title": "Test Page", "url": "https://example.com", "raw_content": "full content"},
            None,
            "full content",
            id="summarize_returns_none_falls_back_to_truncated_raw",
        ),
        pytest.param(
            {
                "title": "Test Page",
                "url": "https://example.com",
                "raw_content": "",
                "content": "snippet",
            },
            None,
            "snippet",
            id="no_raw_content_uses_tavily_snippet",
        ),
    ],
)
def test_process_summary_fallback(
    tool: TavilySearchTool,
    mocker: MockerFixture,
    raw_result: dict,
    summarize_return: str | None,
    expected_summary_prefix: str,
) -> None:
    mocker.patch.object(tool, "summarize", return_value=summarize_return)

    results = tool.process([raw_result])

    assert len(results) == 1
    assert results[0].summary.startswith(expected_summary_prefix)
    assert results[0].title == "Test Page"
    assert results[0].url == "https://example.com"
