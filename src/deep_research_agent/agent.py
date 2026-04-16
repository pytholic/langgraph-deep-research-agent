"""Deep research agent assembly.

This module provides the public factory function for creating the deep research agent.
It assembles all tools, prompts, and sub-agent configurations into a compiled LangGraph graph.

Created by @pytholic on 2026.04.16
"""

from langchain.agents import create_agent
from langchain.chat_models import init_chat_model
from langgraph.pregel import Pregel

from deep_research_agent.prompts.summarize import RESEARCHER_INSTRUCTIONS
from deep_research_agent.prompts.system import (
    FILE_USAGE_INSTRUCTIONS,
    OUTPUT_FORMAT_INSTRUCTIONS,
    SUBAGENT_USAGE_INSTRUCTIONS,
    TODO_USAGE_INSTRUCTIONS,
)
from deep_research_agent.state import DeepAgentState
from deep_research_agent.task import _create_task_tool
from deep_research_agent.tools.files import ls, read_file, write_file
from deep_research_agent.tools.research import get_today_str, think_tool
from deep_research_agent.tools.todos import read_todos, write_todos
from deep_research_agent.tools.web import tavily_search


def create_deep_research_agent(
    model_name: str = "gpt-4o-mini",
    max_concurrent_research_units: int = 3,
    max_researcher_iterations: int = 3,
) -> Pregel:
    """Assemble and return the deep research agent graph.

    Args:
        model_name: LLM model identifier (default: gpt-4o-mini)
        max_concurrent_research_units: Max parallel sub-agents per iteration
        max_researcher_iterations: Max search calls per sub-agent

    Returns:
        Compiled LangGraph agent ready to invoke
    """
    model = init_chat_model(model=model_name, temperature=0.0)

    # Tools available to research sub-agents
    sub_agent_tools = [tavily_search, think_tool]

    # Tools available to the parent agent
    built_in_tools = [ls, read_file, write_file, write_todos, read_todos, think_tool]

    # Configure the research sub-agent
    research_sub_agent = {
        "name": "research-agent",
        "description": "Delegate research to the sub-agent researcher. Only give this researcher one topic at a time.",
        "prompt": RESEARCHER_INSTRUCTIONS.format(date=get_today_str()),
        "tools": ["tavily_search", "think_tool"],
    }

    # Create the task delegation tool (enables sub-agent context isolation)
    task_tool = _create_task_tool(sub_agent_tools, [research_sub_agent], model, DeepAgentState)

    delegation_tools = [task_tool]

    # Parent agent has access to all tools (search available for trivial cases)
    all_tools = sub_agent_tools + built_in_tools + delegation_tools

    # Format the sub-agent usage instructions with runtime parameters
    subagent_instructions = SUBAGENT_USAGE_INSTRUCTIONS.format(
        max_concurrent_research_units=max_concurrent_research_units,
        max_researcher_iterations=max_researcher_iterations,
    )

    # Assemble the full system prompt
    instructions = (
        "# TODO MANAGEMENT\n"
        + TODO_USAGE_INSTRUCTIONS
        + "\n\n"
        + "=" * 80
        + "\n\n"
        + "# FILE SYSTEM USAGE\n"
        + FILE_USAGE_INSTRUCTIONS
        + "\n\n"
        + "=" * 80
        + "\n\n"
        + "# SUB-AGENT DELEGATION\n"
        + subagent_instructions
        + "\n\n"
        + "=" * 80
        + "\n\n"
        + OUTPUT_FORMAT_INSTRUCTIONS
    )

    return create_agent(model, all_tools, system_prompt=instructions, state_schema=DeepAgentState)
