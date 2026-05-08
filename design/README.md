# Ponder — Design Workspace

A space for working through design intuitions before they harden into specs.

## Purpose

The user has intuitive ideas about how to build a modular framework for
low-cost, high-performance specialized reasoning systems. The technical
language to describe those ideas — and the ML methodologies they connect to —
is what this workspace develops.

The flow is:

1. **Surface intuitions.** The user articulates ideas in their own language.
   Captured in `interview.md`.
2. **Map to methodology.** Each intuition gets translated into a known ML
   technique (or flagged as potentially novel). Captured in `concepts.md` as
   it emerges.
3. **Test assumptions.** Each claim about gain/loss/cost gets a verifiable
   experiment design. Captured in `assumptions.md` as it emerges.
4. **Fold into specs.** Once the design is coherent, the artifacts here get
   distilled into additions to `CONTEXT.md` and the spec doc.

## Files

- `interview.md` — the running design conversation, structured as Q/A
- `concepts.md` — (created on demand) ML-method mappings of user intuitions
- `assumptions.md` — (created on demand) claims to verify empirically

## Posture

- Resist premature commitment to terminology. The user's framing may be more
  precise than the standard ML term it superficially resembles.
- When connecting intuitions to existing research, name the technique and
  flag where the user's idea diverges from it.
- Quantification is the goal. Every claim about "low-cost" or
  "high-performance" should be reducible to a measurement protocol.
