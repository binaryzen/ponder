# Ponder Eval Harness — Sketch

Design sketch for a component-level + end-to-end evaluation framework. Not yet implemented. Written to capture benchmark research before moving on; revisit when the POC is mature enough to need systematic evaluation.

Benchmark research source: conversation 2026-05-07, summarized in `memory/`.

---

## Framing

Benchmarks are a starting point, not a north star. The harness should be designed around Ponder's actual failure modes and architecture, borrowing *structure* from existing benchmarks rather than optimizing for their scores.

Two levels of evaluation:
- **Component-level**: isolate one region (Thalamus, Hippocampus, Prefrontal, Broca) with mocked neighbors
- **Pipeline-level**: end-to-end turns; compare actual blackboard state to expected state after turn completes

Correctness signal: where possible, compare *state* after action (blackboard values, retrieved memory sets, plan structure) rather than free-text output similarity. τ-Bench's approach — annotate expected goal state, diff against actual — is the right model.

---

## Failure mode axes

Every test case should be tagged with the failure mode(s) it exercises. From cross-benchmark consensus:

| Code | Failure mode | Description |
|---|---|---|
| `HALLUC` | Hallucination | Inventing facts, parameters, or structure not in source |
| `OMIT` | Omission | Silently ignoring required fields or instructions |
| `RECOVER` | Error recovery | Failing to replan after tool failure or unexpected state |
| `STATE` | State tracking | Losing track of what happened in earlier turns |
| `AMBIG` | Ambiguity resolution | Making poor choices when instructions conflict |
| `TEMPORAL` | Temporal reasoning | Failing to order or relate events across time |
| `UPDATE` | Knowledge update | Not resolving contradiction when new info supersedes old |
| `IRREVERS` | Irreversibility | Taking destructive/non-undoable actions without recognizing them |

---

## Component-level harnesses

### Thalamus

**What to evaluate**: Input classification accuracy across the five types (`question`, `command`, `statement`, `greeting`, `clarification`) plus graceful degradation on ambiguous or adversarial inputs.

**Test case structure**:
```python
ThalamusCase(
    raw_input="...",
    expected_type="question",           # or None if adversarial
    failure_modes=["AMBIG"],
    notes="...",
)
```

**Case categories to cover**:
- Clean single-type inputs (baseline accuracy)
- Ambiguous inputs that could be classified multiple ways
- Inputs with classification-irrelevant context noise
- Multi-sentence inputs where type is only determined by last sentence
- Non-English or code-mixed inputs (robustness)

**Sources to borrow from**: GAIA Level 1 input variety, MIND2WEB (intent extraction from UI text)

---

### Hippocampus

**What to evaluate**: Two distinct properties, tested separately:

1. **Retrieval accuracy** — does the right memory come back? (passive recall)
2. **Decision relevance** — does the retrieved memory change the downstream plan? (active use)

Most existing benchmarks test only (1). MemoryArena showed a 30–40% gap between the two. Hippocampus should be tested on both.

**Test case structure**:
```python
HippocampusCase(
    raw_input="...",
    seeded_memories=[Memory(text="...", tags=[...]), ...],
    expected_retrieved_ids=["m1", "m3"],            # retrieval accuracy
    expected_plan_delta="...",                       # if plugged into Prefrontal: how plan changes
    failure_modes=["STATE", "TEMPORAL"],
    notes="...",
)
```

**Case categories to cover**:
- Single relevant memory among noise
- Multi-hop: answer requires combining two memories
- Temporal ordering: memory A before memory B; question requires recognizing sequence
- Contradiction: two memories conflict; newer one should win (`UPDATE`)
- No relevant memory: agent should not hallucinate a retrieval (`HALLUC`)
- Memory referenced by pronoun or implicit relation, not explicit text match

**Sources to borrow from**: HotpotQA (multi-hop structure), LongMemEval (5 competencies), LoCoMo (session-spanning)

---

### Prefrontal

**What to evaluate**: Plan quality given input + memories + context. Not the LLM output verbatim — the *structure* of the produced plan: are steps present, are dependencies ordered, are constraints respected?

**Test case structure**:
```python
PrefrontalCase(
    raw_input="...",
    input_type="command",
    retrieved_memories=[...],
    operator_context="...",
    rules_of_engagement="...",
    expected_steps_contain=["step A", "step B"],    # order-sensitive where relevant
    expected_steps_absent=["step X"],               # should not hallucinate steps
    failure_modes=["HALLUC", "OMIT", "RECOVER"],
    notes="...",
)
```

**Case categories to cover**:
- Simple single-step plans (baseline)
- Dependency-ordered multi-step plans (SmartPlay pattern: need A → B → C)
- Plans requiring constraint adherence from `rules_of_engagement` (τ-Bench pattern)
- Blocking dependencies — step B can't proceed until step A confirms; plan should express this
- Recovery case: first plan fails; re-plan with updated state
- Goal ambiguity: two valid plans exist; evaluate that agent commits to one coherently

**Sources to borrow from**: SmartPlay (dependency graphs), τ-Bench (policy constraints), LMRL-Gym (multi-turn strategy)

---

### Broca

**What to evaluate**: Response quality given full blackboard state. Two dimensions:

