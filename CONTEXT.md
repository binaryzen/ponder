# Synthetic Mind — Project Context

Source of truth for project decisions and specifications. The `.docx` spec is
auxiliary / archival. Updates here are the canonical record.

---

## What this project is

A streaming, asynchronous, feedback-coupled multi-agent inference system
organized around a neuromorphic metaphor. Multiple specialist models — each
owning a cognitive function analogous to a brain region — share a stateful
blackboard and stream labeled output chunks into a response generator (Broca)
in real time.

This is not a chatbot with a router. It is a synthetic mind with a voice.

The biological framing is the hook, but the architecture is not constrained to
it. Non-biological region types are expected in later phases.

---

## Core design principles

These four properties are architectural invariants — not implementation details.
Every phase must preserve them.

### 1. Reasoning before speaking

No region that produces output visible to the user may receive raw input
directly. All input passes through classification and planning stages first.
Broca is always last. This is enforced structurally, not by convention.

**Consequence:** Time-to-first-token is a function of reasoning depth. The fast
battery (Thalamus, Amygdala) must be genuinely cheap so simple inputs don't pay
the full planning cost.

### 2. Out-of-order buffer consumption

Broca consumes from a context buffer (Redis Stream) that is filled by upstream
regions as they complete — not necessarily in input order. Broca generates from
whatever is available, not from a fully assembled, sequentially ordered context.

**Consequence:** Broca must generate coherently from partial context. The
interrupt semantics (restart vs. append on late chunk arrival) are a first-class
design decision, not an edge case. See open questions.

### 3. Raw input does not reach Broca

Broca has no access to `raw_input`. It receives only the distilled outputs of
upstream regions: `input_type`, `retrieved_memories`, `task_plan`, and
tone/modulation signals. This prevents the literal phrasing of the input from
over-specifying the response.

**Consequence:** The system responds to what it understood, not what was
literally asked. Errors manifest as confident responses to misread intent —
surfacing intermediate state is the mitigation.

### 4. Tone is a drivable sub-system

A dedicated region (Conscience in Phase 1; a tone modulator in later phases) is
responsible for register, affect, and style. It can be driven implicitly
(inferred from urgency score, input type, retrieved context) or explicitly
(operator-set fields). The operator does not need to lead — tone is a
persistent, configurable property of the system, not a per-turn instruction.

**Consequence:** "What to say" (Prefrontal → plan) and "how to say it" (tone
modulator → register) are separated. Broca assembles from both. Wrong urgency
scoring produces tone mismatches; calibration of Amygdala and Conscience is
therefore load-bearing.

---

## Infrastructure decisions

| Decision | Choice | Rationale |
|---|---|---|
| Cloud | Lambda Labs | Raw GPU access, no managed services tax, pay only for running instances |
| K8s | k3s, self-managed | Full control plane ownership, no managed K8s fee, installed via Ansible |
| GPU | A10G (Lambda Labs) | Sufficient for 7B model inference, available on Lambda |
| Artifact storage | Backblaze B2 | S3-compatible API, $0.006/GB/mo, scale-to-zero friendly |
| Container registry | GHCR | Free tier, cloud-agnostic |
| Provisioning | provision.sh (Lambda Labs API) + Ansible | Shell for instance launch, Ansible for cluster bootstrap |

## Scale-to-zero discipline

Lambda Labs charges only for running instances. No idle costs. Operational habit:
- Terminate instance when not working
- No Lambda persistent filesystems (use B2 instead)
- Inference Deployment scaled to 0 replicas when not serving

Estimated cost: ~$0.20/mo idle, ~$15–30/mo active development.

---

## Stack decisions

