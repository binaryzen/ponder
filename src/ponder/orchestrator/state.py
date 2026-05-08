"""Component-namespaced state store + provider-backed context service.

Two layers:

  StateStore   — component-private state. Each component writes only under
                 its own URN namespace (``component:<owner>:<key>``).
                 Reads are technically possible but should normally go
                 through the ContextService.

  ContextService — public, curated view. Each context URN
                   (``context:<key>``) has a registered Provider whose
                   implementation decides how to combine, prioritize, or
                   default values from underlying component state.

Providers can:
  - passthrough one source URN
  - prefer the highest-confidence source among several
  - return a synthesized default when no source provides
  - composite — derive a value from multiple component states

This separation is the "leverage point" — what specialists see is the
ContextService output, not raw component state. New sources contributing
to an existing context URN are picked up by the provider's depends_on
prefix matching; consumers don't need to know.
"""

from __future__ import annotations

import asyncio
import time
from dataclasses import dataclass, field
from typing import Any, Callable, Iterable, Sequence

from ponder.orchestrator.blackboard import Blackboard, StateChange


# ── URN conventions ─────────────────────────────────────────────────────────

COMPONENT_PREFIX = "component:"
CONTEXT_PREFIX = "context:"


def component_urn(owner: str, key: str) -> str:
    """Construct a component-state URN: ``component:<owner>:<key>``."""
    return f"{COMPONENT_PREFIX}{owner}:{key}"


def context_urn(key: str) -> str:
    """Construct a context URN: ``context:<key>``."""
    return f"{CONTEXT_PREFIX}{key}"


def split_component_urn(urn: str) -> tuple[str, str]:
    """``component:cogitator:state`` -> ``("cogitator", "state")``."""
    if not urn.startswith(COMPONENT_PREFIX):
        raise ValueError(f"not a component URN: {urn!r}")
    rest = urn[len(COMPONENT_PREFIX):]
    owner, _, key = rest.partition(":")
    return owner, key


# ── StateStore ──────────────────────────────────────────────────────────────

class StateStore:
    """Component-private state. Wraps a Blackboard with namespace discipline."""

    def __init__(self, blackboard: Blackboard | None = None) -> None:
        self._bb = blackboard or Blackboard()

    @property
    def blackboard(self) -> Blackboard:
        """Underlying primitive — exposed for the Runtime to register subscribers."""
        return self._bb

    def write(self, owner: str, key: str, value: Any) -> StateChange:
        return self._bb.set(component_urn(owner, key), value)

    def read(self, urn: str, default: Any = None) -> Any:
        return self._bb.get(urn, default)

    def keys_with_prefix(self, prefix: str) -> list[str]:
        """Return all stored URNs starting with ``prefix``. Used by providers."""
        return [k for k in self._bb.keys() if k.startswith(prefix)]

    def items_with_prefix(self, prefix: str) -> dict[str, Any]:
        return {k: self._bb.get(k) for k in self.keys_with_prefix(prefix)}

    def subscribe(self, urns: Iterable[str]) -> asyncio.Queue:
        return self._bb.subscribe(urns)


# ── Provider ────────────────────────────────────────────────────────────────

@dataclass
class Provider:
    """A function that produces a context value from underlying StateStore.

    fn         — called as ``fn(store)`` to produce the context value
    depends_on — list of state-URN prefixes this provider's value depends on.
                 The ContextService recomputes whenever a write hits any of
                 these prefixes.
    """

    fn: Callable[[StateStore], Any]
    depends_on: list[str] = field(default_factory=list)


# ── Provider primitives ─────────────────────────────────────────────────────

def passthrough(source_urn: str, default: Any = None) -> Provider:
    """Trivial provider — returns the raw value at one component URN."""
    return Provider(
        fn=lambda store: store.read(source_urn, default),
        depends_on=[source_urn],
    )


def default_if_unset(source_urn: str, default: Any) -> Provider:
    """Returns the source value, or ``default`` if the source is None/missing."""
    def _fn(store: StateStore) -> Any:
        value = store.read(source_urn)
        return default if value is None else value
    return Provider(fn=_fn, depends_on=[source_urn])


def prefer_highest_confidence(
    source_prefix: str,
    extract_value: Callable[[Any], Any] = lambda v: v.get("value"),
    extract_confidence: Callable[[Any], float] = lambda v: v.get("confidence", 0.0),
    default: Any = None,
) -> Provider:
    """Pick the highest-confidence value among all sources matching ``source_prefix``.

    Each source's stored value is expected to be a dict-like with at least
    "value" and "confidence" fields. ``extract_*`` lambdas let you customize
    if your sources use a different shape.
    """
    def _fn(store: StateStore) -> Any:
        items = store.items_with_prefix(source_prefix)
        best: tuple[float, Any] | None = None
        for _urn, raw in items.items():
            if raw is None:
                continue
            try:
                conf = float(extract_confidence(raw))
            except (TypeError, ValueError, AttributeError):
                continue
            if best is None or conf > best[0]:
                best = (conf, extract_value(raw))
        return best[1] if best is not None else default
    return Provider(fn=_fn, depends_on=[source_prefix])