1. **Fidelity** — does the response reflect what Prefrontal planned and what Hippocampus retrieved?
2. **Schema compliance** — if structured output is expected, does it conform? (post-schema-inference work)

**Test case structure**:
```python
BrocaCase(
    full_state=BlackboardState(...),
    expected_response_contains=["..."],
    expected_response_absent=["hallucinated fact"],
    expected_schema_output={"field": "value"},      # for structured output cases
    failure_modes=["HALLUC", "OMIT"],
    notes="...",
)
```

**Case categories to cover**:
- Response accurately reflects plan (fidelity check)
- Response does not introduce facts absent from retrieved memories (`HALLUC`)
- Response handles empty retrieval gracefully (doesn't invent memories)
- Structured output: given schema + filled slots, emit valid JSON
- Long plan → concise coherent response (compression without omission)

**Sources to borrow from**: SLOTBench (schema compliance + content fidelity tracked separately), τ-Bench (DB state diff as correctness signal)

---

## Pipeline-level harness

End-to-end turns. Input goes in; blackboard state after the turn is diffed against expected state.

**Test case structure**:
```python
PipelineCase(
    raw_input="...",
    seeded_memories=[...],
    expected_state_contains={
        "input_type": "question",
        "response_draft": CONTAINS("Paris"),
    },
    expected_state_absent=["hallucinated_key"],
    failure_modes=["STATE", "HALLUC"],
    turn_sequence=[...],   # optional: multi-turn cases
    notes="...",
)
```

**Case categories**:
- Single-turn golden path (all four regions produce expected output)
- Multi-turn: context from turn N visible in turn N+2
- State reset between turns: previous turn's plan should not bleed into new one
- Error injection: one region returns malformed output; downstream regions handle gracefully
- Multi-turn contradiction: user corrects agent in turn 2; turn 3 should reflect correction (`UPDATE`)

---

## Multi-turn memory cases

Separate category because they span turns and require orchestrator involvement.

**Pattern** (borrowed from LoCoMo / MemoryArena):
- Seed N turns of conversation
- Ask a question that requires synthesizing across turns (multi-hop)
- Ask a question about temporal ordering
- Introduce contradicting information; verify next response resolves correctly
- Ask about something never mentioned; verify abstention (no hallucinated memory)

The gap between retrieval accuracy and decision-relevant use is specifically tested by: seeding a memory, running a turn where it *should* change the plan, and asserting the plan changed (not just that the memory was retrieved).

---

## Harness runner sketch

```python
# eval/runner.py (not yet implemented)

class EvalResult:
    case_id: str
    passed: bool
    failure_modes_triggered: list[str]
    notes: str
    actual_state: dict


class EvalHarness:
    def run_thalamus_suite(self, cases: list[ThalamusCase]) -> list[EvalResult]: ...
    def run_hippocampus_suite(self, cases: list[HippocampusCase]) -> list[EvalResult]: ...
    def run_prefrontal_suite(self, cases: list[PrefrontalCase]) -> list[EvalResult]: ...
    def run_broca_suite(self, cases: list[BrocaCase]) -> list[EvalResult]: ...
    def run_pipeline_suite(self, cases: list[PipelineCase]) -> list[EvalResult]: ...


def summarize(results: list[EvalResult]) -> dict:
    """Per failure-mode pass rate + overall. Surfaces which failure modes are systemic."""
    ...
```

Results summarized per failure-mode axis, not just overall pass rate. If `HALLUC` fails 80% of the time but `TEMPORAL` fails 20%, that's actionable signal.

---

## What to borrow from open-source benchmarks

When ready to populate actual test cases:

| Benchmark | What to extract | Location |
|---|---|---|
| HotpotQA | Multi-hop question structures; supporting-fact annotations → memory seed patterns | https://hotpotqa.github.io |
| LoCoMo | Session-spanning dialogue cases; temporal ordering questions | https://snap-research.github.io/locomo |
| LongMemEval | 5-competency structure: extraction, multi-session, temporal, update, abstention | (paper + HuggingFace) |
| SmartPlay | Dependency-graph task structures for Prefrontal cases | arXiv 2310.01557 |
| τ-Bench | Policy-constrained planning; goal-state diff evaluation methodology | github.com/sierra-research/tau2-bench |
| SLOTBench | Schema compliance + content fidelity as separate metrics | EMNLP 2025 |
| AgentBench | Cross-domain task taxonomy (OS, DB, KG, etc.) for coverage mapping | github.com/THUDM/AgentBench |

Do not directly adopt benchmark test cases — use them as structural templates. Their exact tasks may be gamed or distribution-matched by training data.

---

## Open questions (deferred)

- **Evaluation judge**: For Prefrontal and Broca outputs, LLM-as-judge (Agent-as-a-Judge from Mind2Web 2) vs. structured assertion. Structured assertions are cheaper and more reproducible; judge needed only for open-ended response quality.
- **Adversarial generation**: Whether to auto-generate adversarial cases from a separate model (tests `HALLUC` and `AMBIG` at scale) or hand-curate.
- **Regression harness integration**: Whether eval cases live alongside the existing 138 unit tests or in a separate `eval/` tree (probably separate — different latency, external deps).
- **Schema-inference eval**: Once schema recognition and slot completion are implemented, extend Prefrontal and Broca cases to include schema selection + slot fidelity as first-class metrics.
