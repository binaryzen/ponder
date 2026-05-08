# Ponder

A streaming, asynchronous, feedback-coupled multi-agent inference system organized around a neuromorphic metaphor. Multiple specialist models — each owning a cognitive function analogous to a brain region — share a stateful blackboard and produce labeled output into a response generator (Broca) in real time.

This is not a chatbot with a router. It is a synthetic mind with a voice.

For project context, design history, and architectural decisions, see [`CONTEXT.md`](../../CONTEXT.md) at the repo root and the `design/` directory. For deferred-improvement notes, see [`design/post-poc-review.md`](../../design/post-poc-review.md).

---

## What's in the box

| Tool | Purpose |
|---|---|
| **`ponder`** | Single-turn Phase 1 LangGraph pipeline (Thalamus → Hippocampus → Prefrontal → Broca) |
| **`ponder-audit`** | CLI viewer for the audit event stream (live tail / trace listing / per-trace tree) |
| **`ponder-diagnostics`** | Browser-based diagnostic panel — live state, context, traces, and request/response loop |
| **Orchestrator demos** | Mock specialists exercising the M1.1 reactive substrate (chatter, streaming, streaming_v2) |
| **Test suite** | 138 unit tests (regions, pipeline, audit, orchestrator, state, simulated, diagnostics) |

---

## Quickstart (local POC)

From the project root:

```bash
# 1. Bring up Redis + Qdrant
docker compose up -d

# 2. Install Ollama (https://ollama.com) and pull the POC model
ollama pull phi3.5

# 3. Install the Python package (from src/ponder/)
cd src/ponder && pip install -e ".[dev]" && cd ../..

# 4. Configure environment for local POC
cp .env.poc.example .env
# Load it: PowerShell:  Get-Content .env | ForEach-Object { if ($_ -match '^([^#=]+)=(.*)$') { Set-Item "Env:$($matches[1])" $matches[2] } }
# bash:        export $(cat .env | xargs)

# 5. Run a turn
ponder "What is the capital of France?"
```

Note: pip may put `ponder.exe` somewhere not on your PATH. Fallback: `python -m ponder "..."`.

---

## Architecture (Phase 1 pipeline)

```
  raw_input
      │
      ▼
┌───────────┐
│ Thalamus  │  encoder classifier → input_type
└─────┬─────┘
      │
      ▼
┌─────────────┐
│ Hippocampus │  vector retrieval → retrieved_memories
└──────┬──────┘
       │
       ▼
┌─────────────┐
│  Prefrontal │  generative (plan) → task_plan
└──────┬──────┘
       │
       ▼
┌───────┐
│ Broca │  generative (voice) → response_draft
└───────┘
```

| Region | Reads | Writes | Model (POC / production) |
|---|---|---|---|
| Thalamus | `raw_input` | `input_type` | MiniLM encoder (CPU) |
| Hippocampus | `raw_input` | `retrieved_memories` | MiniLM encoder + Qdrant |
| Prefrontal | `raw_input`, `input_type`, `retrieved_memories`, `operator_context`, `rules_of_engagement` | `task_plan` | phi3.5 (Ollama) / Mistral-7B-Instruct-v0.3 (vLLM) |
| Broca | full state | `response_draft`, `goal_achieved` | phi3.5 (Ollama) / Mistral-7B-Instruct-v0.3 (vLLM) |

Thalamus classifies into: `question` | `command` | `statement` | `greeting` | `clarification`.

The Phase 2 reactive substrate (orchestrator) is documented under [`CONTEXT.md`](../../CONTEXT.md) and exercised via the demos below.

---

## Running each tool

### `ponder` — single-turn pipeline

Issues one full Phase 1 turn end-to-end and prints Broca's response.

```bash
ponder "What color is the sky?"

# explicit env override
PONDER_MODEL_URL=http://localhost:11434 ponder "Tell me a fact about octopuses"
```

Requires: Redis, Qdrant, and an OpenAI-compatible LLM endpoint reachable per the env-var configuration.

### `ponder-audit` — audit stream viewer

Three modes against the Redis audit stream (`ponder:<unit>:audit`):

