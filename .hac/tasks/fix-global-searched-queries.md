# Task: Fix Global State Tracking for `searched_queries`

| Field        | Value         |
| ------------ | ------------- |
| **Status**   | 🟢 Active     |
| **Priority** | P1            |
| **Owner**    | @pytholic     |
| **Created**  | 2026-05-03    |
| **Updated**  | 2026-05-03    |
| **Branch**   | feature/m0-m1 |
| **Scope**    | ~1 session    |

## Context

Sub-agents start with an empty `searched_queries` list and their search history is discarded when they finish. This means:

- Parallel agents can't avoid duplicate searches
- The parent orchestrator has no visibility into what was searched
- The current tool-level tracking (Option 3, injected into tool responses) only works within a single sub-agent's run

Currently in place:

- ✅ `searched_queries: NotRequired[list[str]]` in `state.py`
- ✅ Passed down into isolated state in `task.py:106`
- ✅ Tool-level append in `arxiv_tool.py` + `web_tool.py` (via `append_searched_query`)
- ❌ Not propagated back up in `task.py` Command return
- ❌ No reducer — parallel agents will clobber each other's updates

## Plan

- [ ] **Step 1**: Add `list_reducer` to `state.py` and annotate `searched_queries`
  ```python
  def list_reducer(left: list[str], right: list[str]) -> list[str]:
      seen = set(left or [])
      return (left or []) + [q for q in (right or []) if q not in seen]

  searched_queries: Annotated[NotRequired[list[str]], list_reducer]
  ```
- [ ] **Step 2**: Propagate back up in `task.py` Command return
  ```python
  "searched_queries": result.get("searched_queries", []),
  ```
- [ ] **Step 3**: Verify with a run — check that queries from sub-agent appear in parent state

## Notes / Findings

- The `list_reducer` deduplicates on merge (preserves order, skips already-seen queries) so repeated merges don't balloon the list.
- With `max_concurrent_research_units=1` this is a correctness fix, not a performance fix — but it unblocks Task 1 (specialized sub-agents) which needs reliable cross-agent dedup.

## Session Log

- **2026-05-03:** Task created from Notion note (2026.03.05). Pieces mostly in place; reducer + propagation-back are the two missing steps.
