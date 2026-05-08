# Drift Check Playbook

Two-stage practice for keeping `CONTEXT.md` aligned with `design/*` without
post-hoc cleanup. Replaces the earlier "Haiku writes, Opus verifies" pattern,
which let factual hallucinations land in the canonical doc before getting
caught.

## Stages

**Stage 1 — Survey (cheap model, e.g., Haiku).** Produces a structured
change report. Read-only against the repo. Does not modify `CONTEXT.md`.

**Stage 2 — Validate + Apply (smarter model, e.g., Sonnet/Opus).** Reads
the report only. For each proposed change, cross-references the citation
and the factual claims against source files. Applies validated changes,
rejects hallucinations with reasons logged.

The smart model's read budget is bounded — only the cited grounding for each
proposal, not the whole design surface.

---

## Stage 1 prompt template

Adapt the project name and paths if reused elsewhere.

```
You are running Stage 1 of a documentation drift check for the Ponder
project. Your job is to PROPOSE changes to CONTEXT.md, NOT apply them.

Read:
- C:\Users\Admin\Projects\ponder\CONTEXT.md (canonical target)
- C:\Users\Admin\Projects\ponder\design\*.md (working design source)

For each substantive design decision in design/ that is not reflected
in CONTEXT.md, produce one proposed change in the format below.

ABSOLUTE RULES:
- DO NOT modify CONTEXT.md. Output the report only.
- Every proposal must cite its source design file.
- Every factual claim (env var names, version numbers, file paths, model
  identifiers, port numbers, command names, API method names, etc.) must
  be listed under "Factual claims" so Stage 2 can verify it.
- If you are uncertain whether a claim is grounded, do NOT include it.
  Bias toward fewer, well-grounded proposals.

Output your report to:
  C:\Users\Admin\Projects\ponder\design\drift-reports\<YYYY-MM-DD>-<HHMM>.md

Use the schema below.

==== REPORT SCHEMA ====

# Drift Check Report — <YYYY-MM-DD HH:MM>

## Summary
- Files surveyed: <list>
- Proposed changes: <N>
- Anything you considered but rejected as too speculative: <list with reason>

## Proposed change 1: <short title>

**Target section in CONTEXT.md**: <heading or "(new section after X)">

**Type**: add | replace | delete

**Current text** (verbatim from CONTEXT.md, or "(section does not exist)"):
~~~
<text>
~~~

**Proposed text** (verbatim, ready to paste):
~~~
<text>
~~~

**Rationale**: <one sentence>

**Citation**:
- File: design/<file>.md
- Section/line: <heading or line range>
- Quoted passage: "<relevant excerpt>"

**Factual claims** (each will be verified in Stage 2):
- <claim 1, e.g., "env var is named PONDER_REDIS_URL">
- <claim 2, e.g., "Qdrant version is v1.17.1">
- <claim 3, e.g., "module path is src/ponder/ponder/audit/cli.py">
(empty list ok if the change is purely structural / nothing to verify)

==== END SCHEMA ====
```

## Stage 2 procedure

The smarter model reads the report and processes proposals in order.

**For each proposal:**

1. **Verify citation.** Read the cited section of the design file. Does it
   actually say what the proposal claims it does?
   - YES → continue
   - NO → reject; log "citation does not support claim"

2. **Verify factual claims.** For each item in the Factual claims list,
   look up the authoritative source (see grounding map below) and confirm.
   - All verified → continue
   - Any failed → reject; log which claims failed and what the source actually says

3. **Apply.** Use Edit to make the change in `CONTEXT.md`.

4. **Log result.** "Applied" or "Rejected (reason)".

After all proposals processed, produce a summary:
- Applied: N (list titles)
- Rejected: M (list titles + reasons)

## Factual-claim grounding map

Where to look when verifying common kinds of factual claims.

| Claim type | Authoritative source |
|---|---|
| Environment variable names | `src/ponder/ponder/config.py` (Pydantic model) and `.env.poc.example` |
| Container image versions | `docker-compose.yml` and `manifests/vector-store.yaml`, `manifests/redis.yaml` |
| Python package versions / dev deps | `src/ponder/pyproject.toml` |
| Module paths | actual filesystem under `src/ponder/ponder/` |
| Function / class names | source files under `src/ponder/ponder/` |
| Test counts | run `pytest --collect-only -q` or trust last reported count |
| Model identifiers (Ollama, vLLM) | `.env.poc.example` for POC defaults; `charts/cognitive-unit/values.yaml` for cluster |
| Port numbers | `docker-compose.yml` and `manifests/*.yaml` |
| Stream / channel naming | `src/ponder/ponder/audit/emitter.py` (`stream_key`) |
| API endpoint shapes | `src/ponder/ponder/audit/service.py`, `design/audit-interface.md` |
| Specialist names / structure | `src/ponder/ponder/orchestrator/specialist.py` and demos under `orchestrator/demos/` |
| Schema notation primitives | `design/data-structures.md` |
| Anything in design/ | The named file itself; if claim contradicts the file, source is wrong |

If a claim type isn't on this map and isn't trivially checkable, treat
the proposal as needing human review and flag it rather than guessing.

## When to run

- End of session, before declaring a stopping point
- After a substantial design decision is captured (e.g., M-milestone closes)
- Before major implementation work that will assume CONTEXT.md is current
- Optional: scheduled (cron / hook) for long-running projects

## Why this is structurally better than write-then-verify

| Old practice | This practice |
|---|---|
| Haiku writes canonical doc, Opus reviews | Haiku proposes, Opus validates against grounding, then writes |
| Errors land in canonical doc, get caught later (or missed) | Errors caught at proposal stage, never land |
| "Spot-verify" is vibes-based | Each claim has explicit citation + grounding-map verification |
| Smart model re-reads entire repo to verify | Smart model reads only cited grounding per proposal |
| Mistakes leave footprints in git history | Clean canonical doc state preserved |

## Reports archive

Stage 1 reports are written to `design/drift-reports/<YYYY-MM-DD>-<HHMM>.md`.
Kept as audit trail of what was proposed and what was applied vs. rejected.
Useful for:
- Tracing when a particular fact entered CONTEXT.md
- Spot-checking the cheap model's hallucination rate over time
- Backtracking if a later finding invalidates an earlier proposal
