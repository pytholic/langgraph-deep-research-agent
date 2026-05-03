# Task: M0 + M1 — Real Baseline & Output Quality

| Field        | Value         |
| ------------ | ------------- |
| **Status**   | 🟢 Active     |
| **Priority** | P0            |
| **Owner**    | @pytholic     |
| **Created**  | 2026-05-02    |
| **Updated**  | 2026-05-02    |
| **Branch**   | feature/m0-m1 |
| **Scope**    | ~1–2 sessions |

## Context

Split model configuration so orchestrator and researcher use different models, then apply prompt-level output quality fixes from the output-quality-guide. No graph restructuring.

- **M0**: Expose `orchestrator_model` / `researcher_model` params in `create_deep_research_agent`, update UI server and `examples/run.py`, run baseline with `gpt-4.1` / `gpt-4o-mini`.
- **M1**: Six prompt/config changes — mandatory `read_file`, expert persona, negative constraints, depth requirements, XML analysis block, quality-based stop + researcher output template.

Plan file: `.claude/plans/2026-04-28-m0-m1-baseline-and-output-quality.md`

## Plan

### M0 — Model param split + baseline

- [ ] **T1** Write failing tests → `tests/unit/test_agent_factory.py`
- [ ] **T2** Implement split in `agent.py` (signature + two usages)
- [ ] **T3** Update `ui/server.py` RunRequest fields
- [ ] **T4** Update `examples/run.py` call site
- [ ] **T5** Run 3 baseline queries, fill `docs/baseline-findings.md`

### M1 — Prompt quality improvements

- [ ] ~~**T6** Write failing tests → `tests/unit/test_prompts.py`~~ *(skipped — not worth the overhead)*
- [x] **T7** Replace `FILE_USAGE_INSTRUCTIONS` in `prompts/system.py`
- [x] **T8** Replace `OUTPUT_FORMAT_INSTRUCTIONS` in `prompts/system.py`
- [x] **T9** Replace stop conditions + add `<Output Format>` in `prompts/summarize.py`
- [ ] **T10** Run same 3 queries, compare vs M0, update `docs/baseline-findings.md`

## M0 Test Steps (T1 brief)

Five assertions in `tests/unit/test_agent_factory.py` verifying the factory signature:

1. `orchestrator_model` param exists
2. `researcher_model` param exists
3. `model_name` param is gone
4. `orchestrator_model` default is `"gpt-4.1"`
5. `researcher_model` default is `"gpt-4o-mini"`

Run: `uv run pytest tests/unit/test_agent_factory.py -v` — expect 5 failures before T2.

## Blockers

- **Sub-agent missing `read_file` tool**: `RESEARCHER_INSTRUCTIONS` now tells the researcher to call `read_file()` before synthesizing, but `research_sub_agent` in `agent.py` only has `[tavily_search, arxiv_search, think_tool]`. Fix: add `read_file` (and likely `ls`) to the sub-agent's tool list in `agent.py`.

## Notes / Findings

- **Ollama memory**: Running two different models (orchestrator + researcher) with Ollama loads both into VRAM simultaneously — can OOM on consumer hardware. Mitigations in order of preference: (1) pass the same model name for both params when using Ollama, (2) set `OLLAMA_MAX_LOADED_MODELS=1` env var, (3) set `max_concurrent_research_units=1`. Not a concern for OpenAI API runs (M0 baseline).

## Session Log

- **2026-05-02:** Task created. Branch `feature/m0-m1` checked out. Starting T1.
