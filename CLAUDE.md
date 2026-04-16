# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

An autonomous daily research agent that discovers, filters, and delivers research updates using LangGraph subagent delegation. The orchestrator agent receives configured topics, delegates search tasks to specialized subagents (Arxiv, Web, Social), scores/ranks results, and produces a daily markdown digest — optionally feeding high-signal content into an Obsidian vault knowledge base.

## Setup & Commands

```bash
uv sync                   # Install dependencies
cp .env.example .env      # Configure OPENAI_API_KEY and TAVILY_API_KEY
```

**Linting & formatting:**

```bash
uv run ruff check --fix src/   # Lint with autofix
uv run ruff format src/        # Format
uv run pyright src/            # Type check
```

**Run pre-commit hooks manually:**

```bash
uv run pre-commit run --all-files
```

**Run the demo:**

```bash
uv run jupyter notebook examples/research_demo.ipynb
```

**Direct usage:**

```python
from deep_research_agent.agent import create_deep_research_agent

agent = create_deep_research_agent()
result = agent.invoke({
    "messages": [{"role": "user", "content": "Find today's most relevant AI research papers."}]
})
```

## Environment Variables

Required in `.env`:

- `OPENAI_API_KEY` — LLM provider
- `TAVILY_API_KEY` — web search

Optional:

- `LANGSMITH_TRACING`, `LANGSMITH_API_KEY`, `LANGSMITH_PROJECT` — tracing

## Architecture

### Agentic pattern

This repo implements a **multi-source Coordinator pattern**: the orchestrator agent receives configured research topics and delegates search tasks to specialized subagents (Arxiv, Web, Social). Each subagent is an isolated subgraph with its own tools, state, and error handling — a failure in one source doesn't break the pipeline. Results flow through a Filter & Ranker (scoring, deduplication) and Formatter before producing a daily digest.

### Current implementation (inherited from coordinator-agent template)

The codebase currently uses the Coordinator pattern from `langgraph-coordinator-agent` as a starting point:

**1. Sub-agent context isolation** (`src/deep_research_agent/task.py`): When the parent delegates a research task, `_create_task_tool` spawns a sub-agent with a clean context window containing only the task description — no parent message history.

**2. Virtual file system + context offloading** (`src/deep_research_agent/state.py`): `DeepAgentState` carries a `files: dict[str, str]` with a `file_reducer` that merges updates additively. Search tools save full content to files and return only short summaries.

### Target architecture (to be built)

```
Orchestrator Agent
  ├── Arxiv Subagent (arxiv API search)
  ├── Web Subagent (Tavily web search)
  ├── Social Subagent (Twitter/X, LinkedIn feeds)
  │
  ▼
Filter & Ranker (score, deduplicate)
  │
  ▼
Formatter (daily digest markdown)
  │
  ├── stdout / file output
  └── Wiki Bridge → vault/raw/ (optional)
```

### Module responsibilities

| Module                 | Purpose                                                                                                                     |
| ---------------------- | --------------------------------------------------------------------------------------------------------------------------- |
| `agent.py`             | Public factory `create_deep_research_agent()` — assembles tools, prompts, sub-agent configs into a compiled LangGraph graph |
| `state.py`             | `DeepAgentState` (extends `AgentState` with `todos` and `files`), `file_reducer`, `Todo` TypedDict                          |
| `task.py`              | `_create_task_tool()` — creates the `task` delegation tool that implements context isolation                                |
| `tools/research.py`    | `tavily_search` (search + offload), `think_tool` (reflection), `summarize_webpage_content`                                  |
| `tools/files.py`       | `ls`, `read_file`, `write_file` — virtual filesystem tools over `state["files"]`                                            |
| `tools/todos.py`       | `write_todos`, `read_todos` — TODO tracking tools over `state["todos"]`                                                     |
| `prompts/system.py`    | All system prompt constants and tool descriptions for the parent agent                                                      |
| `prompts/summarize.py` | Prompts for the research sub-agent and web content summarization                                                            |

### Key design constraints

- **Tool returns `Command`**: Tools that modify state return `langgraph.types.Command` objects to update state atomically.
- **`file_reducer` is additive**: Parallel sub-agents each write distinct files; the reducer merges dicts so no writes are lost.
- **`langgraph.json`**: Points to `create_deep_research_agent` as the graph entrypoint for LangGraph Server deployment.

## Code Style

- Ruff with Google-style docstrings (`pydocstyle` convention)
- Pyright in strict mode for `src/`, basic mode for `tests/`
- `ANN` rules enforced (type annotations required) except in tests
- `T20` rules enforced (no `print` statements — use `rich` or return values)
- Line length: 100 characters
- Python 3.13+
