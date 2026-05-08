"""Tests for the simulation primitives in ponder.orchestrator.simulated."""

import asyncio
import time

import pytest

from ponder.orchestrator.simulated import LatencyProfile, PacingProfile


@pytest.mark.asyncio
async def test_latency_profile_fixed():
    profile = LatencyProfile(fixed_ms=50.0)
    start = time.monotonic()
    delay = await profile.wait()
    elapsed = (time.monotonic() - start) * 1000
    assert delay == pytest.approx(50.0)
    assert elapsed >= 45.0  # slight scheduler slack


@pytest.mark.asyncio
async def test_latency_profile_jitter_within_bounds():
    profile = LatencyProfile(fixed_ms=100.0, jitter_ms=20.0, seed=42)
    delays = [await profile.wait() for _ in range(5)]
    for d in delays:
        assert 80.0 <= d <= 120.0


@pytest.mark.asyncio
async def test_latency_profile_step_up():
    profile = LatencyProfile(fixed_ms=10.0, step_up_ms=5.0)
    d1 = await profile.wait()
    d2 = await profile.wait()
    d3 = await profile.wait()
    assert d1 == pytest.approx(10.0)
    assert d2 == pytest.approx(15.0)
    assert d3 == pytest.approx(20.0)


@pytest.mark.asyncio
async def test_latency_profile_seed_reproducible():
    a = LatencyProfile(fixed_ms=100.0, jitter_ms=50.0, seed=7)
    b = LatencyProfile(fixed_ms=100.0, jitter_ms=50.0, seed=7)
    a_delays = [await a.wait() for _ in range(3)]
    b_delays = [await b.wait() for _ in range(3)]
    assert a_delays == b_delays


@pytest.mark.asyncio
async def test_latency_profile_no_negative_sleep():
    """Even with extreme negative jitter, wait() never sleeps a negative duration."""
    profile = LatencyProfile(fixed_ms=10.0, jitter_ms=100.0, seed=0)
    for _ in range(20):
        delay = await profile.wait()
        assert delay >= 0


@pytest.mark.asyncio
async def test_pacing_profile_streams_chunks():
    pacing = PacingProfile(chunk_count=3, inter_chunk_ms=20, inter_chunk_jitter=5)
    received: list = []

    def on_chunk(idx, chunk):
        received.append((idx, chunk))

    await pacing.stream(["a", "b", "c"], on_chunk)
    assert received == [(0, "a"), (1, "b"), (2, "c")]


@pytest.mark.asyncio
async def test_pacing_profile_respects_chunk_count_cap():
    pacing = PacingProfile(chunk_count=2, inter_chunk_ms=5)
    received = []
    await pacing.stream(["a", "b", "c", "d"], lambda i, c: received.append(c))
    assert received == ["a", "b"]


@pytest.mark.asyncio
async def test_pacing_profile_respects_supplied_chunks_cap():
    pacing = PacingProfile(chunk_count=10, inter_chunk_ms=5)
    received = []
    await pacing.stream(["a", "b"], lambda i, c: received.append(c))
    assert received == ["a", "b"]


@pytest.mark.asyncio
async def test_pacing_profile_async_callback():
    pacing = PacingProfile(chunk_count=2, inter_chunk_ms=5)
    received = []

    async def on_chunk(idx, chunk):
        await asyncio.sleep(0.01)
        received.append(chunk)

    await pacing.stream(["x", "y"], on_chunk)
    assert received == ["x", "y"]


@pytest.mark.asyncio
async def test_pacing_profile_burst_pause_added_at_burst_boundary():
    """With burst_size=2 and pause=200ms, after 2 chunks there's an extra pause."""
    pacing = PacingProfile(
        chunk_count=4,
        inter_chunk_ms=10,
        inter_chunk_jitter=0,
        burst_size=2,
        burst_pause_ms=100,
    )
    timings = []

    async def on_chunk(idx, chunk):
        timings.append(time.monotonic())

    start = time.monotonic()
    await pacing.stream(["a", "b", "c", "d"], on_chunk)

    # Chunks 0, 1 emitted at ~10, 20ms; chunk 2 should hit ~130ms (extra burst pause); chunk 3 ~140ms
    elapsed_chunks = [(t - start) * 1000 for t in timings]
    assert elapsed_chunks[1] < elapsed_chunks[2]
    # Chunk 2 should be at least 100ms later than chunk 1 (the burst pause).
    assert elapsed_chunks[2] - elapsed_chunks[1] >= 100