| Layer | Choice | POC variant |
|---|---|---|
| Orchestration | LangGraph | LangGraph (Phase 1 linear, Phase 2 concurrent) |
| Blackboard state | Redis Hash | In-memory dict (Phase 1); Redis (Phase 2+) |
| Message bus | Redis Streams (labeled chunk delivery to Broca) | Redis Streams via `docker-compose.yml` |
| Vector store | Qdrant (in-cluster, lightweight) | Qdrant v1.17.1 via `docker-compose.yml` |
| Packaging | Helm — one chart per cognitive unit, parameterized via values.yaml | Local dev: direct Python; POC: docker-compose |
| Base model | Mistral-7B-Instruct-v0.3 (production) | Phi-3.5-mini-instruct via Ollama (POC, modest HW) |
| Encoder model | sentence-transformers/all-MiniLM-L6-v2 (Thalamus, Amygdala) | same |

---

## POC local stack configuration

Phase 1 POC runs locally via `docker-compose.yml`:

- **Redis** (6379): blackboard state (Hash) + audit stream (`ponder:<unit>:audit`)
- **Qdrant** (6333): vector store for Hippocampus memory
- **Ollama** (11434): LLM inference server, serving phi3.5-mini-instruct (3.8B params)

Configuration via environment variables (see `.env.poc.example`):
- `PONDER_REDIS_URL=redis://localhost:6379`
- `PONDER_QDRANT_URL=http://localhost:6333`
- `PONDER_MODEL_URL=http://localhost:11434` (no `/v1` suffix — `model_client` appends `/v1/chat/completions`)
- `PONDER_GENERATIVE_MODEL=phi3.5`
- `PONDER_ENCODER_MODEL=sentence-transformers/all-MiniLM-L6-v2`
- `PONDER_PROMPTS_DIR=…/prompts` (live iteration without redeployment)

**Why phi3.5 for POC:** 3.8B parameters, ~4 GB resident, instruction-tuned on
synthetic data — strong at structured output and few-shot pattern following.
Comfortable on a 16 GB-RAM laptop with Docker also running. Mistral-7B reserved
for production when GPU headroom is available.

**First run:** `ollama pull phi3.5` downloads ~2.2 GB during one-time setup
(several minutes on typical broadband). After that, the first `ponder`
invocation pays a ~10–30s cold-start cost while Ollama loads the weights into
memory; subsequent calls within the same Ollama lifetime are fast.

---

## Portability constraints

Portability across cloud platforms is a design requirement. The only
platform-specific artifacts are `provision.sh` and the Ansible bootstrap
playbook. Everything above the OS must be portable without structural change.

Migrating to another platform should cost no more than half a day.

---

## Phase 2 design — Orchestrator substrate & schema-driven inference

Phase 2 has two parallel, coordinated work tracks: **orchestrator substrate**
(managing component activation patterns and communication topology) and
**schema-driven inference** (the reasoning mechanism itself). See
`design/interview.md` (Sessions 1–4) and `design/concepts.md` for the full
design conversation. Known-shortcut notes are tracked in
`design/post-poc-review.md`.

### Schema-driven inference mechanism

**Crystallized definition:** Reasoning is the process of:

1. **Recognition** — situation → ranked candidate schemas
2. **Selection** — choose lens(es) to apply  
3. **Slot completion** — generate slot-questions and propose answers

This is **schema-driven inference** (Gentner, Structure-Mapping Theory) / **candidate
inference** in structure-mapping terminology. The schema acts as an interrogative
probe that structures inquiry.

**Data structures (v1 normative spec):** `design/data-structures.md` defines
Schema, RecognitionResult, SelectionResult, AuditEvent, and related types.
All Phase 2+ schemas are authored under `notation_version: 1`; notation versioning
is monotonic integer, with migrations defined on breaking changes.

**Entity ID convention:** UUID v4.
- Bare UUID within single domain context
- `<domain>:<uuid>` crossing domain contexts
- `<domain>:<uuid>@<version>` for versioned schema references

### Audit subsystem (M1 implementation)

Separate Redis Stream `ponder:<unit>:audit` (alongside the existing inter-region
cognitive stream). Emits structured audit events (AuditEvent type) with trace IDs
for provenance tracking.

