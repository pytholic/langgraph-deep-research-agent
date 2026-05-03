# Decisions — langgraph-deep-research-agent

## Quick Reference

| Date       | Decision                                            | Choice                                                  | Impact                                                                      |
| ---------- | --------------------------------------------------- | ------------------------------------------------------- | --------------------------------------------------------------------------- |
| 2026-05-03 | Remove Ollama summarization from search hot path    | Use Tavily's native snippet; full content in files      | Unblocks parallel execution; Ollama was serializing all agents              |
| 2026-05-03 | Remove arxiv threading lock                         | Rely on built-in `delay_seconds` rate limiting          | Unblocks parallel arxiv calls across sub-agents                             |
| 2026-05-03 | Sequential filenames (`web_001.md`, `arxiv_001.md`) | Replace UUID-suffixed names                             | Eliminates model hallucination of filenames                                 |
| 2026-05-03 | Async task tool with `ainvoke`                      | `async def task` + `sub_agent.ainvoke()`                | True concurrent sub-agent execution via asyncio                             |
| 2026-05-02 | Serialize arxiv API access                          | Module-level `threading.Lock`                           | Prevents HTTP 429 from concurrent arxiv calls — **SUPERSEDED 2026-05-03**   |
| 2026-05-02 | Keep one generalist research-agent                  | Single agent with both tools                            | Avoids duplicate results; cross-source reasoning preserved                  |
| 2026-05-02 | No upstream dedup across sub-agents                 | Known gap, dedup only by URL post-hoc                   | Sub-agent #2 can repeat searches done by #1                                 |
| 2026-05-03 | Revise: split into specialized sub-agents           | Parked — implement after global state tracking is fixed | Revisits single-agent decision; detailed Architecture Decision Record below |
| 2026-05-03 | Hybrid model: Ollama orchestrator + API researcher  | Ollama for synthesis, `gpt-4.1-nano` for sub-agents     | Resolves Ollama memory bloat; revives M0 model split params                 |

______________________________________________________________________

<!-- Append new decisions below this line, newest first.

Format:
## YYYY-MM-DD: Decision Title
- **Context:** What situation or constraint prompted this decision?
- **Choice:** What did we decide?
- **Why:** Why this option over others?
- **Rejected:** What alternatives were considered and why not?
-->

## 2026-05-03: Remove Ollama summarization from search hot path

- **Context:** When 3+ sub-agents run in parallel, each `tavily_search` call invokes `ChatOllama.invoke()` for summarization. Ollama processes requests sequentially, serializing all agents at ~20s each — defeating parallelism entirely.
- **Choice:** Default `summarize=False` in `TavilySearchTool.process()`. Use Tavily's native `content` snippet as the summary. Full raw content still saved to files for later reading.
- **Why:** The agent reads full files during synthesis anyway. The inline summary only needs to tell the agent what a file contains — Tavily's snippet is sufficient for this. LLM summarization remains available via `summarize=True` for single-agent mode.
- **Rejected:** Making Ollama async — doesn't help because Ollama server itself is sequential. Using OpenAI for summarization — adds cost for minimal benefit given agent reads full files later.

## 2026-05-03: Remove arxiv threading lock, use sequential filenames

- **Context:** The `threading.Lock` on arxiv API was serializing parallel sub-agents. The UUID-suffixed filenames were causing model hallucination (agent invents names like `ai_safety_comparison.md` instead of `Publications - Google DeepMind_JKe69UHi.md`).
- **Choice:** (1) Remove `_arxiv_api_lock` — the arxiv client's `delay_seconds=3.0` already rate-limits. (2) Replace UUID filenames with sequential `web_001.md`, `arxiv_001.md` pattern.
- **Why:** Simple numeric filenames are trivial for any model to reproduce from memory. The lock was overly conservative — the arxiv client handles its own pacing.
- **Rejected:** Keeping lock with shorter timeout — still blocks parallelism unnecessarily.

## 2026-05-03: Make task tool async for true parallel execution

- **Context:** The `task` tool was `def task(...)` with `sub_agent.invoke()` (synchronous). When LangGraph dispatches multiple tool calls, sync tools run in a thread pool — but the observed behavior showed 11-second gaps between sub-agent spawns.
- **Choice:** Convert to `async def task(...)` with `await sub_agent.ainvoke()`. Bump `max_concurrent_research_units` default from 1 to 3.
- **Why:** Async tools run directly on the event loop via `asyncio.gather` in LangGraph's ToolNode. This ensures true concurrent execution without thread pool overhead.
- **Rejected:** Keeping sync + increasing thread pool size — less predictable, event loop blocked during execution.

## 2026-05-02: Serialize arxiv API access with a module lock (SUPERSEDED)

