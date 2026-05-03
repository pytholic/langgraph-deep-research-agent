"""State management for deep agents with TODO tracking and virtual file systems.

This module defines the extended agent state structure that supports:
- Task planning and progress tracking through TODO lists
- Context offloading through a virtual file system stored in state
- Efficient state merging with reducer functions

Created by @pytholic on 2026.04.06
"""

from typing import Annotated, Literal, NotRequired

from langchain.agents.middleware import AgentState
from typing_extensions import TypedDict


class Todo(TypedDict):
    """A todo item with a title, description, and status.

    Attributes:
        title: The title of the todo item
        description: The description of the todo item
        status: The status of the todo item
    """

    title: str
    description: str
    status: Literal["pending", "in_progress", "completed"]


def file_reducer(left: dict[str, str], right: dict[str, str]) -> dict[str, str]:
    """Merge two file dictionaries, with right taking precedence.

    Used as a reducer function for the files field in agent state,
    allowing incremental updates to the virtual file system.

    It merges dict updates additively so parallel sub-agents can write distinct files without
    clobbering each other.

    Args:
        left: The left file dictionary
        right: The right file dictionary

    Returns:
        A merged file dictionary with right values overriding left values
    """
    if left is None:
        return right
    if right is None:
        return left
    return {**left, **right}


def list_reducer(left: list[str], right: list[str]) -> list[str]:
    """Merge two lists, with right taking precedence.

    Used as a reducer function for the searched_queries field in agent state,
    allowing incremental updates to the searched_queries list.

    It merges lists additively so parallel sub-agents can write distinct queries without
    clobbering each other.

    Args:
        left: The left list
        right: The right list

    Returns:
        A merged list with right values overriding left values
    """
    seen = set(left or [])
    return (left or []) + [query for query in (right or []) if query not in seen]


class DeepAgentState(AgentState):
    """Extended agent state that includes task tracking and virtual file system.

    Inherits from LangGraph's AgentState and adds:
    - todos: List of Todo items for task planning and progress tracking
    - files: Virtual file system stored as dict mapping filenames to content
    - searched_queries: List of queries that have been searched
    - file_prefix: Short prefix for filenames, set per sub-agent to avoid collisions
    """

    todos: NotRequired[list[Todo]]
    files: Annotated[NotRequired[dict[str, str]], file_reducer]
    searched_queries: Annotated[NotRequired[list[str]], list_reducer]
    file_prefix: NotRequired[str]
