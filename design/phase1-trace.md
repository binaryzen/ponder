# Phase 1 — Runtime trace of a single turn

What actually happens when `python -m ponder "What is the capital of France?"`
is executed against the local POC stack. Used as the implementation guide for
M1 (audit emitter wiring) — every numbered step below is a candidate emit
point.

Boundary-crossings called out with **→** markers.

---

## Phase A — Process startup (single Python process)

1. **PowerShell** spawns the Python 3.13 interpreter with `-m ponder`. Python
   resolves the module to `ponder/__main__.py` inside the installed package.
2. Import cascade fires (all in-process, blocking):
   - `ponder.__main__` → `ponder.blackboard` (TypedDict definitions)
   - → `ponder.graph.pipeline` → `ponder.regions.{thalamus,hippocampus,prefrontal,broca}`
   - regions → `sentence_transformers` (drags in `torch` — slow, ~1–2s) and
     `qdrant_client` and `httpx`
3. No model weights load yet — region modules use lazy `_get_model()` /
   `_get_client()` patterns. Module-level `_model` and `_client` globals are
   still `None`.

## Phase B — main() and graph compile (in-process)

4. `main()` joins `sys.argv[1:]` → `"What is the capital of France?"`.
   Calls `run(raw_input)`.
5. `run()` calls `initial_state(raw_input)` → constructs a `BlackboardState`
   dict in memory. *This is the entire blackboard for Phase 1 — no Redis
   touch yet, despite what CONTEXT.md says about Redis backing it. Redis is
   provisioned but unused in Phase 1.*
6. `_get_pipeline()` (singleton) calls `build_pipeline()`:
   - `StateGraph(BlackboardState)` constructs an empty graph
   - Adds 4 nodes + 5 edges (`START→thalamus→hippocampus→prefrontal→broca→END`)
   - `.compile()` produces a `Pregel` runner (LangGraph's internal execution
     engine)
7. `pipeline.invoke(state)` — LangGraph walks the graph from START. All nodes
   run sequentially in the main thread; LangGraph adds no concurrency in
   this graph topology.

## Phase C — Per-node execution

### `thalamus_node(state)`

8. `_get_model()` — first call. Constructs
   `SentenceTransformer("sentence-transformers/all-MiniLM-L6-v2")`. Reads
   weights from `~/.cache/huggingface/` if cached, otherwise
   **→ HTTPS** to `huggingface.co`.
9. `_get_prototypes()` — first call. Encodes 25 short sample strings (5 per
   class, hard-coded in `_LABEL_EXAMPLES`) through the encoder. All
   in-process; PyTorch may use several CPU threads internally for matrix
   multiplication, but the call is synchronous. Result: a (5, 384) numpy
   array.
10. `model.encode(["What is the capital of France?"])` → (1, 384) numpy
    array. CPU PyTorch.
11. Cosine similarity via numpy → argmax → label `"question"`.
12. Returns `{"input_type": "question"}`. LangGraph merges into state.

### `hippocampus_node(state)`

13. `_get_model()` — first call **for this module**. Note: there's a second
    `SentenceTransformer` instance now, separate from Thalamus's. Weights
    load from disk cache (no network), but the model is held twice in RAM.
    Known inefficiency; not critical in Phase 1.
14. `_get_client()` — first call. Constructs
    `QdrantClient(url="http://localhost:6333")`. The constructor performs
    a version check **→ HTTP GET** to the Qdrant container.
15. `_ensure_collection()` calls `client.get_collections()` **→ HTTP GET**.
    Result: collection list (after the volume reset, empty).
16. Collection `"hippocampus"` doesn't exist → `client.create_collection(...)`
    **→ HTTP PUT**. Qdrant allocates the collection on disk inside the
    container, sized for 384-dim COSINE vectors.
17. `model.encode([raw_input])` → query vector (in-process, CPU PyTorch).
18. `client.query_points(collection, query=vec, limit=5)` **→ HTTP POST**
    to `/collections/hippocampus/points/query`. Qdrant runs HNSW search
    internally; collection is empty → returns `points=[]`.
19. Returns `{"retrieved_memories": ""}`.

### `prefrontal_node(state)`

20. `_get_template()` — first call. Reads `prompts/prefrontal_v1.txt` from
    disk synchronously.
21. `template.format(input_type=..., retrieved_memories="None", ...)`
    produces the rendered system prompt string (in-process).
22. `generate(system_prompt, user_prompt)` builds an OpenAI-compatible
    chat-completions payload, then
    `httpx.post("http://localhost:11434/v1/chat/completions", json=payload, timeout=120)`
    **→ HTTP POST** to the **Ollama** process.
23. Ollama: receives the request, loads `phi3.5` weights from disk into RAM
    on first invocation (~4 GB resident, ~10–30s), runs autoregressive
    inference on CPU, streams tokens internally, batches them into one
    response body, returns 200 OK with JSON.
