# Technical Concept Mappings

Each entry maps a user intuition to ML methodology, identifies relevant
research, and notes where the user's framing diverges from or extends the
standard.

---

## Concept 1 — Schema-constrained structured prediction

**User intuition.** A specialized component takes context and produces
structured output (named categories with scalar or nominal values), where the
output space is small and well-defined.

**ML mapping.** This is structured prediction. Two architectural
specializations apply:

- **Multi-label classification** — encoder + N classification heads. Cheapest,
  fastest, smallest. Sufficient for the risk categorizer alone (each category
  is an independent classification problem with a small label set). No
  generation required.
- **Constrained generation** — small generative model with output space
  restricted via training and/or decoding. Required when outputs include
  variable bindings (e.g., `${QUESTION_001}`).

**Relevant work.**

- Outlines, lm-format-enforcer, OpenAI Structured Outputs (decoding-time constraints)
- JSON-mode fine-tuning (training-time constraint internalization)
- Function-calling models — Gorilla, ToolLLM
- Slot-filling literature in dialogue systems

**Architectural implication for Ponder.** The risk categorizer can be a tiny
encoder-based classifier. The goal categorizer must be generative. These are
two different artifact types under one conceptual umbrella, and treating them
identically would over-spend on the simpler one.

---

## Concept 2 — Symbolic abstraction in training data

**User intuition.** Use opaque tokens (`A`, `B`, `C`, `${QUESTION_001}`) in
training data so the model learns the form of reasoning, not the content.

**ML mapping.** Symbol Tuning territory.

- **Wei et al., 2023, "Symbol tuning improves in-context learning in language
  models."** Empirical finding: replacing natural-language labels with
  arbitrary symbols during fine-tuning *improves* in-context learning across
  many tasks. The model can no longer rely on label-name semantics and is
  forced to attend to structural patterns.

**Adjacent research lines.**

- Systematic generalization in neural networks — Lake & Baroni; Marcus;
  Bahdanau et al.
- Variable binding in transformers — Tafjord, Sabharwal et al.
- Webb, Holyoak, Lu — "Emergent analogical reasoning in large language models"
- Compositional generalization benchmarks (SCAN, COGS, CFQ)

**Caveat / tension.** Symbol Tuning found *short* arbitrary symbols (e.g.,
`foo`, `bar`) outperformed verbose multi-token labels. The user's stated
preference for verbose multi-token labels is in tension with this finding.
Possible reconciliations:

- The verbosity intuition is calibrated for a downstream concern (parsing,
  human readability) rather than training-signal quality.
- The verbosity is doing additional work via training-signal density
  (multi-token labels = more loss-per-example).
- The intuition may need revision in light of the empirical evidence.

To be resolved when Q3 is answered.

---

## Concept 3 — Information compression for proportional structural attention

**User intuition.** Replacing a verbose semantic referent with an opaque token
reduces the dilution of structural tokens during the forward pass. Structural
tokens (`if`, `then`, comparison operators, schema field names) get more
proportional weight in the model's computation; content tokens that would
otherwise activate irrelevant pathways are squeezed out.

**ML mapping.** Speculative — no direct paper found that frames the
hypothesis this way. Adjacent ideas:

- **Information bottleneck principle** (Tishby et al.) — squeezing intermediate
  representations forces them to retain only task-relevant information,
  improving generalization. Applies to representation learning, not directly
  to input/output token selection, but the intuition is related.
- **Attention dilution / capacity arguments** — implicit in much sparse
  attention work; long contexts diffuse attention. Symbolic compression is a
  form of explicit pre-attention concentration.
- **Curriculum and data-quality work** — Phi-series papers (Microsoft) argue
  that small, high-quality, structured training data outperforms larger
  noisier data. This is related but doesn't isolate the "opaque-symbol"
  mechanism.

**Status.** Candidate testable claim. Hypothesis:

> Holding model architecture and training compute constant, a model trained
> on symbolically-compressed examples generalizes better on structural
> reasoning tasks than a model trained on naturalistic prose expressing the
> same reasoning.

**Action items.**

- Targeted literature search: does anyone test this directly? Possibly under
  "abstract pattern learning," "rule-based generalization," or in the
  algorithmic-reasoning subfield (CLRS benchmark, etc.).
