"""Tests for the orchestrator substrate.

External dependencies (Redis audit emit) are patched. Tests exercise the
substrate logic without touching the network.
"""

import asyncio
from unittest.mock import patch

import pytest

from ponder.orchestrator import EXIT_KEY, Blackboard, Runtime, Specialist


# Silence audit emits across all tests in this file — they hit a real Redis otherwise.
@pytest.fixture(autouse=True)
def _silence_audit():
    with patch("ponder.audit.emitter.emit"), \
         patch("ponder.orchestrator.dispatcher.emit"), \
         patch("ponder.orchestrator.runtime.emit"), \
         patch("ponder.orchestrator.runtime.emit_pipeline_event", return_value="span-x"):
        yield


# ── Blackboard ───────────────────────────────────────────────────────────────


def test_blackboard_get_set():
    bb = Blackboard()
    assert bb.get("k") is None
    bb.set("k", 1)
    assert bb.get("k") == 1


def test_blackboard_set_returns_change():
    bb = Blackboard()
    bb.set("k", 1)
    change = bb.set("k", 2)
    assert change.key == "k"
    assert change.old_value == 1
    assert change.new_value == 2


@pytest.mark.asyncio
async def test_blackboard_subscribe_keys():
    bb = Blackboard()
    q = bb.subscribe(["a"])
    bb.set("a", 1)
    bb.set("b", 2)  # not watched
    change = await asyncio.wait_for(q.get(), timeout=0.5)
    assert change.key == "a"
    assert q.empty()


@pytest.mark.asyncio
async def test_blackboard_wildcard_subscribe():
    bb = Blackboard()
    q = bb.subscribe([])  # empty = wildcard
    bb.set("a", 1)
    bb.set("b", 2)
    c1 = await q.get()
    c2 = await q.get()
    assert {c1.key, c2.key} == {"a", "b"}


def test_blackboard_update_batch():
    bb = Blackboard()
    changes = bb.update({"a": 1, "b": 2})
    assert len(changes) == 2
    assert bb.get("a") == 1
    assert bb.get("b") == 2


# ── Specialist ───────────────────────────────────────────────────────────────


def test_specialist_requires_run():
    with pytest.raises(ValueError):
        Specialist(name="bad")


def test_specialist_default_predicate_fires():
    sp = Specialist(name="x", run=lambda bb: None)
    bb = Blackboard()
    bb.set("k", 1)
    change = bb.set("k", 2)
    assert sp.should_activate(bb, change) is True


# ── Runtime: state-driven activation ─────────────────────────────────────────


@pytest.mark.asyncio
async def test_runtime_activates_specialist_on_watched_key():
    fired = asyncio.Event()

    async def run(bb):
        fired.set()
        return None

    sp = Specialist(name="watcher", watches=["trigger"], run=run)
    rt = Runtime([sp], worker_count=2)

    async def driver():
        await asyncio.sleep(0.05)
        rt.blackboard.set("trigger", 1)
        await asyncio.wait_for(fired.wait(), timeout=2.0)
        rt.blackboard.set(EXIT_KEY, True)

    await asyncio.gather(rt.run(max_runtime_seconds=3.0), driver())
    assert fired.is_set()


@pytest.mark.asyncio
async def test_runtime_predicate_filters_activations():
    fire_count = {"n": 0}

    async def run(bb):
        fire_count["n"] += 1
        return None

    sp = Specialist(
        name="picky",
        watches=["trigger"],
        run=run,
        should_activate=lambda bb, change: change.new_value % 2 == 0,
    )
    rt = Runtime([sp], worker_count=2)

    async def driver():
        await asyncio.sleep(0.05)
        for v in [1, 2, 3, 4, 5, 6]:
            rt.blackboard.set("trigger", v)
        await asyncio.sleep(0.5)
        rt.blackboard.set(EXIT_KEY, True)

    await asyncio.gather(rt.run(max_runtime_seconds=3.0), driver())
    # Only even values triggered runs (2, 4, 6).
    assert fire_count["n"] == 3


@pytest.mark.asyncio
async def test_runtime_concurrent_specialists_on_same_key():
    """Two specialists watch the same key; both fire on a write."""
    a_done = asyncio.Event()
    b_done = asyncio.Event()

    async def a_run(bb):
        await asyncio.sleep(0.1)
        a_done.set()
        return None

    async def b_run(bb):
        await asyncio.sleep(0.1)
        b_done.set()
        return None

    sp_a = Specialist(name="A", watches=["trigger"], run=a_run)
    sp_b = Specialist(name="B", watches=["trigger"], run=b_run)
    rt = Runtime([sp_a, sp_b], worker_count=4)

    async def driver():
        await asyncio.sleep(0.05)
        rt.blackboard.set("trigger", 1)
        await asyncio.wait_for(asyncio.gather(a_done.wait(), b_done.wait()), timeout=2.0)
        rt.blackboard.set(EXIT_KEY, True)

    await asyncio.gather(rt.run(max_runtime_seconds=3.0), driver())
    assert a_done.is_set() and b_done.is_set()


# ── Runtime: model semaphore gating ──────────────────────────────────────────


