# Status — langgraph-deep-research-agent

> Autonomous daily research agent using LangGraph subagent delegation to discover, filter, and deliver research updates as a structured markdown digest.

## Overview

| Task                                   | Status    | Priority | Owner     | Updated    |
| -------------------------------------- | --------- | -------- | --------- | ---------- |
| Digest quality fixes                   | ⚪ Done   | P0       | @pytholic | 2026-05-02 |
| M0 + M1: Baseline & Prompts            | ⚪ Done   | P0       | @pytholic | 2026-05-03 |
| Fix global `searched_queries` tracking | ⚪ Done   | P1       | @pytholic | 2026-05-03 |
| Hybrid model + provider UI             | ⚪ Done   | P1       | @pytholic | 2026-05-03 |
| Parallel sub-agent execution           | ⚪ Done   | P0       | @pytholic | 2026-05-03 |
| Specialized sub-agents + pipeline      | 🔵 Parked | P1       | @pytholic | 2026-05-03 |

### Status Labels

- 🟢 **Active** — Currently being worked on
- 🟡 **Review** — Work done, needs human review
- 🔴 **Blocked** — Waiting on external dependency or decision
- ⚪ **Done** — Completed and verified

### Priority Levels

- **P0** — Must be done now, blocks other work
- **P1** — Important, do next
- **P2** — Nice to have, do when bandwidth allows

## Parked Ideas

| Idea                                              | Origin             | Date       | Notes                                                                           |
| ------------------------------------------------- | ------------------ | ---------- | ------------------------------------------------------------------------------- |
| Specialized sub-agents + post-processing pipeline | Notion Task 1      | 2026-05-03 | Now unblocked by parallel execution; can implement when ready                   |
| `query_log_reducer` for `searched_queries`        | Session discussion | 2026-05-03 | Needed when concurrency > 1; currently `NotRequired[list[str]]` with no reducer |

## Blocked Items

_Nothing blocked._

## Notes

- 2026-05-03: Fixed parallel sub-agent execution — made `task` tool async with `ainvoke`, removed Ollama summarization bottleneck, removed arxiv threading lock, bumped default `max_concurrent_research_units` to 3
- 2026-05-03: Fixed streaming UI bug — sub-agent labels used `len(seen)` instead of stable per-namespace index; all events after 3 agents appeared as "#3"
- 2026-05-03: Switched to sequential filenames (`web_001.md`, `arxiv_001.md`) — eliminates model hallucinating random UUID-suffixed names
- 2026-05-03: Added parallel lane UI — trace panel now renders concurrent sub-agent steps side-by-side instead of linear column
- 2026-05-03: Removed emojis from all prompts and tool responses
- 2026-05-02: Fixed race condition in `task.py` — concurrent sub-agents mutated shared injected state
- 2026-05-02: Removed `with_structured_output(Summary)` from `web_tool.py` — eliminated dict-without-type leak
- 2026-05-02: Switched LLM backend from OpenAI (`gpt-4o-mini`) to Ollama (`llama3.1:8b`) via `ChatOllama`