24. httpx blocks the calling thread until the full response arrives.
    Returns `{"task_plan": "<plan prose>"}`.

### `broca_node(state)`

25. Same pattern as Prefrontal: read `broca_v1.txt`, format with full state
    (including the plan from Prefrontal), `generate()` **→ HTTP POST** to
    Ollama. Phi-3.5 is already loaded in Ollama's memory now, so request
    returns much faster.
26. Returns `{"response_draft": "<the answer>", "goal_achieved": True}`.

LangGraph reaches END; `pipeline.invoke()` returns the final state dict.

## Phase D — Post-pipeline

27. `run()` calls `store_memory(text="Q: ...\nA: ...", metadata={"input_type": "question"})`.
28. `model.encode([text])` → 384-dim vector (in-process).
29. `client.upsert(collection, points=[PointStruct(id=uuid4(), vector=..., payload=...)])`
    **→ HTTP POST** to Qdrant `/collections/hippocampus/points`. Qdrant
    indexes the new point.
30. `main()` prints `result["response_draft"]` to stdout. Process exits.

---

## Boundary-crossing summary

| Step               | From                     | To                              | Protocol | Why                        |
| ------------------ | ------------------------ | ------------------------------- | -------- | -------------------------- |
| 8 (first run only) | Python                   | huggingface.co                  | HTTPS    | Encoder weights download   |
| 14                 | Python (`qdrant_client`) | Qdrant container (Rust process) | HTTP     | Client version check       |
| 15, 16             | Python                   | Qdrant                          | HTTP     | Collection list / create   |
| 18                 | Python                   | Qdrant                          | HTTP     | Vector search              |
| 22                 | Python (`httpx`)         | Ollama (Go process)             | HTTP     | LLM inference (Prefrontal) |
| 25                 | Python                   | Ollama                          | HTTP     | LLM inference (Broca)      |
| 29                 | Python                   | Qdrant                          | HTTP     | Memory upsert              |

All HTTP calls are synchronous and blocking. No threads spawned in Python
beyond what PyTorch and httpx use internally. The Python process owns one
logical thread of execution from `main()` to print.

Container-to-host boundary is bridged by Docker Desktop's WSL2 backend —
Linux kernel inside WSL2 runs Qdrant and Redis; Windows host networking
forwards `localhost:6333` and `localhost:6379` into the WSL2 namespace.
Ollama runs natively on Windows, no container; HTTP server listens on
`localhost:11434` directly.

## OSS components and their roles

| Component | Language | Role in this run |
|---|---|---|
| **CPython 3.13** | C | Runs the orchestrator process |
| **LangGraph** | Python | Compiles and walks the node graph; manages state merging between nodes |
| **PyTorch** | C++/CUDA (CPU here) | Neural-net forward passes for the encoder |
| **sentence-transformers** | Python | Wraps HuggingFace Transformers; produces 384-dim embeddings |
| **HuggingFace Transformers / Hub** | Python | Model loading, hub fetch on first run |
| **httpx** | Python | HTTP client for both `qdrant_client` and `model_client.py` |
| **Pydantic v2** | Rust core + Python | Config validation in `ponder.config` |
| **qdrant-client** | Python | HTTP/gRPC wrapper around Qdrant's API |
| **Qdrant** | Rust | Vector database; HNSW search, collection storage |
| **Ollama** | Go | LLM inference server; loads quantized GGUF weights, exposes OpenAI-compat API |
| **llama.cpp** (vendored in Ollama) | C++ | Actual quantized-LLM inference engine inside Ollama |
| **Phi-3.5-mini-instruct** | (model weights) | The 3.8B-parameter LLM that produced both plan and response |
| **MiniLM-L6-v2** | (model weights) | The encoder that classified intent and embedded the query |
| **Docker Engine + Docker Desktop** | Go + Electron | Runs the Qdrant and Redis containers via WSL2 |
| **WSL2 (Linux kernel)** | C | Hosts the container processes |
| **Redis** | C | **Provisioned but not invoked.** Listens on 6379 idle. M1+ work. |

---

## M1 emit-point map

The numbered steps that should produce audit events when M1 wires the
emitter:

- **Step 4** (run start) → `pipeline` event, `turn_start`
- **Step 7** (graph invocation start) → could be implicit; covered by per-node events
- **Steps 12, 19, 24, 26** (region completions) → `pipeline` event, `region_complete`
  with payload describing what was written and timing
- **Step 29** (memory upsert) → `pipeline` event, `memory_store`
- **Step 30** (return) → `pipeline` event, `turn_end`

Phase 2+ regions will additionally emit `recognition`, `selection`,
`slot_fill`, `behavior_anticipation`, `verdict` events at their own
internal points.