@pytest.mark.asyncio
async def test_model_semaphore_serializes_model_specialists():
    """Two specialists with needs_model=True can never run concurrently when sem=1."""
    in_flight = {"now": 0, "max": 0}
    lock = asyncio.Lock()

    async def model_run(bb):
        async with lock:
            in_flight["now"] += 1
            in_flight["max"] = max(in_flight["max"], in_flight["now"])
        await asyncio.sleep(0.15)
        async with lock:
            in_flight["now"] -= 1
        return None

    sp_a = Specialist(name="modelA", watches=["go"], needs_model=True, run=model_run)
    sp_b = Specialist(name="modelB", watches=["go"], needs_model=True, run=model_run)
    rt = Runtime([sp_a, sp_b], worker_count=4, model_concurrency=1)

    async def driver():
        await asyncio.sleep(0.05)
        rt.blackboard.set("go", 1)
        await asyncio.sleep(0.5)
        rt.blackboard.set(EXIT_KEY, True)

    await asyncio.gather(rt.run(max_runtime_seconds=3.0), driver())
    # With model_concurrency=1, never more than one model run in flight at once.
    assert in_flight["max"] == 1


@pytest.mark.asyncio
async def test_non_model_specialist_runs_in_parallel_with_model_specialist():
    """A non-model specialist does not compete with a model specialist."""
    overlap_observed = {"yes": False}
    model_running = asyncio.Event()
    nonmodel_running = asyncio.Event()

    async def model_run(bb):
        model_running.set()
        await asyncio.sleep(0.2)
        if nonmodel_running.is_set():
            overlap_observed["yes"] = True
        return None

    async def nonmodel_run(bb):
        await model_running.wait()  # ensure model has started
        nonmodel_running.set()
        await asyncio.sleep(0.05)
        if model_running.is_set():
            overlap_observed["yes"] = True
        return None

    sp_a = Specialist(name="model", watches=["go"], needs_model=True, run=model_run)
    sp_b = Specialist(name="cheap", watches=["go"], needs_model=False, run=nonmodel_run)
    rt = Runtime([sp_a, sp_b], worker_count=4, model_concurrency=1)

    async def driver():
        await asyncio.sleep(0.05)
        rt.blackboard.set("go", 1)
        await asyncio.sleep(0.5)
        rt.blackboard.set(EXIT_KEY, True)

    await asyncio.gather(rt.run(max_runtime_seconds=3.0), driver())
    assert overlap_observed["yes"] is True


# ── Runtime: cascading state changes ────────────────────────────────────────


@pytest.mark.asyncio
async def test_cascade_a_writes_b_writes_c():
    """A produces B; B produces C. Verify the cascade fires."""
    c_set = asyncio.Event()

    async def a_run(bb):
        return {"b": "value-b"}

    async def b_run(bb):
        return {"c": "value-c"}

    async def c_run(bb):
        c_set.set()
        return None

    sp_a = Specialist(name="A", watches=["a"], run=a_run)
    sp_b = Specialist(name="B", watches=["b"], run=b_run)
    sp_c = Specialist(name="C", watches=["c"], run=c_run)
    rt = Runtime([sp_a, sp_b, sp_c], worker_count=4)

    async def driver():
        await asyncio.sleep(0.05)
        rt.blackboard.set("a", "value-a")
        await asyncio.wait_for(c_set.wait(), timeout=2.0)
        rt.blackboard.set(EXIT_KEY, True)

    await asyncio.gather(rt.run(max_runtime_seconds=3.0), driver())
    assert rt.blackboard.get("b") == "value-b"
    assert rt.blackboard.get("c") == "value-c"


# ── Runtime: tick-driven activation ──────────────────────────────────────────


@pytest.mark.asyncio
async def test_tick_specialist_fires_periodically():
    fire_count = {"n": 0}

    async def run(bb):
        fire_count["n"] += 1
        return None

    sp = Specialist(name="ticker", tick_seconds=0.1, run=run)
    rt = Runtime([sp], worker_count=2)

    async def driver():
        await asyncio.sleep(0.55)  # ~5 ticks
        rt.blackboard.set(EXIT_KEY, True)

    await asyncio.gather(rt.run(max_runtime_seconds=2.0), driver())
    # Allow some tolerance for scheduling; expect at least 4 ticks in 0.55s.
    assert fire_count["n"] >= 4


# ── Runtime: priority ordering ───────────────────────────────────────────────


@pytest.mark.asyncio
async def test_priority_ordering_when_workers_busy():
    """When workers are saturated, queued tasks come off in priority order."""
    completion_order: list[str] = []

    def make_run(name, sleep):
        async def _run(bb):
            await asyncio.sleep(sleep)
            completion_order.append(name)
            return None
        return _run

    # Block worker first with a long-running low-priority task; then queue
    # high-priority + medium-priority tasks. They should come off high-first.
    blocker = Specialist(name="blocker", watches=["start"], priority=50, run=make_run("blocker", 0.3))
    high = Specialist(name="high", watches=["queue_em"], priority=10, run=make_run("high", 0.05))
    mid = Specialist(name="mid", watches=["queue_em"], priority=30, run=make_run("mid", 0.05))

    rt = Runtime([blocker, high, mid], worker_count=1)  # single worker forces serialization

    async def driver():
        await asyncio.sleep(0.05)
        rt.blackboard.set("start", 1)         # blocker takes the worker
        await asyncio.sleep(0.05)
        rt.blackboard.set("queue_em", 1)      # mid + high queued; high should run first
        await asyncio.sleep(0.6)
        rt.blackboard.set(EXIT_KEY, True)

    await asyncio.gather(rt.run(max_runtime_seconds=2.0), driver())

    # Blocker first (it was running). Then high before mid by priority.
    assert completion_order == ["blocker", "high", "mid"]