- If novel, design a clean controlled experiment. Two corpora differing only
  in symbolic compression of referents; train identical models; evaluate on
  held-out structural-reasoning tasks. Would feed `assumptions.md`.

---

## Concept 4 — Controlled internal vocabulary as system contract

**User intuition.** Bias the model toward a curated set of relationships,
verbs, and adjectives. Use this vocabulary as the wire format between
cognitive components. Free-form natural language is reserved for the I/O
boundary (user input and Broca's output). The vocabulary is not just a
training-data property — it is a system-level engineering primitive.

**Engineering claims:**

1. **Cacheability.** Bounded output spaces hash to a finite set, so identical
   inputs produce identical outputs and component results can be memoized.
2. **Reduced non-determinism.** Constrained vocabulary collapses the space of
   semantically equivalent expressions, sharply reducing sampling variance
   for the same input.
3. **Modular interfaces.** Inter-region communication becomes type-checked
   and schema-validated. "Less wrinkly data shapes."

**ML / CS mapping.** This is the methodological core of neurosymbolic AI:
neural components communicating via symbolic interfaces. Specific lineages:

- **Controlled natural languages.** Attempto Controlled English (ACE) is the
  closest single analog — a restricted English subset designed to be
  unambiguous and machine-parseable.
- **Frame semantics.** Fillmore's frames; FrameNet. Predicates with named
  slots; vocabulary is itself structured.
- **Knowledge representation.** RDF, OWL, conceptual graphs, description
  logics. Decades of work on the expressiveness/tractability tradeoff.
- **Type systems in programming languages.** Rigid module contracts; the
  direct engineering analog.
- **Wire protocols.** gRPC, protobuf, Thrift. The networking analog: agreed
  schema between processes, deterministic serialization.
- **Neurosymbolic AI** as a research program — Garcez & Lamb; the broader
  literature on combining sub-symbolic and symbolic computation.

**Historical caution.** Hand-designed vocabularies of any breadth are
expensive to build and brittle to maintain. CYC enumerated common-sense
knowledge in formal logic and partly failed because the vocabulary kept
expanding to handle edge cases. WordNet and FrameNet are useful but
incomplete. Empirical lesson: the *methodology for constructing the
vocabulary* is as important as the vocabulary itself, and probably more so.

**Tensions to track.**

- LLMs are stochastic. "Determinism" requires fixing temperature, decoding
  strategy, and model weights. Cache invariant must be designed explicitly.
- Per-component vocabularies vs. shared vocabulary. Per-component is more
  expressive but creates inter-region dialects to translate between.
- Extensible vocabulary breaks caching and complicates fine-tuning, but a
  fully fixed vocabulary will discover gaps in deployment.

**Action items.**

- Q5 partial answer received: **vocabulary is domain-scoped** (per problem
  domain, not global, not per-component).
- Vocabulary mutability still open — fixed vs. extensible.
- Cross-domain vocabulary interaction still open.

---

## Concept 5 — Categorization → Rule Retrieval → Strict Evaluation pipeline

**User intuition.** A repeatable three-stage component pipeline for any task
that resembles compliance checking, constraint satisfaction, or
domain-specific validation:

1. **Categorize** the entity against a domain typology.
2. **Retrieve** the rules that apply to that category from a validation
   context.
3. **Evaluate** the entity strictly against the retrieved rules (plus any
   other acceptance criteria fanning in from parallel sources) and emit
   verdicts.

**Why this is interesting as an architecture.** Each stage has a clean
boundary, a well-typed interface, and is independently testable. The
categorizer can be evaluated on labeling accuracy; the retriever on
recall@k against a known rule set; the evaluator on synthetic rules with
ground-truth verdicts.

**Pattern instances already in the Ponder spec.**

- **Conscience** is a degenerate case of this pipeline: categorization is
  trivial (the input is "the current draft response"), retrieval is trivial
  (rules of engagement + operator context, supplied directly), evaluation is
  the load-bearing step.
- **A future regulatory-validation region** would be a fully-elaborated
  instance, with each of the three stages doing nontrivial work.

**Worked example (user-supplied).**

- Input: proposed accessibility ramp design
- Stage 1: categorizer assigns `structure abutting public easement`
- Stage 2: regulatory validation context emits applicable rules including
  `${structure} SHALL NOT ABUT PUBLIC EASEMENT WITH HEIGHT TRANSFER GREATER THAN 1/8`
- Stage 3: decision component evaluates the proposed design against these
  rules + other criteria

**Research lineages.**

- BIM compliance checking — SMARTcodes, RASE methodology, BCRL. ~15 years of
  prior work on automated accessibility/structural rule checking.
- Production rule systems — CLIPS, Drools, Jess.
- Neurosymbolic constraint satisfaction.
- Information retrieval for rule lookup — recall@k metrics, dense retrieval,
  hybrid sparse+dense.

**Failure mode to design against.** Recall failure at stage 2 propagates
silently — if a relevant rule isn't retrieved, the strict evaluator can't
catch the violation. The retrieval step is the system's blind spot, not the
evaluator.

---

## Concept 6 — Closed-world strict evaluation

**User intuition.** The decision component operates only on supplied rules,
brings no own domain knowledge, and produces verdicts traceable to specific
rules.

**ML / CS mapping.** This is the closed-world assumption from KR, applied
deliberately at the component boundary. Borrowing terminology:

- The component is **fact-grounded** — its world is exactly the supplied
  inputs.
- The component is **non-defeasible** — verdicts cannot be overridden by
  general world knowledge.
- The component is **traceable** — every verdict cites the rule(s) that
  drove it.

**Why this is a strong design choice.**

| Property | Benefit |
|---|---|
| Auditability | Every verdict has a rule-citation chain |
| Independent verifiability | Component is testable on synthetic rule sets, no domain needed |
| Hallucination floor | Cannot invent rules; failure modes are bounded by retrieval |
| Composability | Multiple rule sources fan in; component is agnostic to source |

**Tradeoffs.**

- ❌ No graceful degradation. Cannot say "this seems risky based on related
  regulations" — only evaluates what was supplied.
- ❌ Brittle to retrieval incompleteness. Missing rule → silent miss.
- ❌ Cannot resolve conflicts the rule set itself doesn't address. If two
  rules contradict and no precedence rule is supplied, behavior is
  undefined.

**Computation question (open — Q6).** Several options:

- (a) Pattern matching against structured entity fields
- (b) Symbolic reasoning (forward-chaining, conflict resolution)
- (c) Neural rule-following (generative model trained on rule+entity → verdict)
- (d) Hybrid (neural parsing + symbolic evaluation)

Each has different training-data, vocabulary-scope, and testability
implications. Resolution is pending.

**RFC 2119 connection.** The user's `MUST` / `SHALL` / `SHALL NOT` vocabulary
is exactly the IETF specification language. RFC 2119 (clarified by RFC 8174)
gives precise semantics:

- **MUST** / **SHALL** = absolute requirement
- **MUST NOT** / **SHALL NOT** = absolute prohibition
- **SHOULD** = recommendation, exceptions allowed if consequences understood
- **SHOULD NOT** = discouragement, exceptions allowed
- **MAY** = optional

If this vocabulary is adopted, the component must encode these distinctions —
particularly the SHOULD vs MUST gradient, since SHOULD violations may be
acceptable while MUST violations are not. This affects verdict semantics
(binary vs. graded) and rule-set composition (precedence between SHOULD and
MUST when they collide).

---

## Concept 7 — Abstract relational schemas as structural representation

**User intuition.** The deeper goal — what the controlled vocabulary,
constraint evaluation, and rule-following discussions were all instrumental
to — is training components that **represent the structural dynamics of
situations independent of surface content**, as **entity-relationship
graphs** ("schemas").

**Examples (user-supplied):**

- "teacher teaching students" — asymmetric knowledge-transmission with
  feedback channel
- "unbound feedback loop" — runaway positive feedback, instability
- "opposing trends in equilibrium" — stable balance from competing forces

The same schema graph applies to vastly different concrete situations: the
"teacher teaching students" pattern shows up in classrooms, parenting,
consulting engagements, and ML training algorithms.

**Inversion of earlier framing.** Concepts 1–6 are now reinterpreted as
*means* to this end:

- Controlled vocabulary (4) reduces ambiguity so structure is exposed
- Symbolic abstraction (2) lets the model learn form rather than content
- Information compression (3) increases the proportional weight of
  structural tokens during training
- The three-stage pipeline (5) and closed-world evaluation (6) are useful
  for compliance subdomains but are not the central architectural pattern

**ML / cognitive-science lineage.** This is one of the deepest and most
contested research programs in AI:

- **Gentner, *Structure-Mapping Theory* (1983).** Foundational. Analogies
  are mappings between relational structures, not surface attributes.
  Computational descendants: SME (Falkenhainer et al.), LISA (Hummel &
  Holyoak).
- **Hofstadter** — Copycat, Tabletop, Metacat; *Surfaces and Essences*. 40+
  years of arguing that analogy is the core of cognition. The closest single
  philosophical antecedent.
- **System archetypes** (Meadows, Senge — *The Fifth Discipline*). A small
  catalog (~12) of recurring causal-loop patterns: limits to growth,
  shifting the burden, tragedy of the commons, fixes that fail, escalation,
  success to the successful, etc. Each has a canonical graphical form.
  Borrow this catalog as a starting target.
- **Image schemas** (Lakoff, Johnson — *Philosophy in the Flesh*).
  Pre-conceptual structures: CONTAINER, SOURCE-PATH-GOAL, BALANCE,
  FORCE-DYNAMIC. Plausibly cognitively universal.
- **Schank's scripts and frame-based AI** (Schank & Abelson, 1977). The 70s
  ancestor. Failed at scale due to hand-encoding cost; LLMs change the
  calculus.
- **Webb, Holyoak, Lu (2023), "Emergent analogical reasoning in large
  language models."** Empirical: GPT-3 solves Raven's Progressive Matrices
  and verbal analogies zero-shot. LLMs already encode something
  schema-like; the open question is reliable elicitation as explicit
  structured output.
- **Causal loop diagrams.** Standard notation in system dynamics. Closest
  existing graphical convention to the user's intent.
- **Knowledge graph / scene graph generation.** ML methodology for
  generating structured graph outputs from unstructured input. Direct
  technical precedent for the output format.
- **Abstract Meaning Representation (AMR) parsing.** Generates rooted
  directed graphs representing sentence semantics; the closest mature ML
  task to schema extraction.

**Genuine difficulties.**

1. **Non-uniqueness of mapping.** "Consultant onboarding client" can be
   schematized as teacher/student, merchant/service, or healer/patient. All
   valid. The output is "a schema given an abstraction lens," not "the
   schema." Either commit to a fixed lens per component, or model the lens
   as part of the input.
2. **Training data scale.** Where do labeled (concrete situation → schema)
   examples come from? Hand-curated archetype examples don't scale.
   Possible synthesis routes: distill from a strong generalist; bootstrap
   via consistency objectives; use system-dynamics literature as seed.
3. **Evaluation.** Inter-annotator agreement on schema labels has
   historically been poor. Need to define ground truth carefully — possibly
   by anchoring evaluation to the *consequences* of schema identification
   (e.g., schema-induced predictions match observed outcomes) rather than
   schema labels themselves.
4. **Catalog growth.** Every prior attempt to enumerate primitives (CYC,
   FrameNet, Schank scripts) saw the catalog expand without bound in
   deployment. Mitigation: start with a tightly-bounded archetype set
   (system archetypes catalog is a candidate) and accept that coverage will
   be partial.

**Honest assessment of feasibility.** Modern LLMs change the calculus for
problems that defeated purely symbolic approaches. The Webb et al. result
shows latent capability is present. The engineering question is whether
that latent capability can be elicited as explicit, structured, reliable
graph output at sufficient scale to ground a system on. Unsolved, but not
obviously unachievable. Starting with a small, well-defined archetype
catalog (e.g., the ~12 system archetypes) reduces ambition to something
tractable.

**Crystallized notation form (after Q9 resolution).**

Schemas are not full formal models of dynamics. They are compact
descriptors that pair a structural pattern with named expected behaviors:

```
schema = {
  entities: [...],
  relationships: [...],   # open NL with domain canonicalization
  cardinality: [...],     # standard ER (1:1, 1:N, M:N)
  variants: [...],        # named expected emergent behaviors
  domain: ...,
  notation_version: ...
}
```

Dynamics and emergence are **not first-class operators** in the notation.
They are listed as named variants. Their semantic content is carried by
the training narratives, not by formal definitions inside the notation.

This deliberately mirrors the system-archetypes convention: each archetype
is (structural pattern) + (small list of named typical outcomes). It is
sufficient for problem-solving without formal dynamic models. Once a
situation is recognized as an instance of the schema, the variants list
*immediately surfaces what to expect*. That is the operational payoff.

**Recognition is graph-structural, not embedding-similarity.** The user's
worked example for feedback systems framed recognition as a structural
rule ("one of its inputs is affected by an output"). This points toward
graph-homomorphism / pattern-match recognizers rather than vector
similarity. More interpretable and audit-friendly; consistent with the
auditability commitment (Concept 11).

**Action items.**

- Q7 answered (see Concept 8).
- Q9 substantially answered (see this section + Concept 10).
- Investigate the Webb/Holyoak/Lu paper closely.
- Investigate AMR parsing methodology.
- Adopt system archetypes catalog as candidate seed schema set.

---

## Concept 8 — Schema-driven inference as the reasoning mechanism

**User intuition (now crystallized).** Reasoning in Ponder is the process
of **selecting schemas, applying them to situations, and completing the
slots they create**. Schemas are not labels; they are **interrogative
probes** that generate questions whose answers populate previously
unarticulated structure of the situation.

**Three-stage mechanism.**

1. **Recognition.** Situation → ranked set of candidate schemas whose
   structure fits.
2. **Lens application / selection.** Choose schema(s) to actively engage.
   The chosen schema **directs the perspective of approach**, not merely
   describes the situation.
3. **Slot completion.** With (situation, schema), generate slot-questions
   ("who fills the teacher role here?"); propose answers from evidence,
   world knowledge, or generative inference. The proposed answers are
   **candidate inferences** — novel claims about the situation that were
   not in the input.

**Lineage and exact terminology.**

- **Gentner, Structure-Mapping Theory.** "Candidate inference" is the
  precise technical term for slot completion via analogy. When schema A is
  mapped onto situation B, structural relations of A that don't yet appear
  in B become predictions about B.
- **Schank, Scripts/Plans/Goals/Understanding (1977).** Script-driven
  inference: recognize "restaurant," fill slots for menu/waiter/payment
  even if not mentioned. Direct precursor.
- **Frame semantics, FrameNet.** Frames have frame elements (FEs).
  Recognized frame → slot-fill task for unfilled FEs.
- **Schema theory in cognitive psychology** (Bartlett, Rumelhart). The
  general framework.
- **Webb, Holyoak, Lu (2023).** Empirical demonstration that LLMs perform
  candidate-inference-style analogy zero-shot; the latent capability is
  available, the engineering question is reliable elicitation as
  structured output.

**Why this is a strong operational definition of reasoning.**

- **Testable per stage.** Recognition can be evaluated on labeled
  situations; selection on lens-choice traces; slot-filling on
  (situation, schema, slot) → answer triples.
- **Component-decomposable.** Each stage is a separable model with
  testable inputs and outputs.
- **Auditable.** The reasoning chain is explicit: which schemas were
  recognized, which was selected, which slots were filled, with what
  answers.

**Three separable functions, mapped provisionally to Ponder regions.**

| Function | Description | Region |
|---|---|---|
| Schema recognizer | situation → ranked candidate schemas | Hippocampus (vector retrieval) |
| Schema selector | choose lens(es) to apply | Prefrontal (planning) |
| Slot-filler probe | generate slot questions, propose answers | Wernicke (deep semantic parse) |

The slot-filler is the architecturally hardest piece because it is the
component doing genuine generative inference rather than retrieval or
classification. It needs:

- **Domain knowledge** — what fillings make sense in this context
- **Constraint propagation** — other slots constrain this one
- **Plausibility judgment** — does the proposed filling cohere with the
  rest of the situation

These are LLM-style strengths but require careful prompting/training.

**Open architectural questions.**

1. **Multi-schema parallelism.** When multiple schemas apply (consultant
   onboarding client = teacher/student + merchant/service +
   healer/patient), does the system commit to one for action or hold
   multiple in tension? Affects whether selection is a single-choice or a
   weighted-blend operation.
2. **Schema directing strategy vs. describing situation.** The user's
   "set the perspective of approach" claim is strong: schemas direct
   *strategy*, not just labels. Downstream regions (Prefrontal especially)
   must therefore be schema-aware — when a schema is active, planning and
   decomposition operate within its frame. This is an architectural
   coupling worth being deliberate about.
3. **Schema representation as data structure** — Q8, pending. Affects
   everything downstream.

**Action items.**

- Q8 answered (see Concept 9 for training methodology). Schema is
  **ERG-like**, with extensions needed for dynamics and emergence;
  catalog is **on-demand** rather than fixed.
- Q9 (notation primitives) is the next load-bearing question.
- Decide multi-schema arbitration policy.
- Specify the schema-awareness contract for Prefrontal.
- Identify minimum viable schema catalog for Phase 2 prototype (system
  archetypes catalog is a candidate seed).

---

## Concept 9 — Schematic narrative paired training

**User intuition.** Train the schema model on **(narrative, structured
notation) pairs**. Generate many narratives that exemplify a schema in
varied surface contexts, each paired with the canonical structured
notation. The model learns the invariant structure across surface
variation.

**ML mapping.** This is **paired-example training for structured
prediction** — a well-established methodology with several mature
descendants:

- **AMR parsing.** AMR (Abstract Meaning Representation) datasets were
  built by hand-pairing sentences with their semantic graphs. AMR parsers
  learn this mapping. Direct technical precedent.
- **Rationale-distilled small models.** Orca, Phi-series. Pair an
  intermediate structured representation (chain-of-thought, plan,
  rationale) with the input and target output; train a small model on the
  pairs. Empirically: smaller models trained this way outperform larger
  models trained on raw inputs alone.
- **Synthetic data generation for fine-tuning.** Phi-2/3, WizardLM,
  Self-Instruct lineage. Synthesize training data with guaranteed
  structural properties; train on the synthetic corpus.
- **Knowledge graph induction from text.** Graph2Seq, OpenIE,
  REBEL — training models to extract triples or graphs from natural
  language. Methodology is mature.

**Key property of the methodology.** The model is forced to abstract over
surface form because the same notation appears with many different
narratives. Surface variation is the training signal that drives
abstraction. This is the same principle that makes Symbol Tuning work
(Concept 2): variation strips content from form.

**Open methodology questions.**

1. **Where do the narratives come from?**
   - Hand-written by experts (slow, expensive, high quality)
   - LLM-generated from a seed schema (scalable, risk of mode collapse)
   - Curated from existing corpora and labeled (slow, but uses real-world
     distribution)
   - Hybrid: hand-write seed narratives, LLM-expand, hand-curate
2. **How many narratives per schema?** Order of magnitude. The AMR
   community started with ~10K sentence-graph pairs total; modern
   instruction-tuning datasets run into millions. Likely need at least
   hundreds per schema for reliable abstraction.
3. **Does the same narrative ever pair with multiple schemas?** Important
   for the multi-schema arbitration question (Concept 8). Multi-pairing
   teaches the model that schemas are perspectives, not unique ground
   truth.
4. **What's the structured notation itself?** This is Q9 — the recursive
   vocabulary problem.

**Engineering implication for "on demand" catalog.** If schemas are
generated on demand, the model needs to be capable of producing novel
notation graphs at inference time, not just retrieving known ones. This
makes the paired training even more important: the model has to learn the
*notation language* well enough to generate well-formed novel graphs.

**Action items.**

- Q9.2 answered (see Concept 10). Open NL predicates with domain
  canonicalization.
- Q9.1, Q9.3, Q9.4, Q9.5 still open — entity types, cardinality, dynamics,
  emergence.
- Estimate corpus scale needed.
- Decide narrative-generation pipeline (hand / LLM / hybrid).
- Decide notation human-readability tradeoff.

---

## Concept 10 — Open notation with domain canonicalization

**User intuition.** Notation predicates are open NL while the design space
is being mapped. Within a domain, prefer a curated set to suppress synonym
sprawl ("multiple things that should be one thing"). Provisional design;
will tighten as canonical predicates emerge from usage.

**ML / KR mapping.** This pattern — open vocabulary + domain-specific
canonical sets — is exactly how mature controlled vocabularies in real
domains evolved:

- **MeSH** (Medical Subject Headings, NLM)
- **SNOMED-CT** (clinical terminology)
- **LOINC** (laboratory observations)
- **Schema.org** with altLabel/preferredLabel relationships

All started looser and tightened over time as canonical forms emerged from
practice. The user's framing matches this trajectory deliberately.

**Canonicalization mechanism (design choice — not yet committed).**

| Mechanism | Pros | Cons |
|---|---|---|
| Trained-in | Cheapest at inference | Inflexible after training |
| Synonym-table post-processing | Fast, explicit, auditable | Hand-curated tables |
| Constrained decoding with bias | Elegant, no extra component | Inference-time coupling |
| Embedding-similarity collapsing | Automated | Silent false merges |
| Dedicated canonicalizer model | Most flexible | Extra component |

**Practical hybrid likely.** Trained-in for high-frequency canonicals
(cheap, fast); embedding-similarity as fallback for near-synonyms; human
curation as the long-running backstop. This mirrors how production
knowledge-graph construction pipelines handle predicate normalization.

**Two implications now load-bearing.**

1. **Notation versioning.** Predicate set will evolve. Each (narrative,
   notation) pair must record the notation version it was authored under.
   Migrations between versions must exist, or vocabulary evolution
   silently invalidates training data.
2. **Domain identification is now a system requirement.** Canonicalization
   is per-domain (Concept 4 / Q5). The system must:
   - Determine domain from input (tagged? inferred? schema-supplied?)
   - Handle multi-domain situations (which canonicals apply when domains overlap?)
   - Resolve domain disagreements between recognizer and selector

   Domain-identification design is itself a sub-architecture worth
   pulling on as a separate question.

**Action items.**

- Decide canonicalization mechanism (or commit to the practical hybrid).
- Design notation versioning scheme — minimally a version field on each
  schema; ideally tooling for migration between versions.
- Pull on domain identification: how does the system know which domain a
  situation belongs to?

---

## Concept 11 — Auditability as system commitment

**User intuition.** The key facility of the schema mechanism — explicitly
named — is **the ability to audit the findings and usage of them**.

**Status:** This is now a **cross-cutting system commitment**, not a local
property of any one component. Auditability has surfaced as a thread
through multiple concepts:

- Concept 6 (closed-world strict evaluation) — verdicts trace to specific
  rules
- Concept 7 (controlled vocabulary) — bounded outputs are
  schema-validatable
- Concept 8 (schema-driven inference) — three-stage decomposition gives
  per-stage test surfaces
- Concept 10 (notation versioning) — pairs are versioned for traceable
  evolution

**Operational requirements.**

1. **Schema application trace.** Every reasoning step records which
   schemas were considered, which were applied, and the order of
   application.
2. **Inference tagging.** Every candidate inference (slot-fill output)
   carries metadata: originating schema, slot it filled, evidence used,
   confidence.
3. **Behavior anticipation trace.** When a schema is applied and its
   variants surface expected behaviors, the trace records which behavior
   was anticipated and which (if any) was observed.
4. **Provenance unrolling.** Any conclusion the system reaches must be
   unrollable through its schema-application chain back to inputs.

**Architectural implications for Ponder.**

- The blackboard already records turn state. Extend it to record schema
  trace per turn.
- Hippocampus (currently storing memory text) should also store schema
  application history alongside facts.
- The Conscience region is a natural place to evaluate
  schema-application validity (e.g., did we apply schemas appropriate to
  the domain? did we anticipate behaviors that didn't materialize?).

**Why this is a strong commitment.** Most LLM-based systems are
post-hoc explainable at best — you ask the model to justify its output,
and it generates a rationale that may or may not reflect the actual
computation. Schema-driven inference with provenance tracking is
**legible by construction**: the trace is the actual reasoning path, not
a reconstruction. This is a substantial differentiator for high-stakes
applications (regulatory, medical, engineering).

**Tradeoffs to be aware of.**

- Trace storage cost — every turn produces metadata; need a retention
  policy
- Trace complexity — deep schema-application chains may be hard to
  inspect; need visualization tooling
- Performance — provenance tracking adds overhead per inference step
- Honesty — the trace is only as good as the schema-application
  decisions; if the recognizer silently picks the wrong schema, the trace
  is misleading even though it's structurally valid

**Action items.**

- Specify the trace data structure (Q-pending).
- Decide provenance retention policy.
- Build basic trace visualization for development.
- Audit-blind-spot analysis: where can the system fail audibly vs.
  silently?

---