**Architecture:** Service abstraction (`design/audit-interface.md`) mediates between
Redis backend and multiple consumers (CLI viewer, future web viewer, scripts).
Resource-oriented API with cursor-based pagination using Redis Stream IDs. SSE
endpoint for live tailing. OpenTelemetry-compatible field naming (`span_id`,
`parent_span_id`, etc.) enables integration with Phoenix, Jaeger, or similar
backends.

**CLI viewer (`ponder-audit` script, M1):** Plain-text output, three commands —
`tail` (live event stream), `traces` (recent trace listing), `trace <id>`
(events for one trace, prefix-matched). Implemented in
`src/ponder/audit/cli.py` against the service layer. Textual-based
TUI with vim-style navigation (per `audit-interface.md`) is deferred; the
plain CLI is sufficient for current debugging.

### Orchestrator substrate (M1.1, validated under simulation)

A reactive event-driven runtime in `src/ponder/orchestrator/` — separate
from the LangGraph linear pipeline (which remains the Phase 1 turn shape).
`asyncio`-native, single-process. Validates the activation × communication
matrix the user requires:

| | Push to component input | Shared context (blackboard) |
|---|---|---|
| **Fire on demand** | DAG-style invocation | Write-on-call |
| **Rate-limited loop** | Periodic input emission | Periodic update |

Plus contextual modulation (activation/rate determined by state).

**Components:**
- `Blackboard` — async-aware key/value store with subscription-driven activation
- `Specialist` — protocol declaring `name`, `watches`, `priority`, `needs_model`,
  `tick_seconds`, `run`, `should_activate`
- `Dispatcher` — `asyncio.PriorityQueue` + worker pool; `asyncio.Semaphore` for
  model resource gating
- `Runtime` — wires everything; lifecycle, exit conditions
- `simulated.LatencyProfile` / `PacingProfile` — configurable simulated latency
  and chunked-output pacing for mock specialists

**StateStore + ContextService** (`orchestrator/state.py`): adds a layer above the
raw blackboard.
- `StateStore` — component-namespaced writes under `component:<owner>:<key>`
- `ContextService` — provider-backed reads at `context:<key>`, with
  `passthrough`, `default_if_unset`, `prefer_highest_confidence`, `composite`
  primitives. Reactive — provider recomputes on changes to declared deps.
- `SpecialistView` — what a specialist sees: read via context URNs, write to
  own namespace.

**Demos** (`orchestrator/demos/`):
- `chatter` — five concurrent specialists exercising tick / state-change /
  cascade / priority / semaphore-gated patterns
- `streaming` — long-running cogitator producing chunked output, interrupted
  mid-flow; speaker drains queue around the interruption
- `streaming_v2` — same scenario migrated onto StateStore + ContextService;
  composite provider merges sources from four components into the speaker's
  outgoing queue

### Phase 2 POC exit criteria

POC validates **two parallel tracks** before committing to training specialists:

| Track | Evidence | Exit criteria |
|---|---|---|
| **Composability** | Orchestration substrate supports useful component activation patterns | All 4 cells of (activation × communication) matrix working; ≥1 cell demonstrates contextual rate/activation modulation |
| **Specialist suitability** | Prompted specialists produce acceptable-quality results; schema-driven inference does real work | End-to-end output of acceptable quality; audit trail shows schema-driven reasoning drives the output — not merely scaffolding |

Acceptable-quality threshold deferred until post-build. Setting metrics pre-build
risks anchoring on wrong signals; failure modes emerge in practice. POC is explicitly
iterative — multiple cycles expected.

---

## Evaluation framework (Phase 2+)

A design sketch for component-level and end-to-end evaluation is documented
in `design/eval-harness.md`. Not yet implemented. Covers failure-mode taxonomy
(HALLUC, OMIT, RECOVER, STATE, AMBIG, TEMPORAL, UPDATE, IRREVERS), component-level
harnesses for each region (Thalamus, Hippocampus, Prefrontal, Broca), pipeline-level
end-to-end cases, and multi-turn memory evaluation. Benchmark research sources
include HotpotQA, LoCoMo, LongMemEval, SmartPlay, τ-Bench, SLOTBench, and AgentBench.

