# Deep Research Agent: Output Quality Guide

A diagnostic and improvement guide for why your agent produces shallow outputs and how to fix it.

---

## The Problem in Your Example

Your query: _"Find the most recent arxiv papers on LLM agents and summarize their key contributions."_

The response returned 3 papers with short bullet-point summaries, one of which ("DeVI: Physics-based Dexterous Human-Object Interaction") is barely relevant to LLM agents. That's the key tell: **the agent stopped at the arxiv abstract and never synthesized deeper**. Increasing `max_results` just gave you more shallow summaries.

This is a **compounding failure** across three layers: the model layer, the prompt/orchestration layer, and the data ingestion layer. Each one individually would cause problems; together they produce the shallow output you see.

---

## Root Cause Diagnosis

### 1. Model: `gpt-4o-mini` Has a Trained Conciseness Bias

**This is the primary issue.** Your agent at [agent.py:44](src/deep_research_agent/agent.py#L44) uses `gpt-4o-mini` with `temperature=0.0` for everything — both orchestration and the final synthesis step.

`gpt-4o-mini` is engineered for speed and cost efficiency. Its RLHF (reinforcement learning from human feedback) training heavily biases it toward brief, summarized, direct responses — because that's what human raters reward in conversational contexts. When tasked with a broad research directive, it interprets "adequate" as the first response that mathematically satisfies the prompt, then stops. Unlike reasoning models (o1/o3) that engage in extended internal planning before generating output, gpt-4o-mini generates reactively: it processes context and immediately starts emitting the final token stream.

**Model comparison for agentic research:**

| Model                | Optimal Agentic Role                               | Synthesis Depth                          |
| -------------------- | -------------------------------------------------- | ---------------------------------------- |
| `gpt-4o-mini`        | Sub-agent tool calls, triage, formatting           | Low — prone to extreme summarization     |
| `gpt-4o` / `gpt-4.1` | Orchestration, final report generation             | High — follows negative constraints well |
| `o1` / `o3-mini`     | Complex data synthesis, scientific review          | Very high — native multi-hop reasoning   |
| `claude-3-5-sonnet`  | Parallel researcher nodes, long-context extraction | High — exceptional context retention     |

**Fix:** Split the model assignment — strong model for orchestration and synthesis, mini for sub-agent tool calls.

```python
def create_deep_research_agent(
    orchestrator_model: str = "gpt-4.1",       # strong model for synthesis
    researcher_model: str = "gpt-4o-mini",      # cheap model for tool calls
    ...
):
    orchestrator = init_chat_model(model=orchestrator_model, temperature=0.2)
    researcher = init_chat_model(model=researcher_model, temperature=0.0)
```

---

### 2. The Agent Is Not Reading Files Before Synthesizing

Look at the virtual filesystem workflow in [system.py:74](src/deep_research_agent/prompts/system.py#L74):

```
1. Orient  → ls()
2. Save    → write_file() (user request)
3. Research → search tools write files
4. Read    → read the files and answer
```

The agent is supposed to call `read_file()` on each paper file before writing the final response. But `gpt-4o-mini` **skips step 4** — it sees the truncated ToolMessage summaries and synthesizes from those directly.

**Evidence in your code** — [arxiv_tool.py:144](src/deep_research_agent/tools/arxiv_tool.py#L144):

```python
summaries.append(f"- {result.filename}: {result.summary}...")
```

The ToolMessage contains the arxiv abstract truncated with `...`. The agent sees this and considers itself done. It never reads the full file.

**Fix:** Add a mandatory read instruction to `FILE_USAGE_INSTRUCTIONS`:

```python
FILE_USAGE_INSTRUCTIONS = """...
## MANDATORY: Before Writing Your Final Response
1. Use ls() to list all saved files
2. Use read_file() on EVERY research file to access full content
3. Only THEN write your final response using the actual file content

NEVER write a final response based only on tool call summaries. Always read the files first.
"""
```

---

### 3. The Arxiv Tool Returns Only Abstracts — No Full Paper Content

In [arxiv_tool.py:55-78](src/deep_research_agent/tools/arxiv_tool.py#L55-L78), the `process()` method uses `result.summary` (the arxiv abstract) and sets `raw_content=""`. The file saved to the virtual filesystem contains only the abstract.

This is why your summaries look like abstract paraphrases — that's literally all the data available to synthesize.

**Fix options (ordered by impact):**

**Option A — LLM-based abstract expansion (easy, fast)**
Pass the abstract through the `think_tool` with a prompt to extract deeper implications, methodological details, and comparisons to prior work from the abstract text alone.

**Option B — Download and parse the PDF (best quality)**
The `arxiv` library supports PDF download. Parse with `pymupdf` or `pypdf`:

```python
def download_paper_text(result: arxiv.Result, dirpath: str) -> str:
    result.download_pdf(dirpath=dirpath)
    # parse PDF text with pymupdf or pypdf
    ...
```

**Option C — Semantic Scholar API (good middle ground)**
Provides structured paper data: TLDRs, full abstracts, citation counts, influential citations, and structured field extraction — without the PDF parsing complexity.

---

### 4. The Sub-Agent Stops Too Early (Count-Based, Not Quality-Based)

In [summarize.py:62-70](src/deep_research_agent/prompts/summarize.py#L62-L70):

```
Stop Immediately When: You have 3+ relevant examples/sources
```

For "find the most recent LLM agent papers", the sub-agent does:

1. 1 arxiv search → gets 3 papers → `3+ sources found` → **STOP**

It never cross-references with web sources, checks recency independently, or validates relevance.

**Fix:** Replace count-based stop conditions with quality-based ones:

```python
**Stop When**:
- You have answered the question with specifics (numbers, dates, method names)
- You have cross-referenced at least 2 independent sources on each key claim
- You have checked BOTH arxiv AND web sources when the topic spans research and application
```

---

### 5. The Researcher Prompt Has No Output Depth Instructions

[RESEARCHER_INSTRUCTIONS](src/deep_research_agent/prompts/summarize.py#L32) tells the sub-agent how to search but gives it **no instructions on how to write its findings**. It dumps whatever the tool returned, producing shallow files that the parent agent then synthesizes shallowly.

**Fix:** Add an explicit output template to the researcher:

```python
<Output Format>
After completing research, write findings to a file. Each source MUST include:
1. **What**: The specific contribution or finding (not a vague description)
2. **How**: The mechanism or method used
3. **Why it matters**: Concrete improvements over prior work
4. **Evidence**: Specific numbers, benchmark results, dataset names, or comparisons

BAD: "The paper introduces a new method for LLM agents that improves performance."
GOOD: "ReAct-v2 achieves 87.3% on HotpotQA (vs 71.2% for CoT) by interleaving reasoning
       traces with tool calls using a learned action selector trained on 12K examples."

Do NOT paraphrase the abstract. Extract the substance.
</Output Format>
```

---

### 6. The Synthesizer Prompt Has No Depth Requirements or Negative Constraints

[OUTPUT_FORMAT_INSTRUCTIONS](src/deep_research_agent/prompts/system.py#L128) specifies markdown formatting but says nothing about output depth, minimum content requirements, or what to avoid.

Without negative constraints, models default to their trained preference: brief, bullet-point summaries.

**Fix:** Add three elements to the synthesizer prompt:

**Negative constraints** (explicitly forbid brevity):

```
- Do NOT provide brief, high-level summaries
- Do NOT use bullet points for qualitative analysis — write analytical prose
- Do NOT omit technical methodologies or benchmark results found in the source files
```

**Expert persona** (anchors the model's output register toward professional literature):

```
You are an expert research analyst writing a detailed technical briefing for
a senior ML engineer. Write at the depth and density of a published survey paper.
```

**Depth requirements**:

```
## Depth Requirements
- Explain the specific contribution per source — not just the topic
- Include concrete specifics: method names, benchmark scores, dataset sizes
- Connect findings across sources: what trends emerge? what do multiple papers agree on?
- Minimum 2-3 sentences of analysis per source (not restating the title or abstract)
- End with a synthesis section answering: "What does this mean for the field?"
```

---

### 7. State Overwriting Loses Context During Loops

This is less visible but becomes critical once you add iterative research (see the Reflection Loop section below). If your graph loops — searching paper A, analyzing it, then looping to search paper B — a state field configured to **overwrite** will lose paper A's analysis when paper B is retrieved.

Your current `state.py` uses a `file_reducer` for the `files` dict, which is correct. But if you extend the state to track intermediate analysis notes, search history, or draft content, those fields need reducer annotations too:

```python
from operator import add
from typing import Annotated
from langgraph.graph import MessagesState

class DeepAgentState(MessagesState):
    files: Annotated[dict[str, str], file_reducer]
    research_notes: Annotated[list[str], add]   # accumulates, never overwrites
    follow_up_queries: Annotated[list[str], add] # for reflection loop
    draft: str                                   # overwrite is fine here
    iteration_count: int
```

Without `operator.add` on list fields, a looping graph becomes amnesic — it can only report on its most recent action.

---

## Advanced Fixes (Architectural)

The above fixes address symptoms. The following address the deeper architectural constraints that prevent the system from producing multi-page, expert-grade research.

### Iterative Reflection Loop

The single biggest missing architectural piece. Currently your graph is linear:

```
PLAN → SEARCH → READ → SYNTHESIZE → END
```

A deep research architecture should be cyclical:

```
PLAN → SUB-QUERIES → SEARCH → READ → SYNTHESIZE → REFLECT → (STOP or LOOP)
```

After the synthesizer writes an initial draft, a **Reflection Node** evaluates it against the original query — acting as an adversarial critic. If the draft is too shallow, lacks technical depth, or misses requirements, the reflection node generates targeted follow-up queries and routes the graph back to the search workers for another round.

```python
# Conceptual reflection prompt
REFLECTION_INSTRUCTIONS = """
You are an adversarial academic reviewer evaluating a research draft.
Evaluate the draft against the original query: {original_query}

Check for:
- Missing technical specifics (methods, benchmarks, comparisons)
- Claims made without evidence from the source material
- Topics in the query not addressed in the draft
- Sections that merely paraphrase abstracts without analysis

If the draft is insufficient, output:
  decision: "loop"
  follow_up_queries: ["specific query 1", "specific query 2"]

If the draft is complete, output:
  decision: "stop"
"""
```

The conditional edge evaluates `decision` and routes accordingly, with a hard cap on `iteration_count` to prevent infinite loops.

---

### XML Chain-of-Thought Before Final Output

Force the synthesizer to reason explicitly before writing prose. This prevents the model from jumping to a shallow summary — it must first complete an analysis pass:

```python
SYNTHESIZER_INSTRUCTIONS = """
Before writing the final report, you MUST complete an analysis block:

<analysis>
- List the key finding from each source
- Identify agreements and contradictions across sources
- Determine the central narrative that connects all findings
- Note any gaps that couldn't be answered from the available sources
</analysis>

Only after completing the <analysis> block, write the final report in markdown.
"""
```

This is an enforced form of Chain-of-Thought. The model is required to correlate and digest all data before summarizing, which naturally produces longer, more coherent output.

---

### Memory Pointer Pattern (for Full-Document Ingestion)

If you implement PDF download (Root Cause #3, Option B), three 15,000-word papers will overflow the context window and cause **silent degradation** — the model appears to succeed but truncates internally and loses track of its assignment. The user never sees an error.

Instead of injecting raw paper text into the LLM context, use the Memory Pointer Pattern:

1. The extraction tool stores the full paper text in a vector store (e.g., Chroma, Qdrant, or even a local dict indexed by paper ID)
2. The tool returns only a lightweight reference ID (the pointer) to the LLM
3. When the synthesizer needs specific details, it calls a retrieval tool with the pointer, pulling only the semantically relevant chunks into its active context

This keeps the active context window small and focused while making full paper content available on demand.

---

### Plan-and-Execute Decomposition

Currently the orchestrator jumps directly to search delegation. For complex queries, adding a dedicated **Planner Node** before search improves coverage and specificity:

```
User Query → [Planner Node] → Structured Sub-Queries → [Parallel Researchers]
```

The planner decomposes "find the latest LLM agent papers" into:

- "LLM agent architectures for robotics and physical control"
- "Multi-agent coordination and alignment frameworks"
- "LLM agent evaluation benchmarks 2025-2026"

Each sub-query goes to a dedicated researcher with isolated context. This prevents all researchers from returning the same homogeneous results from a single generalized search.

---

## Priority Fix Order

| Priority | Issue                                     | Fix                                                                                     | Effort     |
| -------- | ----------------------------------------- | --------------------------------------------------------------------------------------- | ---------- |
| 1        | `gpt-4o-mini` for synthesis               | Use `gpt-4.1` or `gpt-4o` for orchestrator                                              | Low        |
| 2        | Agent skips `read_file()`                 | Add mandatory read instruction to `FILE_USAGE_INSTRUCTIONS`                             | Low        |
| 3        | No output depth in researcher             | Add `<Output Format>` block to `RESEARCHER_INSTRUCTIONS`                                | Low        |
| 4        | No synthesis depth / negative constraints | Add depth requirements + negative constraints + persona to `OUTPUT_FORMAT_INSTRUCTIONS` | Low        |
| 5        | Count-based stop condition                | Replace with quality-based stop in `RESEARCHER_INSTRUCTIONS`                            | Low        |
| 6        | Arxiv returns only abstracts              | Option A: LLM expansion; Option B: PDF download                                         | Low–Medium |
| 7        | No reflection loop                        | Add Reflection Node + cyclical edges                                                    | High       |
| 8        | No XML chain-of-thought                   | Add `<analysis>` block requirement to synthesizer prompt                                | Low        |
| 9        | State reducer gaps                        | Annotate new state fields with `operator.add`                                           | Low        |
| 10       | Context overflow on full docs             | Implement Memory Pointer Pattern                                                        | High       |

---

## Quick Wins (Do These First)

Items 1–5 and 8 require only model config and prompt changes — no graph restructuring:

1. **Upgrade orchestrator model** — `gpt-4.1` or `gpt-4o` for the parent agent
2. **Force `read_file()` before final response** — add MANDATORY read instruction to `FILE_USAGE_INSTRUCTIONS`
3. **Add output depth template to researcher** — What/How/Why/Evidence structure with a BAD/GOOD example
4. **Add negative constraints + expert persona to synthesizer** — explicitly forbid bullet summaries, set expert register
5. **Fix stop condition** — quality-based rather than count-based
6. **Add XML analysis block to synthesizer** — `<analysis>` pass before markdown output

These six changes alone should produce substantially deeper outputs. Then tackle the reflection loop and arxiv PDF ingestion.

---

## References

- [LangChain: Context Management for Deep Agents](https://www.langchain.com/blog/context-management-for-deepagents) — context offloading thresholds and goal drift during summarization
- [Agents 2.0: From Shallow Loops to Deep Agents](https://towardsai.net/p/machine-learning/agents-2-0-from-shallow-loops-to-deep-agents) — architectural causes of shallow single-pass agents
- [AgentCPM: Interleaving Drafting and Deepening for Deep Research](https://arxiv.org/html/2602.06540v1) — iterative deepening and draft-then-reflect architecture
- [Deep Research: A Survey of Autonomous Research Agents](https://arxiv.org/html/2508.12752v1) — synthesis as a reasoning mechanism, not transcription
- [JetBrains: When Tool-Calling Becomes an Addiction](https://blog.jetbrains.com/ai/2025/07/when-tool-calling-becomes-an-addiction-debugging-llm-patterns-in-koog/) — agents trapped in tool loops instead of synthesizing
