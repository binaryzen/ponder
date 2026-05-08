"""Tests for ponder.orchestrator.state — StateStore, ContextService, providers."""

import asyncio
import pytest

from ponder.orchestrator.blackboard import Blackboard
from ponder.orchestrator.state import (
    ContextService,
    Provider,
    SpecialistView,
    StateStore,
    component_urn,
    composite,
    context_urn,
    default_if_unset,
    passthrough,
    prefer_highest_confidence,
    split_component_urn,
)


# ── URN helpers ──────────────────────────────────────────────────────────────


def test_component_urn_format():
    assert component_urn("cogitator", "state") == "component:cogitator:state"


def test_context_urn_format():
    assert context_urn("current_input") == "context:current_input"


def test_split_component_urn_roundtrip():
    assert split_component_urn("component:cogitator:state") == ("cogitator", "state")


def test_split_component_urn_rejects_non_component():
    with pytest.raises(ValueError):
        split_component_urn("context:foo")


def test_split_component_urn_handles_colons_in_key():
    """Keys may themselves contain colons; partition leaves the rest intact."""
    owner, key = split_component_urn("component:cog:nested:key")
    assert owner == "cog"
    assert key == "nested:key"


# ── StateStore ───────────────────────────────────────────────────────────────


def test_state_store_writes_under_owner_namespace():
    store = StateStore()
    store.write("cogitator", "state", "thinking")
    assert store.read(component_urn("cogitator", "state")) == "thinking"


def test_state_store_separates_owners():
    store = StateStore()
    store.write("a", "key", 1)
    store.write("b", "key", 2)
    assert store.read(component_urn("a", "key")) == 1
    assert store.read(component_urn("b", "key")) == 2


def test_state_store_keys_with_prefix():
    store = StateStore()
    store.write("cog", "x", 1)
    store.write("cog", "y", 2)
    store.write("other", "z", 3)
    keys = store.keys_with_prefix("component:cog:")
    assert set(keys) == {"component:cog:x", "component:cog:y"}


def test_state_store_items_with_prefix():
    store = StateStore()
    store.write("cog", "x", 1)
    store.write("other", "y", 2)
    items = store.items_with_prefix("component:cog:")
    assert items == {"component:cog:x": 1}


# ── Provider primitives ──────────────────────────────────────────────────────


def test_passthrough_returns_source_value():
    store = StateStore()
    store.write("a", "k", "hello")
    p = passthrough(component_urn("a", "k"))
    assert p.fn(store) == "hello"
    assert p.depends_on == [component_urn("a", "k")]


def test_passthrough_returns_default_when_missing():
    store = StateStore()
    p = passthrough(component_urn("a", "k"), default="fallback")
    assert p.fn(store) == "fallback"


def test_default_if_unset_returns_default_for_none():
    store = StateStore()
    p = default_if_unset(component_urn("a", "k"), default="def")
    assert p.fn(store) == "def"


def test_default_if_unset_returns_value_when_set():
    store = StateStore()
    store.write("a", "k", "real")
    p = default_if_unset(component_urn("a", "k"), default="def")
    assert p.fn(store) == "real"


def test_prefer_highest_confidence_picks_top():
    store = StateStore()
    store.write("classifier_a", "intent", {"value": "ask", "confidence": 0.6})
    store.write("classifier_b", "intent", {"value": "muse", "confidence": 0.9})
    store.write("classifier_c", "intent", {"value": "greet", "confidence": 0.3})
    p = prefer_highest_confidence("component:")
    # The current prefix matches all components; provider only considers
    # entries whose value is the expected dict shape.
    # Filter to just the classifier-* sources by adjusting prefix:
    p2 = Provider(
        fn=lambda s: prefer_highest_confidence("component:classifier_").fn(s),
        depends_on=["component:classifier_"],
    )
    assert p2.fn(store) == "muse"


def test_prefer_highest_confidence_default_when_no_sources():
    store = StateStore()
    p = prefer_highest_confidence("component:nonexistent:", default="none")
    assert p.fn(store) == "none"


def test_prefer_highest_confidence_skips_malformed():
    store = StateStore()
    store.write("c1", "intent", "not a dict")  # malformed
    store.write("c2", "intent", {"value": "ok", "confidence": 0.5})
    p = prefer_highest_confidence("component:c", default="none")
    assert p.fn(store) == "ok"