---

## Cognitive regions — Phase 1 scope

Phase 1 implements a linear pipeline with four regions only:

| Region | Tier | Type | Phase 1 role | Model |
|---|---|---|---|---|
| Thalamus | 1 | Encoder classifier | Classifies input type, determines routing | sentence-transformers/all-MiniLM-L6-v2 |
| Prefrontal | 2 | Generative (prompted) | Decomposes goal, produces task plan | phi3.5 (POC) / Mistral-7B (prod) |
| Hippocampus | 2 | Retrieval | Retrieves relevant memory, injects context | sentence-transformers/all-MiniLM-L6-v2 |
| Broca | 3 | Generative (prompted) | Produces final response from blackboard | phi3.5 (POC) / Mistral-7B (prod) |

Remaining regions (Amygdala, Wernicke, Basal Ganglia, Conscience) are
deferred to Phase 2. The Helm chart schema must accommodate them without
structural change.

**Implementation status:**
- M0 done: Phase 1 pipeline runs locally against docker-compose services
- M1 done: audit subsystem in `src/ponder/audit/` (events, emitter, service, CLI)
- M1.1 done: orchestrator substrate in `src/ponder/orchestrator/` (blackboard,
  dispatcher, specialist, runtime, simulated) with concurrent-activation demos
  validating composability matrix cells
- M1.2 done: diagnostic panel in `src/ponder/diagnostics/` (FastAPI server,
  state/context/event SSE streams, snapshot, input/interrupt endpoints, browser UI)

---

## Phase 1 execution plan

Status key: `[ ]` not started · `[~]` in progress · `[x]` done

### Step 1 — Infrastructure bootstrap `[~]`

```bash
export LAMBDA_API_KEY=...
export LAMBDA_SSH_KEY_NAME=ponder-dev
./provision.sh launch
ansible-playbook bootstrap.yml -i <ip>, --private-key ~/.ssh/lambda_key
```

- Requires: Lambda Labs API key, SSH key pair registered in Lambda console
- `provision.sh` handles: instance type `gpu_1x_a10`, region selection, instance naming
- `bootstrap.yml` handles: k3s install, NVIDIA device plugin, kubeconfig fetch + server address patch
- **Validate:** `export KUBECONFIG=~/.kube/ponder-config && kubectl get nodes` — node shows `Ready`, `nvidia.com/gpu: 1` in capacity

### Step 2 — Cluster foundation `[ ]`

```bash
kubectl apply -f manifests/redis.yaml
kubectl apply -f manifests/vector-store.yaml
```

- Redis: single-replica, append-only persistence, 2GB limit. Serves both blackboard (Hash) and message bus (Streams).
- Qdrant: single-replica, emptyDir storage (ephemeral — see open question on persistence). Port 6333 HTTP, 6334 gRPC.
- **Validate:**
  ```bash
  kubectl exec -n ponder deploy/redis -- redis-cli ping   # → PONG
  curl http://<node-ip>:6333/healthz                      # → {"title":"qdrant - ..."}
  ```
  Note: expose Qdrant via `kubectl port-forward` if no ingress configured.

### Step 3 — Helm chart + container image `[ ]`

Build and push the ponder container, then install the chart:

```bash
# Build
cd src/ponder && docker build -t ghcr.io/<org>/ponder:latest .
docker push ghcr.io/<org>/ponder:latest

# Install
helm install unit-alpha charts/cognitive-unit \
  --namespace ponder \
  --set unit.image.repository=ghcr.io/<org>/ponder \
  --set unit.image.tag=latest
```

- Needs a `Dockerfile` in `src/ponder/` (not yet written — next artifact)
- vLLM model server pod will pull Mistral 7B on first start; this takes several minutes and requires HuggingFace token if gated
- **Validate:** `kubectl get pods -n ponder` — orchestrator and model-server pods reach `Running`; model-server readiness probe passes (`/health` returns 200)

