"""Task delegation tools for context isolation through sub-agents.

This module provides the core infrastructure for creating and managing sub-agents
with isolated contexts. Sub-agents prevent context clash by operating with clean
context windows containing only their specific task description.

Created by @pytholic on 2026.04.08
"""

from typing import Annotated, NotRequired, cast

from langchain.agents import create_agent
from langchain_core.messages import HumanMessage, ToolMessage
from langchain_core.tools import BaseTool, InjectedToolCallId, tool
from langgraph.prebuilt import InjectedState
from langgraph.types import Command
from typing_extensions import TypedDict

from deep_research_agent.prompts.system import TASK_DESCRIPTION_PREFIX
from deep_research_agent.state import DeepAgentState


class SubAgent(TypedDict):
    """Configuration for a specialized sub-agent."""

    name: str
    description: str
    prompt: str
    tools: NotRequired[list[str]]


def _create_task_tool(
    tools: list[BaseTool],
    subagents: list[SubAgent],
    model: object,
    state_schema: type[DeepAgentState],
) -> BaseTool:
    """Create a task delegation tool that enables context isolation through sub-agents.

    This function implements the core pattern for spawning specialized sub-agents with
    isolated contexts, preventing context clash and confusion in complex multi-step tasks.

    Args:
        tools: List of available tools that can be assigned to sub-agents
        subagents: List of specialized sub-agent configurations
        model: The language model to use for all agents
        state_schema: The state schema (typically DeepAgentState)

    Returns:
        A 'task' tool that can delegate work to specialized sub-agents
    """
    # Create an agent registry
    agents = {}

    # Build tool name mapping for selective tool assignment
    tools_by_name = {}
    for tool_ in tools:
        if not isinstance(tool_, BaseTool):
            tool_ = tool(tool_)
        tools_by_name[tool_.name] = tool_

    # Create specialized sub-agents based on configurations
    for _agent in subagents:
        if "tools" in _agent:
            # use specific tools if specified
            _tools = [tools_by_name[t] for t in _agent["tools"]]
        else:
            #  Default to all available tools
            _tools = tools

        agents[_agent["name"]] = create_agent(
            model,
            system_prompt=_agent["prompt"],
            tools=_tools,
            state_schema=state_schema,
        )

    # Generate description of available sub-agents for the tool description
    other_agents_string = [f"- {_agent['name']}: {_agent['description']}" for _agent in subagents]

    @tool(description=TASK_DESCRIPTION_PREFIX.format(other_agents=other_agents_string))
    def task(
        description: str,
        subagent_type: str,
        state: Annotated[DeepAgentState, InjectedState],
        tool_call_id: Annotated[str, InjectedToolCallId],
    ) -> Command | str:
        """Delegate a task to a specialized sub-agent with isolated context.

        This creates a fresh context for the sub-agent containing only the task description,
        preventing context pollution from the parent agent's conversation history.
        """
        # Validate requested agent type exists
        if subagent_type not in agents:
            return f"Error: invoked agent of type {subagent_type}, the only allowed types are {[f'`{k}`' for k in agents]}"

        # Get the requested subagent
        sub_agent = agents[subagent_type]

        # Build an isolated copy of the state for the sub-agent.
        # CRITICAL: we must NOT mutate the shared injected state dict —
        # concurrent task tool calls share the same reference.
        isolated_state: dict[str, object] = {
            "messages": [HumanMessage(content=description)],
            "files": dict(state.get("files", {})),
        }

        # Execute the sub-agent in isolation
        result = sub_agent.invoke(isolated_state)

        # Return results to parent agent via Command state update.
        # Sub-agent's last message content may be str or a list of structured
        # content blocks. The parent's ToolMessage validator chokes on raw
        # dict blocks lacking a "type" field, so flatten everything to text.
        raw_content = cast(object, result["messages"][-1].content)
        if isinstance(raw_content, str):
            last_content: str = raw_content
        elif isinstance(raw_content, list):
            parts: list[str] = []
            for block in cast(list[object], raw_content):
                if isinstance(block, dict):
                    parts.append(str(cast(dict[str, object], block).get("text", "")))
                else:
                    parts.append(str(block))
            last_content = "\n".join(parts)
        else:
            last_content = str(raw_content)

        return Command(
            update={
                "files": result.get("files", {}),  # Merge any file changes
                "messages": [
                    # Sub-agent result becomes a ToolMessage in parent context
                    # Hide all other internal messages for parent agent
                    ToolMessage(last_content, tool_call_id=tool_call_id)
                ],
            }
        )

    return task