def test_composite_combines_multiple_sources():
    store = StateStore()
    store.write("a", "x", 10)
    store.write("b", "y", 5)
    p = composite(
        fn=lambda s: s.read(component_urn("a", "x"), 0) + s.read(component_urn("b", "y"), 0),
        depends_on=["component:a:x", "component:b:y"],
    )
    assert p.fn(store) == 15


# ── ContextService ───────────────────────────────────────────────────────────


def test_context_register_and_get():
    store = StateStore()
    store.write("a", "k", "value")
    ctx = ContextService(store)
    ctx.register(context_urn("foo"), passthrough(component_urn("a", "k")))
    assert ctx.get(context_urn("foo")) == "value"


def test_context_get_unregistered_returns_default():
    store = StateStore()
    ctx = ContextService(store)
    assert ctx.get(context_urn("nope"), default="x") == "x"


def test_context_register_rejects_non_context_urn():
    store = StateStore()
    ctx = ContextService(store)
    with pytest.raises(ValueError):
        ctx.register("component:bad:urn", passthrough(component_urn("a", "k")))


def test_context_snapshot():
    store = StateStore()
    store.write("a", "k", 1)
    store.write("b", "k", 2)
    ctx = ContextService(store)
    ctx.register(context_urn("a"), passthrough(component_urn("a", "k")))
    ctx.register(context_urn("b"), passthrough(component_urn("b", "k")))
    snap = ctx.snapshot()
    assert snap == {"context:a": 1, "context:b": 2}


def test_context_recomputes_on_underlying_change():
    store = StateStore()
    ctx = ContextService(store)
    ctx.register(context_urn("foo"), passthrough(component_urn("a", "k"), default="empty"))
    assert ctx.get(context_urn("foo")) == "empty"
    store.write("a", "k", "now-here")
    assert ctx.get(context_urn("foo")) == "now-here"


@pytest.mark.asyncio
async def test_context_publishes_changes_to_blackboard():
    """When started with publish_changes_via, recomputed context URNs are written to that blackboard."""
    bb = Blackboard()
    store = StateStore(bb)
    ctx = ContextService(store, publish_changes_via=bb)
    ctx.register(context_urn("foo"), passthrough(component_urn("a", "k"), default="empty"))

    # Subscribe to context:foo before starting.
    subscriber = bb.subscribe([context_urn("foo")])

    await ctx.start()
    try:
        # Make a change to the underlying state.
        store.write("a", "k", "new-value")
        # The context should re-publish to the blackboard.
        change = await asyncio.wait_for(subscriber.get(), timeout=1.0)
        assert change.key == context_urn("foo")
        assert change.new_value == "new-value"
    finally:
        await ctx.stop()


@pytest.mark.asyncio
async def test_context_does_not_republish_when_value_unchanged():
    bb = Blackboard()
    store = StateStore(bb)
    ctx = ContextService(store, publish_changes_via=bb)
    ctx.register(context_urn("foo"), passthrough(component_urn("a", "k"), default="x"))

    subscriber = bb.subscribe([context_urn("foo")])

    await ctx.start()
    try:
        store.write("a", "k", "x")  # same as default -> no context change
        # Wait briefly; nothing should arrive.
        with pytest.raises(asyncio.TimeoutError):
            await asyncio.wait_for(subscriber.get(), timeout=0.3)
    finally:
        await ctx.stop()


# ── SpecialistView ───────────────────────────────────────────────────────────


def test_specialist_view_writes_under_owner():
    store = StateStore()
    ctx = ContextService(store)
    view = SpecialistView(owner="alice", state=store, context=ctx)
    view.write("k", "v")
    assert store.read(component_urn("alice", "k")) == "v"


def test_specialist_view_get_routes_context_urns_through_provider():
    store = StateStore()
    store.write("a", "k", "raw-value")
    ctx = ContextService(store)
    ctx.register(context_urn("derived"), passthrough(component_urn("a", "k")))
    view = SpecialistView(owner="alice", state=store, context=ctx)
    assert view.get(context_urn("derived")) == "raw-value"


def test_specialist_view_get_passes_through_for_component_urns():
    """Component URNs should not be wrapped in provider semantics."""
    store = StateStore()
    store.write("a", "k", 42)
    ctx = ContextService(store)
    view = SpecialistView(owner="anyone", state=store, context=ctx)
    assert view.get(component_urn("a", "k")) == 42