### Step 4 — Region implementations `[x]`

Implemented. Artifacts:

| File | Status |
|---|---|
| `ponder/blackboard.py` | done |
| `ponder/config.py` | done |
| `ponder/model_client.py` | done |
| `ponder/regions/thalamus.py` | done |
| `ponder/regions/hippocampus.py` | done |
| `ponder/regions/prefrontal.py` | done |
| `ponder/regions/broca.py` | done |

**Not yet written:**
- `Dockerfile` for the ponder container
- `b2/` sync scripts for model weight management

### Step 5 — LangGraph wiring `[x]`

Implemented in `ponder/graph/pipeline.py`. Graph: `Thalamus → Hippocampus → Prefrontal → Broca`.

Order rationale: Hippocampus before Prefrontal so retrieved context is available when Prefrontal plans. In Phase 2, both run concurrently; the ordering only matters for Phase 1's sequential execution.

**Validate locally** (requires running Redis, Qdrant, and model server):
```bash
cd src/ponder && pip install -e ".[dev]"
ponder "What is the capital of France?"
```

**Validate in cluster:**
```bash
kubectl exec -n ponder deploy/unit-alpha-orchestrator -- \
  ponder "What is the capital of France?"
```

### Step 6 — Prompt templates `[x]`

Implemented. Iterate against live system — these are the first things to tune once end-to-end is working.

- `prompts/prefrontal_v1.txt` — structured plan format (GOAL / MUST-CONVEY / SUBTASKS)
- `prompts/broca_v1.txt` — voice framing ("express a mind, not follow a script")

Prompt iteration process: run `ponder "<input>"` with `PONDER_PROMPTS_DIR` pointing to a local dir; edit templates; rerun. No redeployment needed since templates are read at runtime.

---

## Region interface contracts

Each region is a pure function `(BlackboardState) → dict`. Nodes write only the fields they own — they must not modify fields owned by other regions.

| Region | Reads | Writes | Side effects |
|---|---|---|---|
| Thalamus | `raw_input` | `input_type` | none |
| Hippocampus | `raw_input` | `retrieved_memories` | none (read-only against Qdrant) |
| Prefrontal | `raw_input`, `input_type`, `retrieved_memories`, `operator_context`, `rules_of_engagement` | `task_plan` | none |
| Broca | `input_type`, `retrieved_memories`, `task_plan`, `operator_context`, `rules_of_engagement`, `urgency_score` | `response_draft`, `goal_achieved` | none |

`store_memory()` (Hippocampus) is called externally by `__main__.py` after a turn completes — it is not a node side effect.

`input_type` values: `question` | `command` | `statement` | `greeting` | `clarification`

### Configuration surface

All config is injected via environment variables. No hardcoded endpoints anywhere in the package. See README for the full table. In-cluster, the Helm ConfigMap sets all variables automatically from `values.yaml`.

### Pending artifacts

| Artifact | Needed for |
|---|---|
| `src/ponder/Dockerfile` | Step 3 (container image) |
| `b2/push_weights.sh` | B2 weight management |
| `b2/pull_weights.sh` | B2 weight management |

---

## Artifact manifest (full project)

