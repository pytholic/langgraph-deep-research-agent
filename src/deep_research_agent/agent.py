"""Deep research agent assembly.

This module provides the public factory function for creating the deep research agent.
It assembles all tools, prompts, and sub-agent configurations into a compiled LangGraph graph.

Created by @pytholic on 2026.04.16
"""

from langchain.agents import create_agent
from langgraph.pregel import Pregel

from deep_research_agent.models import OllamaModel, OpenAIModel, Provider, create_model
from deep_research_agent.prompts.summarize import RESEARCHER_INSTRUCTIONS
from deep_research_agent.prompts.system import (
    FILE_USAGE_INSTRUCTIONS,
    OUTPUT_FORMAT_INSTRUCTIONS,
    SUBAGENT_USAGE_INSTRUCTIONS,
    TODO_USAGE_INSTRUCTIONS,
)
from deep_research_agent.state import DeepAgentState
from deep_research_agent.task import _create_task_tool
from deep_research_agent.tools.arxiv_tool import arxiv_search
from deep_research_agent.tools.files import ls, read_file, write_file
from deep_research_agent.tools.research import get_today_str, think_tool
from deep_research_agent.tools.todos import read_todos, write_todos
from deep_research_agent.tools.web_tool import tavily_search


def create_deep_research_agent(
    orchestrator_provider: str = Provider.OLLAMA,
    orchestrator_model_name: str = OllamaModel.GEMMA4_E2B,
    researcher_provider: str = Provider.OPENAI,
    researcher_model_name: str = OpenAIModel.GPT5_NANO,
    max_concurrent_research_units: int = 3,
    max_researcher_iterations: int = 8,
) -> Pregel:
    """Assemble and return the deep research agent graph.

    Args:
        orchestrator_provider: Provider for the orchestrator model (e.g. ``"ollama"``).
        orchestrator_model_name: Model name for the orchestrator (synthesis, planning).
        researcher_provider: Provider for researcher sub-agents (e.g. ``"openai"``).
        researcher_model_name: Model name for researcher sub-agents (tool calls, search).
        max_concurrent_research_units: Max parallel sub-agents per iteration.
        max_researcher_iterations: Max search calls per sub-agent.

    Returns:
        Compiled LangGraph agent ready to invoke.
    """
    orchestrator_model = create_model(orchestrator_provider, orchestrator_model_name)
    researcher_model = create_model(researcher_provider, researcher_model_name)

    sub_agent_tools = [read_file, ls, tavily_search, arxiv_search, think_tool]
    research_sub_agent = {
        "name": "research-agent",
        "description": "Delegate research to the sub-agent researcher. Only give this researcher one topic at a time.",
        "prompt": RESEARCHER_INSTRUCTIONS.format(date=get_today_str()),
        "tools": ["read_file", "ls", "tavily_search", "arxiv_search", "think_tool"],
    }
    task_tool = _create_task_tool(
        sub_agent_tools, [research_sub_agent], researcher_model, DeepAgentState
    )

    all_tools = [ls, read_file, write_file, write_todos, read_todos, think_tool, task_tool]
    instructions = _build_system_prompt(max_concurrent_research_units, max_researcher_iterations)

    return create_agent(
        orchestrator_model, all_tools, system_prompt=instructions, state_schema=DeepAgentState
    )


def _build_system_prompt(max_concurrent_research_units: int, max_researcher_iterations: int) -> str:
    """Assemble the orchestrator system prompt from section constants.

    Args:
        max_concurrent_research_units: Injected into sub-agent delegation instructions.
        max_researcher_iterations: Injected into sub-agent delegation instructions.

    Returns:
        Full system prompt string.
    """
    subagent_instructions = SUBAGENT_USAGE_INSTRUCTIONS.format(
        max_concurrent_research_units=max_concurrent_research_units,
        max_researcher_iterations=max_researcher_iterations,
    )
    sep = "\n\n" + "=" * 80 + "\n\n"
    return (
        "# TODO MANAGEMENT\n"
        + TODO_USAGE_INSTRUCTIONS
        + sep
        + "# FILE SYSTEM USAGE\n"
        + FILE_USAGE_INSTRUCTIONS
        + sep
        + "# SUB-AGENT DELEGATION\n"
        + subagent_instructions
        + sep
        + OUTPUT_FORMAT_INSTRUCTIONS
    )