def composite(
    fn: Callable[[StateStore], Any],
    depends_on: Sequence[str],
) -> Provider:
    """General-purpose provider: arbitrary derivation from named state prefixes."""
    return Provider(fn=fn, depends_on=list(depends_on))


# ── ContextService ──────────────────────────────────────────────────────────

class ContextService:
    """Provider-backed view over the StateStore.

    Reading a context URN runs its registered provider against the current
    StateStore. The service can also publish change events on context URNs
    (so specialists can subscribe to context URNs the same way they
    subscribe to component URNs); this is opt-in via ``publish_changes=True``.
    """

    def __init__(
        self,
        store: StateStore,
        publish_changes_via: Blackboard | None = None,
    ) -> None:
        self._store = store
        self._providers: dict[str, Provider] = {}
        # If set, recomputed context values are written into this blackboard so
        # specialists can subscribe to context: URNs natively.
        self._publish_via = publish_changes_via
        self._cached: dict[str, Any] = {}
        self._listener_task: asyncio.Task | None = None

    # ── Registration ────────────────────────────────────────────────────────

    def register(self, urn: str, provider: Provider) -> None:
        if not urn.startswith(CONTEXT_PREFIX):
            raise ValueError(f"context URN must start with '{CONTEXT_PREFIX}': {urn!r}")
        self._providers[urn] = provider

    def registered_urns(self) -> list[str]:
        return list(self._providers.keys())

    # ── Reading ─────────────────────────────────────────────────────────────

    def get(self, urn: str, default: Any = None) -> Any:
        provider = self._providers.get(urn)
        if provider is None:
            return default
        return provider.fn(self._store)

    def snapshot(self) -> dict[str, Any]:
        """Compute and return all registered context URNs in one pass."""
        return {urn: self.get(urn) for urn in self._providers}

    # ── Reactive recomputation ──────────────────────────────────────────────

    async def start(self) -> None:
        """Begin listening for component-state changes; recompute affected context URNs.

        Only meaningful if the service was constructed with a publish_changes_via
        blackboard. Subscribes synchronously before returning so any writes
        issued after start() are observed.

        Primes the value cache with current computed values so subsequent
        writes that don't actually change the context output don't trigger
        spurious publishes.
        """
        if self._listener_task is not None:
            return
        # Prime the cache without publishing — only true value changes from
        # this baseline will fire publishes.
        for urn, provider in self._providers.items():
            self._cached[urn] = provider.fn(self._store)
        # Subscribe synchronously here (not inside the task) so we don't race
        # against writes issued immediately after start() returns.
        queue = self._store.blackboard.subscribe([])  # wildcard
        self._listener_task = asyncio.create_task(self._listen(queue))

    async def stop(self) -> None:
        if self._listener_task:
            self._listener_task.cancel()
            try:
                await self._listener_task
            except asyncio.CancelledError:
                pass
            self._listener_task = None

    async def _listen(self, queue: asyncio.Queue) -> None:
        while True:
            change: StateChange = await queue.get()
            self._on_state_change(change)

    def _on_state_change(self, change: StateChange) -> None:
        for ctx_urn, provider in self._providers.items():
            if not any(self._depends(change.key, prefix) for prefix in provider.depends_on):
                continue
            new_value = provider.fn(self._store)
            old_value = self._cached.get(ctx_urn)
            if new_value != old_value:
                self._cached[ctx_urn] = new_value
                if self._publish_via is not None:
                    self._publish_via.set(ctx_urn, new_value)

    @staticmethod
    def _depends(written_urn: str, dep_prefix: str) -> bool:
        # Treat dep_prefix as a literal-or-prefix match.
        return written_urn == dep_prefix or written_urn.startswith(dep_prefix)


# ── SpecialistView ──────────────────────────────────────────────────────────

@dataclass
class SpecialistView:
    """What a specialist sees when its run() is invoked.

    Reads go through ``view.get(urn)`` (context-service-backed).
    Writes go through ``view.write(key, value)`` (owner-namespaced).
    """

    owner: str
    state: StateStore
    context: ContextService

    def get(self, urn: str, default: Any = None) -> Any:
        # Convenience: route through ContextService for context: URNs;
        # allow direct StateStore reads for component: URNs.
        if urn.startswith(CONTEXT_PREFIX):
            return self.context.get(urn, default)
        return self.state.read(urn, default)

    def write(self, key: str, value: Any) -> StateChange:
        return self.state.write(self.owner, key, value)