```bash
# Recent traces, newest first
ponder-audit traces

# Tree of one trace's events (prefix-matched, so 8 chars is enough)
ponder-audit trace 043c1386

# Live tail — Ctrl+C to stop
ponder-audit tail
```

Requires only Redis. Reads through `ponder.audit.service`.

### `ponder-diagnostics` — interactive diagnostic panel

Embedded FastAPI server + browser UI. Boots a panel-friendly orchestrator runtime in the same process and serves a live introspection page.

```bash
ponder-diagnostics                  # http://localhost:8080/
ponder-diagnostics --port 8082      # different port
ponder-diagnostics --max-seconds 60 # auto-stop after N seconds (default: run until Ctrl+C)
```

What you see in the panel:

- **Components** (left) — registered specialists with priority/model/tick badges
- **Context URNs** (left, lower) — registered context: URNs; click to inspect
- **Component state** (middle, top) — the selected component's blackboard entries
- **Context value** (middle, bottom) — the selected URN's current value
- **Trace** (right, full height) — live event stream from the audit stream (SSE)
- **Input / Output** (bottom) — type a request, see the cogitator's chunked response in spoken_log

Live updates use Server-Sent Events; no polling lag. Two streams: `/api/state/stream` (blackboard writes) and `/api/events/stream` (audit events).

Requires: Redis (for audit stream). The runtime built by `runtime_factory.build_panel_runtime()` uses the simulated cogitator/speaker/interrupt-handler from M1.1 — it does not call the real LLM (mock latency only). Replace with a real-LLM specialist when you're ready.

### Orchestrator demos (no entry-point script — invoke via `python -m`)

Three scenarios validating the M1.1 reactive substrate:

```bash
# 5 mock specialists exercising tick + state-change activation, priority,
# semaphore gating, cascading state changes
python -m ponder.orchestrator.demos.chatter

# Long-running cogitator with chunked output + mid-flow user interrupt
python -m ponder.orchestrator.demos.streaming

# Same scenario migrated to the StateStore + ContextService layer
python -m ponder.orchestrator.demos.streaming_v2
```

Each demo runs ~10–15s and exits. They write to the live audit stream — inspect with `ponder-audit traces` after.

---

## Configuration

All configuration goes through environment variables. The Python package reads them via `ponder.config.Config`:

| Variable | Default | Used by |
|---|---|---|
| `PONDER_REDIS_URL` | `redis://localhost:6379` | audit emitter, blackboard (Phase 2+) |
| `PONDER_QDRANT_URL` | `http://localhost:6333` | Hippocampus |
| `PONDER_MODEL_URL` | `http://localhost:8000` | model_client (no `/v1` suffix; client appends `/v1/chat/completions`) |
| `PONDER_ENCODER_MODEL` | `sentence-transformers/all-MiniLM-L6-v2` | Thalamus, Hippocampus |
| `PONDER_GENERATIVE_MODEL` | `mistralai/Mistral-7B-Instruct-v0.3` | identifier sent to LLM endpoint |
| `PONDER_MEMORY_COLLECTION` | `hippocampus` | Qdrant collection name |
| `PONDER_MEMORY_TOP_K` | `5` | Hippocampus retrieval k |
| `PONDER_MODEL_MAX_TOKENS` | `1024` | LLM call max tokens |
| `PONDER_MODEL_TEMPERATURE` | `0.7` | LLM sampling temperature |
| `PONDER_PROMPTS_DIR` | `<package>/../prompts` | Where Prefrontal / Broca templates are read from |

Local POC overrides live in [`.env.poc.example`](../../.env.poc.example) at the repo root — Ollama on port 11434, phi3.5 model. The same `model_client` works against both Ollama and vLLM; the only thing that changes is `PONDER_MODEL_URL` and `PONDER_GENERATIVE_MODEL`.

### Local services

[`docker-compose.yml`](../../docker-compose.yml) at the repo root provisions:

- **Redis 7.2-alpine** — port 6379, append-only persistence, 2 GB memory cap
- **Qdrant v1.17.1** — port 6333 (HTTP) and 6334 (gRPC)

Both with healthchecks and named volumes (`docker compose down -v` to drop data).

Ollama runs natively on the host (not in compose) — it benefits from native GPU access on Mac/Windows where Docker GPU support is limited.

---

## Testing

