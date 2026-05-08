"""Context variables for audit propagation.

Trace and span identity flows implicitly through call stacks via contextvars,
so region nodes don't need explicit threading of trace_id/parent_span_id
through their signatures. asyncio task spawn inherits contextvars by default,
which matters for Phase 2 parallelism.
"""

from contextvars import ContextVar


# Set per turn at run() entry; every event in the turn carries this trace_id.
current_trace_id: ContextVar[str] = ContextVar("ponder_trace_id", default="")

# Set when entering a logical span; events emitted while this is set inherit
# it as their parent_span_id. Resetting / unsetting reverts to the prior parent.
current_parent_span_id: ContextVar[str] = ContextVar("ponder_parent_span_id", default="")

# Active domain context. Per Q5 in interview.md, vocabulary is domain-scoped.
current_domain: ContextVar[str] = ContextVar("ponder_domain", default="default")

# Cognitive-unit name. Streams are keyed by unit so multiple units can share
# a Redis instance without entanglement.
current_unit: ContextVar[str] = ContextVar("ponder_unit", default="default")