```
provision.sh                              # [x] Lambda Labs instance launch
bootstrap.yml                             # [x] Ansible: k3s + NVIDIA plugin
charts/cognitive-unit/                    # [x] Helm chart
charts/cognitive-unit/values.yaml         # [x] Region config: all 8 regions, enabled flags
charts/cognitive-unit/templates/          # [x] ConfigMap, Deployments, Service
manifests/redis.yaml                      # [x] Redis: Streams + Hash
manifests/vector-store.yaml               # [x] Qdrant
src/ponder/blackboard.py           # [x] BlackboardState TypedDict
src/ponder/config.py               # [x] Config, env-driven
src/ponder/model_client.py         # [x] generate() + generate_streaming() over vLLM/Ollama
src/ponder/regions/thalamus.py     # [x] Input classifier
src/ponder/regions/hippocampus.py  # [x] Memory retrieval + store_memory()
src/ponder/regions/prefrontal.py   # [x] Goal decomposition
src/ponder/regions/broca.py        # [x] Response generation
src/ponder/graph/pipeline.py       # [x] LangGraph Phase 1 linear graph
src/ponder/__main__.py             # [x] CLI entry
src/ponder/prompts/prefrontal_v1.txt      # [x] Prefrontal system prompt
src/ponder/prompts/broca_v1.txt           # [x] Broca system prompt
src/ponder/audit/events.py         # [x] AuditEvent + EventType (OTel-aligned)
src/ponder/audit/emitter.py        # [x] Redis Stream publisher, resilient
src/ponder/audit/service.py        # [x] Resource-oriented read API (events, traces, tail)
src/ponder/audit/cli.py            # [x] `ponder-audit` CLI viewer
src/ponder/orchestrator/blackboard.py    # [x] Async-aware key/value store + subscriptions
src/ponder/orchestrator/specialist.py    # [x] Specialist protocol
src/ponder/orchestrator/dispatcher.py    # [x] Priority queue + worker pool + model semaphore
src/ponder/orchestrator/runtime.py       # [x] Lifecycle + state-change reaction + tick loops
src/ponder/orchestrator/simulated.py     # [x] LatencyProfile / PacingProfile
src/ponder/orchestrator/state.py         # [x] StateStore + ContextService + provider primitives
src/ponder/diagnostics/server.py         # [x] FastAPI app (snapshot, events, SSE, input)
src/ponder/diagnostics/__main__.py       # [x] `ponder-diagnostics` CLI entry (--runtime flag)
src/ponder/diagnostics/panel.html        # [x] Browser UI (HTML + CSS + vanilla JS)
src/ponder/diagnostics/runtime_factory.py     # [x] Panel-friendly runtime
src/ponder/diagnostics/persuasion_runtime.py  # [x] Persuasion demo runtime (real-LLM speaker)
src/ponder/tests/                         # [x] Unit tests (138 total) — regions, pipeline, audit, orchestrator, state, simulated, diagnostics
src/ponder/Dockerfile                     # [ ] Container image (needed for Step 3)
src/ponder/broca/stream_consumer.py# [ ] Redis Stream consumer (Phase 2)
src/ponder/evaluator/goal.py       # [ ] Goal condition evaluator (Phase 3)
b2/push_weights.sh                        # [ ] B2 weight upload
b2/pull_weights.sh                        # [ ] B2 weight download
CONTEXT.md                                # this file
synthetic-mind-spec.docx                  # full system specification
```

---

## Design practices

**Drift-check process:** `CONTEXT.md` is the canonical working source of truth.
`design/` files (interview.md, concepts.md, data-structures.md, etc.) evolve
freely during exploration. Periodically (at pause points), a drift-check review
reconciles CONTEXT.md with design/ decisions, folding mature design into the
canonical doc. Drift-check is performed by a lower-cost model to keep overhead
minimal. See `MEMORY.md` for cadence notes.

---

## Open questions (unresolved, will affect implementation)

- **Goal evaluator** — which model, what signal, binary or scored?
- **Broca interrupt semantics** — restart, append, or insert on late chunk arrival? (Phase 2)
- **Hippocampus vector store persistence** — Qdrant in-cluster is lost on instance termination; B2-backed snapshot or external instance needed for durable memory
- **Conscience threshold calibration** — how does it know what counts as a violation? (Phase 2)
- **Inter-unit orchestration topology** — same LangGraph + Redis pattern or different mechanism at society layer? (Phase 4)
- **Schema recognizer architecture** — embedding similarity vs. graph-homomorphism pattern matching (Phase 2)
- **Multi-schema arbitration policy** — when multiple schemas apply, commit to one or hold multiple in tension? (Phase 2)
