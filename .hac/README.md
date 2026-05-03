# .hac — Human-Agent Context

This directory is the shared context layer between humans and AI agents
working on this project. **HAC** stands for **Human-Agent Context**.

It exists so that when anyone — human or agent — picks up this project
after a break, they can understand the current state in under 30 seconds
without reading code, scrolling through Slack, or asking "where were we?"

## How It Works

| File              | Purpose                                   | Who updates it                  |
| ----------------- | ----------------------------------------- | ------------------------------- |
| `status.md`       | Dashboard — what's active, blocked, done  | Agent (after each work block)   |
| `decisions.md`    | Why we chose X over Y                     | Agent (when decisions are made) |
| `tasks/<name>.md` | Scratchpad per task — plan, findings, log | Agent (during execution)        |

## Master Index

A single-glance lookup across everything tracked in this project.

### Tasks

| Task                                   | Status  | Priority | Owner     | File                                                                         | Updated    |
| -------------------------------------- | ------- | -------- | --------- | ---------------------------------------------------------------------------- | ---------- |
| Digest quality fixes                   | ⚪ Done | P0       | @pytholic | [tasks/digest-quality-fixes.md](tasks/digest-quality-fixes.md)               | 2026-05-02 |
| M0 + M1: Baseline & Prompts            | ⚪ Done | P0       | @pytholic | [tasks/m0-m1-implementation.md](tasks/m0-m1-implementation.md)               | 2026-05-03 |
| Fix global `searched_queries` tracking | ⚪ Done | P1       | @pytholic | [tasks/fix-global-searched-queries.md](tasks/fix-global-searched-queries.md) | 2026-05-03 |
| Hybrid model + provider UI             | ⚪ Done | P1       | @pytholic | —                                                                            | 2026-05-03 |

### Decisions

| Date       | Decision                           | Choice                                                        | Impact                                                     |
| ---------- | ---------------------------------- | ------------------------------------------------------------- | ---------------------------------------------------------- |
| 2026-05-02 | Serialize arxiv API access         | Module-level `threading.Lock` wrapping `client.results()`     | Prevents HTTP 429 from concurrent arxiv calls              |
| 2026-05-02 | Keep one generalist research-agent | Single agent with both `arxiv_search` + `tavily_search` tools | Avoids duplicate results; cross-source reasoning preserved |

## Rules

- This directory is tracked in git. It is project knowledge.
- `decisions.md` is append-only. Never edit or remove past entries.
- Task files are created on-demand, not in advance.
- Don't use `.hac/` for trivial one-off fixes.
