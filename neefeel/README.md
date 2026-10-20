# Neefeel — AI Co-founder Platform

One founder-facing `AICofounder` (Tier 1) turns a conversation into a typed task
DAG, runs it across seven AI executives (Tier 2) in parallel waves, with scoped
3-tier memory, a human-in-the-loop (HITL) safety layer, a code builder that
writes a runnable web prototype, and a Streamlit dashboard.

## Layout

```
neefeel/
  models.py                 Typed contracts (StructuredTask, TaskResult, ExecutiveBriefing, ...)
  llm.py                    The only place that calls the model: fresh agent per call,
                            timeout + retry, <think> stripping, JSON repair round-trip
  text_utils.py             extract_json, strip_think, infer_status_and_risks, output-format footer
  cofounder.py              Dialogue, decomposition, run control, synthesis; all system prompts
  orchestration/
    task_graph.py           DAG: validation, dependency states, ready waves
    engine.py               Parallel waves, HITL pre-run gate + post-run review, failure isolation
  executives/               base.py + product/design/engineering/growth/legal/finance/people
  builder/
    code_builder.py         Spec -> files (delimited FILE blocks, no JSON escaping)
    preview.py              Sanitized write to disk, optional browser open
  memory/
    scopes.py               Tier 1 Global / Tier 2 Department / Tier 3 Task context
    persistent_store.py     Store interface + in-process cosine store
    pinecone_store.py       Pinecone backend (implemented)
    embeddings.py           Hash embedder (dev only, NOT semantic) and OpenAI embedder
    session_state.py        Sliding-window conversation history
  safety/
    hitl.py                 Pre-run gate rules
    conflict.py             Cross-department conflict detection + resolution
  dashboard/                Streamlit app, DAG renderer, preview embedder
  tests/                    pytest suite (no network, no API key)
  benchmarks/               Live-API timing scripts (not tests)
```

## How a run works

1. `chat()` — dialogue. The co-founder replies in JSON with an `intent`; when
   it is `ready_for_execution` it also writes a self-contained `execution_brief`.
2. `decompose(brief)` — the planner returns tasks. The plan is validated as a
   real DAG (unique ids, known dependencies, no cycles) inside a repair loop.
3. `execute(plan)` — the engine runs ready tasks in parallel waves. Each
   executive receives: global facts, its own department's history, and the
   **output of the tasks it depends on** (Tier-3 memory, passed directly).
4. HITL — see below.
5. `synthesize(prompt, plan)` — conflicts are detected and resolved, then one
   `ExecutiveBriefing` is produced. Deliverables, pending confirmations and the
   preview path are filled in by code, not by the model.

All output for a run lives in `neefeel_projects/<run_id>/` (deliverables under
`deliverables/`, prototypes in their own folders), so runs never overwrite each other.

## HITL: two gates with different meanings

* **Pre-run gate** — "do not start until authorized". Set by the planner's
  `requires_human_confirmation`, by policy for every Legal task, and by a
  deterministic scan that targets tasks that *perform or commit to* an action
  (live deploy, real spend, mail to real customers, signing, deletion). Tasks
  that draft, design, model or plan are not gated by topic words alone.
* **Post-run review** — an executive ends with `STATUS: blocked_on_hitl`. The
  finished draft is held. **Approve** accepts it as-is (no second model call);
  **Modify** re-runs it with your new instruction; **Reject** fails it.
  A task you already authorized up front is not asked twice.

Tasks downstream of a blocked or failed task show `blocked_on_dependency` and
resume automatically once their dependencies complete.

## Web preview

The build task is guaranteed: if the planner omits `should_build`, `ensure_build_task`
flags the best-matching engineering task (never a deploy step). The builder has its own
output budget (`NEELFEEL_BUILDER_MAX_TOKENS`, default 24000; documents use
`NEELFEEL_MAX_TOKENS`, default 8000), tolerates a reply cut off after `</html>`, and
retries once asking for a compact single-file build. If the build still fails, the
dashboard shows the reason and a **Retry prototype build** button (it reuses the finished
architecture; no other task re-runs). The preview renders in a sandboxed iframe.

## Prompt ↔ code contracts (enforced by tests)

* Prompt JSON keys match the Pydantic models (`tests/test_alignment.py`).
* The phrases executives are told to write (`contradicts Product's pricing:`,
  `contradicts Finance's runway:`, `contradicts Product's scope:`,
  `STATUS: blocked_on_hitl`) are exactly what the parsers and conflict resolver detect.
* Departments named in prompts equal the `Department` enum.

## Running

```bash
pip install -r requirements.txt
cp neefeel/.env.example neefeel/.env      # add your key; never commit .env

python -m neefeel.main                     # CLI demo (run from the folder containing neefeel/)
streamlit run neefeel/dashboard/app.py     # dashboard
pytest neefeel/tests                       # no network or key needed
```

Each API key is only ever sent to its own provider's base URL.

## Known limits

* Memory is in-process by default and the default embedder is a hash function
  (token-overlap-like, not semantic). Use `PineconeMemoryStore` with a real
  embedder (`OpenAIEmbedding`) for persistence and true semantic recall.
* Output parsing of executive text is heuristic by design (see
  `OUTPUT_FORMAT_INSTRUCTIONS`); a model that ignores the format yields
  `completed` with no risks.
* One active run per `AICofounder` instance.
