# Architectural Decisions

Append new decisions at the top. Each entry records context, the choice made,
the reasoning, and what was explicitly rejected.

## 2026-05-02: Serialize arxiv API access with a module lock

- **Context:** Long pauses and HTTP 429 when using `arxiv_search`, especially when the model dispatches `arxiv_search` and `tavily_search` in parallel. The `arxiv` package uses one shared `Client` with `delay_seconds=3` between requests (API terms). Concurrent threads could race past that logic.
- **Choice:** A module-level `threading.Lock` wraps `list(client.results(...))`. Optional `ARXIV_DELAY_SECONDS` env var (minimum 3.0). Catch `arxiv.HTTPError` in the tool and return a `ToolMessage` instead of failing the run.
- **Why:** LangGraph's tool node runs multiple tools concurrently; serialization guarantees at-most-one in-flight arxiv HTTP request per process and preserves the client's rate-limit sleep behavior.
- **Rejected:** Lowering `delay_seconds` below 3 by default — violates arXiv API terms of use.

<!-- Template:
## YYYY-MM-DD: Decision Title
- **Context:** What situation or constraint prompted this decision?
- **Choice:** What did we decide?
- **Why:** Why this option over others?
- **Rejected:** What alternatives were considered and why not?
-->

## 2026-05-02: Keep one generalist research-agent, add specialists only for genuinely different source types

- **Context:** The orchestrator was spawning 2 identical `research-agent` instances split by tool ("search on arXiv" + "search on Tavily"), causing duplicate results and incoherent output. We considered whether to split arxiv and tavily into separate specialist sub-agents now.
- **Choice:** Option A — keep a single `research-agent` with both `arxiv_search` and `tavily_search` tools. The orchestrator spawns multiple instances only for distinct *topics/facets*, never by source. New specialist types (e.g., `social-agent`) are added only when the source requires genuinely different tools and reasoning.
- **Why:** A single agent's iteration loop can cross-reference across sources (find a paper on arxiv, then search tavily for blog posts explaining it). Splitting by source breaks that loop and creates coordination overhead for no gain. The M3 Planner Node will properly decompose queries into non-overlapping sub-topics — that's the right layer to solve overlap, not the agent type registry. Social media is genuinely different (different APIs, content formats, relevance signals) and warrants its own specialist when the time comes (M5+).
- **Rejected:** Option B (split into `arxiv-agent` + `web-agent` now) — premature complexity, breaks cross-source reasoning within the research loop, requires maintaining separate prompts/tool lists for sources that have no meaningful behavioral difference.