```bash
cd src/ponder
pytest          # run all
pytest -q       # quiet
pytest tests/test_orchestrator.py -q  # one file
```

Tests mock all external dependencies (model server, Qdrant, Redis, audit emit). They validate:

- **Phase 1 pipeline**: state shape, region contracts, classification logic, memory formatting, template rendering, pipeline wiring
- **Audit subsystem**: event field names (OTel-aligned), emitter wire format, instrumentation wrapper, service layer pagination + filtering
- **Orchestrator substrate**: blackboard subscriptions, specialist contract, runtime activation patterns (state-change, tick, predicate filters), model semaphore gating, priority dispatch, cascade
- **Simulated primitives**: latency profile (fixed/jittered/step-up), pacing profile (chunked, bursty)
- **State / context layer**: namespaced writes, provider primitives (passthrough, default, highest-confidence, composite), context recompute on dependency change
- **Diagnostics API**: snapshot / events / input / interrupt endpoints, SSE route registration

Test count at last full run: **138**.

---

## Project structure

```
src/ponder/
  pyproject.toml          Package manifest; deps + console scripts
  README.md               This file
  prompts/
    prefrontal_v1.txt     System prompt for Prefrontal
    broca_v1.txt          System prompt for Broca
  ponder/                 Python package
    __init__.py
    __main__.py           `ponder` CLI entry
    blackboard.py         BlackboardState TypedDict + initial_state()
    config.py             Config (Pydantic), all fields env-overridable
    model_client.py       Shared generate() for generative regions
    regions/
      thalamus.py         Encoder-based input classifier
      hippocampus.py      Memory retrieval (Qdrant) + store_memory()
      prefrontal.py       Goal decomposition (generative)
      broca.py            Response generation (generative)
    graph/
      pipeline.py         LangGraph Phase 1 linear graph
    audit/                M1 audit subsystem
      events.py           AuditEvent + EventType (OTel-aligned)
      context.py          ContextVars for trace propagation
      emitter.py          Redis Stream publisher, resilient
      instrumentation.py  audit_wrap, emit_pipeline_event
      service.py          Resource-oriented read API (events, traces, tail)
      cli.py              `ponder-audit` CLI implementation
    orchestrator/         M1.1 reactive substrate
      blackboard.py       Async-aware key/value store with subscription
      specialist.py       Specialist protocol
      dispatcher.py       Priority queue + worker pool + model semaphore
      runtime.py          Lifecycle + state-change reaction
      simulated.py        LatencyProfile / PacingProfile (mock work)
      state.py            StateStore + ContextService + provider primitives
      demos/
        chatter.py
        streaming.py
        streaming_v2.py
    diagnostics/          M1.2 diagnostic panel
      __main__.py         `ponder-diagnostics` CLI entry
      server.py           FastAPI app (snapshot, events, SSE, input)
      panel.html          Single-file UI (HTML + CSS + vanilla JS)
      runtime_factory.py  Builds the panel-friendly runtime
  tests/                  138 unit tests
    test_blackboard.py
    test_config.py
    test_thalamus.py
    test_hippocampus.py
    test_prefrontal.py
    test_broca.py
    test_pipeline.py
    test_audit_events.py
    test_audit_emitter.py
    test_audit_instrumentation.py
    test_audit_service.py
    test_orchestrator.py
    test_simulated.py
    test_state.py
    test_diagnostics.py
```

---

## Further reading

- [`CONTEXT.md`](../../CONTEXT.md) — canonical project context (architecture invariants, phase plan, stack decisions)
- [`design/`](../../design/) — working design conversations and notes
  - [`interview.md`](../../design/interview.md) — design sessions 1–4
  - [`concepts.md`](../../design/concepts.md) — Concepts 1–11
  - [`data-structures.md`](../../design/data-structures.md) — v1 normative spec
  - [`audit-interface.md`](../../design/audit-interface.md) — audit service contract
  - [`phase1-trace.md`](../../design/phase1-trace.md) — runtime trace of one Phase 1 turn
  - [`post-poc-review.md`](../../design/post-poc-review.md) — deferred items, anatomy review punch list
  - [`drift-check-playbook.md`](../../design/drift-check-playbook.md) — two-stage doc-alignment process