- **Context:** Long pauses and HTTP 429 when using `arxiv_search`, especially when the model dispatches `arxiv_search` and `tavily_search` in parallel. The `arxiv` package uses one shared `Client` with `delay_seconds=3` between requests (API terms). Concurrent threads could race past that logic.
- **Choice:** A module-level `threading.Lock` wraps `list(client.results(...))`. Optional `ARXIV_DELAY_SECONDS` env var (minimum 3.0). Catch `arxiv.HTTPError` in the tool and return a `ToolMessage` instead of failing the run.
- **Why:** LangGraph's tool node runs multiple tools concurrently; serialization guarantees at-most-one in-flight arxiv HTTP request per process and preserves the client's rate-limit sleep behavior.
- **Rejected:** Lowering `delay_seconds` below 3 by default — violates arXiv API terms of use.

## 2026-05-03: Hybrid model — Ollama orchestrator + API researcher sub-agents

- **Context:** Running two different Ollama models (orchestrator + researcher) simultaneously causes memory bloat — both load into VRAM. The M0 model split params (`orchestrator_model` / `researcher_model`) were shelved because we reverted to a single Ollama model.
- **Choice:** Use Ollama for the orchestrator (synthesis, planning — benefits from a larger, capable local model) and a cheap API model like `gpt-4.1-nano` for researcher sub-agents (repetitive tool calls and search — doesn't need a large model). This revives the M0 split param design in `create_deep_research_agent`.
- **Why:** Orchestrator runs once per session; memory cost is acceptable. Researcher sub-agents run many tool-call loops; a fast, cheap API model is better suited and avoids doubling local VRAM usage. Cost is minimal — nano-class models are a fraction of a cent per run.
- **Rejected:** Single local model for both — works today but blocks parallel sub-agents due to VRAM. Two local models simultaneously — causes OOM on consumer hardware.

## 2026-05-03: Revise single-agent decision — specialize sub-agents by source type

- **Context:** The 2026-05-02 decision kept one generalist research-agent with both `arxiv_search` and `tavily_search` to avoid duplicate results and preserve cross-source reasoning. A new analysis (Notion, 2026.03.05) argues specialized agents are better.
- **Choice:** Deferred — implement specialized `arxiv_sub_agent` and `web_sub_agent` after global `searched_queries` state tracking is fixed and concurrency is bumped above 1.
- **Why:** Specialized agents have focused prompts (academic extraction vs. web synthesis), no tool-paralysis (each agent has exactly one search tool), and the orchestrator handles overlap by spawning both in parallel — results are merged and deduplicated by the post-processing pipeline. The original concern about duplicates is addressed at the pipeline layer, not the agent layer.
- **Rejected:** Keeping single generalist agent permanently — blocks parallelism gains and forces a bloated prompt covering two distinct reasoning modes.

## 2026-05-02: No upstream dedup across sub-agents — known gap

- **Context:** When the orchestrator spawns multiple research sub-agents, each gets a fresh isolated context (only its task description + shared files). Sub-agent #2 has no visibility into what #1 already searched, so it can issue duplicate queries and find the same sources.
- **Choice:** Accept this as a known gap for now. Deduplication happens post-hoc in `sources.py` by URL only.
- **Why:** The current prompt mitigates this partly — the orchestrator is instructed to assign distinct topics per sub-agent. With `max_concurrent_research_units=1`, there's only ever one sub-agent, so no overlap is possible.
- **Rejected:** Injecting a "already searched" summary into each sub-agent's task description — would require the orchestrator to track and summarise prior searches, adding prompt complexity. Deferred to M3 Planner Node, which is the right layer to assign non-overlapping sub-topics.

## 2026-05-02: Keep one generalist research-agent, add specialists only for genuinely different source types

- **Context:** The orchestrator was spawning 2 identical `research-agent` instances split by tool ("search on arXiv" + "search on Tavily"), causing duplicate results and incoherent output. We considered whether to split arxiv and tavily into separate specialist sub-agents now.
- **Choice:** Option A — keep a single `research-agent` with both `arxiv_search` and `tavily_search` tools. The orchestrator spawns multiple instances only for distinct *topics/facets*, never by source. New specialist types (e.g., `social-agent`) are added only when the source requires genuinely different tools and reasoning.
- **Why:** A single agent's iteration loop can cross-reference across sources (find a paper on arxiv, then search tavily for blog posts explaining it). Splitting by source breaks that loop and creates coordination overhead for no gain. The M3 Planner Node will properly decompose queries into non-overlapping sub-topics — that's the right layer to solve overlap, not the agent type registry. Social media is genuinely different (different APIs, content formats, relevance signals) and warrants its own specialist when the time comes (M5+).
- **Rejected:** Option B (split into `arxiv-agent` + `web-agent` now) — premature complexity, breaks cross-source reasoning within the research loop, requires maintaining separate prompts/tool lists for sources that have no meaningful behavioral difference.
