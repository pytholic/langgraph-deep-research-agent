# Task: Digest Quality Fixes

| Field        | Value      |
| ------------ | ---------- |
| **Status**   | ⚪ Done    |
| **Priority** | P0         |
| **Owner**    | @pytholic  |
| **Created**  | 2026-05-02 |
| **Updated**  | 2026-05-02 |
| **Scope**    | ~1 session |

## Context

When multiple sub-agents run in parallel, the final digest output has three problems:

1. **Incoherent/concatenated prose** — Sub-agent summaries are dumped verbatim via ToolMessages, then the orchestrator paraphrases them again, producing redundant blocks mashed together.
2. **Duplicate sources** — Both sub-agents search with similar queries, find the same papers/articles, and `extract_sources` doesn't deduplicate by URL.
3. **"Stuck then more" streaming** — The digest stream emits tokens for every non-tool-calling model turn, not just the final answer. Intermediate turns (e.g., after reading todos) leak into the digest.

Root cause of (1) and (2): the orchestrator prompt encourages splitting by source tool ("search on arXiv" / "search on Tavily") instead of by topic. Per the Option A decision, a single research-agent already has both tools.

## Plan

- [x] Create working memory
- [x] Record Option A decision
- [x] **Fix 1: Update SUBAGENT_USAGE_INSTRUCTIONS** — Added `<Critical Rule>` block: never split by source, BAD/GOOD examples, describe topic not tool.
- [x] **Fix 2: URL dedup in `sources.py`** — `extract_sources` now tracks `seen_urls` set and skips duplicates.
- [x] **Fix 3: Digest stream filter in `streaming.py`** — Added `root_tools_executed` flag; digest tokens only emitted after root tools node has fired at least once, and only for root graph (not subgraph) model turns.
- [x] **Verify** — Run confirmed: single sub-agent dispatched, used both arxiv+tavily in its loop, no intermediate turns in digest. (2nd arxiv call hit 429 rate limit from repeated testing, not a code bug.)

## Notes / Findings

- The orchestrator dispatched: `"Search ... on arXiv"` + `"Search ... on Tavily"` — splitting by source, not topic.
- Both sub-agents independently called `arxiv_search` with similar queries → same HERMES++ paper appeared 3x in sources.
- The digest stream filter at `streaming.py:191-196` checks `not msg.tool_call_chunks` but doesn't distinguish intermediate model turns from the final answer.

## Open Questions / Risks

- The streaming fix needs careful handling: we can't know for certain a model turn is "final" until we see no tool calls. The heuristic is: if the root model node produces content without tool_call_chunks, and it's after at least one tool execution round, it's likely the final answer. Edge case: the model might do a planning turn with no tool calls before dispatching — but in practice `create_agent` always produces tool calls or a final answer, not bare planning text.

## Session Log

- **2026-05-02:** All three fixes implemented and verified. Single sub-agent dispatched, used both arxiv+tavily, no intermediate turns in digest. Task complete.
