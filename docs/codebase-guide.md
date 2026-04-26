# Codebase Navigation Guide

A structured reading order for anyone approaching this repository for the first time.

---

## Prerequisites

Before reading any code, spend 5 minutes here:


| File                                                    | What to absorb                                                                         |
| ------------------------------------------------------- | -------------------------------------------------------------------------------------- |
| [README.md](../README.md)                               | Project purpose, setup steps, environment variables                                    |
| [langgraph.json](../langgraph.json)                     | Names the graph entrypoint: `agent.py:create_deep_research_agent`                      |
| [.env.example](../.env.example)                         | External services required: `OPENAI_API_KEY`, `TAVILY_API_KEY`                         |
| [pyproject.toml](../pyproject.toml) (dependencies only) | Runtime stack: `langgraph`, `langchain-openai`, `langchain-tavily`, `arxiv`, `fastapi` |


---

## Reading Order

### 1. Data model — `state.py`, `sources.py`

Read these before anything else. Every other module references them.

**[src/deep_research_agent/state.py](../src/deep_research_agent/state.py)**
Defines `DeepAgentState` — the graph's shared memory bag:

- `messages` — the agent's conversation thread
- `todos` — a task-tracking list the orchestrator manages
- `files` — a virtual filesystem (`dict[str, str]`) with a custom `file_reducer` that merges dict updates additively so parallel sub-agents can write distinct files without clobbering each other

**[src/deep_research_agent/sources.py](../src/deep_research_agent/sources.py)**
Defines the `ResearchSource` enum: `ARXIV`, `WEB`, `SOCIAL`. Read in 2 minutes; establishes the vocabulary used everywhere else.

---

### 2. Core graph — `agent.py`, `task.py`

**[src/deep_research_agent/agent.py](../src/deep_research_agent/agent.py)**
The public factory `create_deep_research_agent()` — assembles tools, prompts, and sub-agent configs into a compiled LangGraph `StateGraph`. This is the single entrypoint for all callers including `langgraph.json`, the FastAPI server, and the example scripts.

**[src/deep_research_agent/task.py](../src/deep_research_agent/task.py)**
The most architecturally important file. `_create_task_tool()` builds the delegation mechanism: when the orchestrator calls `task(description, subagent_type)`, a fresh sub-agent is spawned with a **clean context window** containing only the task description — no parent message history leaks through. The sub-agent's final answer comes back as a `ToolMessage`; all intermediate tool calls are hidden from the orchestrator.

> **Key insight:** context isolation here is intentional — it keeps sub-agents focused and prevents the orchestrator's message thread from growing unboundedly.

---

### 3. Prompts — `prompts/system.py`, `prompts/summarize.py`

**[src/deep_research_agent/prompts/system.py](../src/deep_research_agent/prompts/system.py)**
The orchestrator's system prompt and all tool descriptions. Reading this tells you the orchestrator's reasoning loop: plan with `write_todos`, delegate with `task`, read results from files, then synthesize a digest.

**[src/deep_research_agent/prompts/summarize.py](../src/deep_research_agent/prompts/summarize.py)**
Two prompts: one for research sub-agents (what they should do with search results) and one for summarizing raw webpage content into concise findings.

---

### 4. Tools — `tools/`

Read in this order (largest → smallest, most logic first):


| File                                                                  | What it does                                                                                                                                               |
| --------------------------------------------------------------------- | ---------------------------------------------------------------------------------------------------------------------------------------------------------- |
| [tools/web_tool.py](../src/deep_research_agent/tools/web_tool.py)     | Tavily web search. Note how full results are **offloaded to `state["files"]`** and only a short summary is returned — this keeps the message thread small. |
| [tools/arxiv_tool.py](../src/deep_research_agent/tools/arxiv_tool.py) | ArXiv paper search. Same offload pattern as `web_tool`.                                                                                                    |
| [tools/research.py](../src/deep_research_agent/tools/research.py)     | Orchestrator-level tools: `tavily_search`, `think_tool` (structured reflection), `summarize_webpage_content`.                                              |
| [tools/files.py](../src/deep_research_agent/tools/files.py)           | Virtual filesystem exposed as LangGraph tools: `ls`, `read_file`, `write_file`. All operate on `state["files"]`, not disk.                                 |
| [tools/todos.py](../src/deep_research_agent/tools/todos.py)           | `write_todos` / `read_todos` — task tracking over `state["todos"]`.                                                                                        |


> **Pattern to notice:** tools that modify state return `langgraph.types.Command` objects rather than plain values. This updates state atomically and is how tools communicate results back to the graph.

---

### 5. Infrastructure — `logging.py`, `ui/`

**[src/deep_research_agent/logging.py](../src/deep_research_agent/logging.py)**
`rich`-based structured logging setup. Quick read — establishes how log output is formatted across the project.

**[src/deep_research_agent/ui/server.py](../src/deep_research_agent/ui/server.py)**
FastAPI server that wraps the graph. Exposes `POST /api/run` and streams results back to the browser via SSE. See [docs/architecture.md](architecture.md#6-streaming-architecture--why-a-custom-fastapi-server) for why a custom server exists instead of using LangGraph Server directly.

**[src/deep_research_agent/ui/static/index.html](../src/deep_research_agent/ui/static/index.html)**
Single-page browser UI — 618 lines of HTML/CSS/JS. Skim last; not needed to understand the agent logic.

---

### 6. Examples and tests

Concrete usage that confirms your mental model.


| File                                                              | What to look for                                                                             |
| ----------------------------------------------------------------- | -------------------------------------------------------------------------------------------- |
| [examples/run.py](../examples/run.py)                             | Minimal end-to-end invocation — the clearest usage example                                   |
| [examples/utils.py](../examples/utils.py)                         | Rich-based CLI renderer for streaming events; shows how `stream_events()` output is consumed |
| [tests/conftest.py](../tests/conftest.py)                         | Fixtures — shows which external dependencies are mocked in tests                             |
| [tests/unit/test_state.py](../tests/unit/test_state.py)           | Tests for `file_reducer` — validates the additive merge semantics described above            |
| [tests/unit/test_arxiv_tool.py](../tests/unit/test_arxiv_tool.py) | Tool behavior under normal and error conditions                                              |
| [tests/unit/test_web_tool.py](../tests/unit/test_web_tool.py)     | Same for web search                                                                          |


---

## Mental model

```
User query
    │
    ▼
create_deep_research_agent()        ← agent.py
    │  system prompt: prompts/system.py
    │  state: DeepAgentState (messages + files + todos)
    │
    ├─ task tool (task.py) ──────────► isolated sub-agent
    │                                       ├── arxiv_tool
    │                                       └── web_tool
    │                                   writes results → state["files"]
    │
    ├─ research tools (research.py): tavily_search, think_tool
    ├─ file tools    (files.py):     ls, read_file, write_file
    └─ todo tools    (todos.py):     write_todos, read_todos
    │
    ▼
Daily digest (markdown)
    │
    └─ streamed via FastAPI SSE (ui/server.py)
```

## Two non-obvious design decisions

These are easy to miss but explain several otherwise puzzling implementation choices:

1. **Context isolation in `task.py`** — Sub-agents receive only their task description, not the full parent conversation. This prevents context bloat and keeps each sub-agent's reasoning focused. The cost is that sub-agents cannot reference prior turns; the benefit is predictable, bounded token usage per delegation.
2. `**file_reducer` is additive** — Multiple sub-agents running in parallel each write to distinct filenames. The reducer merges their `files` dicts with `{**existing, **new}` so no writes are lost, even under concurrent execution. If two agents wrote to the *same* filename, the last write would win — by convention, tools use topic-scoped filenames (e.g., `findings_llm_agents.md`) to avoid collisions.
