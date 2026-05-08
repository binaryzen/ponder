"""Simulation primitives for mock specialists.

Encapsulates the kinds of latency / pacing patterns we'll exercise repeatedly
when iterating on orchestration scenarios. Specialists pass these into their
``run`` closures rather than hardcoding sleeps.

Patterns covered:

  - LatencyProfile  — a single delay (constant, jittered, or step-up)
  - PacingProfile   — produce chunks over time at a configurable rate
  - WorkloadProfile — multi-phase mock work (acquire, think, emit, release)

These are the building blocks for "what does a specialist's runtime cost
shape look like?" without needing to wire to a real model.
"""

from __future__ import annotations

import asyncio
import random
from dataclasses import dataclass, field
from typing import Awaitable, Callable, Sequence


# ── LatencyProfile ───────────────────────────────────────────────────────────

@dataclass
class LatencyProfile:
    """A single simulated wait. Configurable shape.

    fixed_ms     — base latency
    jitter_ms    — uniform ± jitter on top of base
    step_up_ms   — incremental increase added each call (warm-up simulation)
    seed         — optional rng seed for reproducible jitter
    """

    fixed_ms: float = 0.0
    jitter_ms: float = 0.0
    step_up_ms: float = 0.0
    seed: int | None = None

    _rng: random.Random = field(init=False, repr=False)
    _calls: int = field(init=False, default=0, repr=False)

    def __post_init__(self) -> None:
        self._rng = random.Random(self.seed) if self.seed is not None else random.Random()

    async def wait(self) -> float:
        """Sleep per profile. Returns the actual delay in milliseconds."""
        delay = self.fixed_ms + self._calls * self.step_up_ms
        if self.jitter_ms > 0:
            delay += self._rng.uniform(-self.jitter_ms, self.jitter_ms)
        delay = max(0.0, delay)
        self._calls += 1
        await asyncio.sleep(delay / 1000.0)
        return delay


# Common pre-configured profiles for legibility in demos.
NO_LATENCY = LatencyProfile()
FAST_LOCAL = LatencyProfile(fixed_ms=50.0, jitter_ms=10.0)
TYPICAL_MODEL = LatencyProfile(fixed_ms=400.0, jitter_ms=80.0)
SLOW_MODEL = LatencyProfile(fixed_ms=1500.0, jitter_ms=300.0)
COLD_START = LatencyProfile(fixed_ms=5000.0, jitter_ms=500.0, step_up_ms=-200.0)  # warms up


# ── PacingProfile ────────────────────────────────────────────────────────────

@dataclass
class PacingProfile:
    """Produces chunks one at a time, with configurable inter-chunk pacing.

    Useful when a specialist's job is to *stream* output to a queue rather
    than emit it as one big result.

    chunk_count       — total chunks to produce
    inter_chunk_ms    — base delay between chunks
    inter_chunk_jitter— uniform ± jitter on inter-chunk delay
    burst_size        — emit this many chunks per "burst" before pausing
    burst_pause_ms    — extra delay between bursts (in addition to inter_chunk)
    """

    chunk_count: int = 4
    inter_chunk_ms: float = 800.0
    inter_chunk_jitter: float = 100.0
    burst_size: int = 0  # 0 = no bursting; emit one at a time
    burst_pause_ms: float = 0.0
    seed: int | None = None

    _rng: random.Random = field(init=False, repr=False)

    def __post_init__(self) -> None:
        self._rng = random.Random(self.seed) if self.seed is not None else random.Random()

    async def stream(
        self,
        chunks: Sequence,
        on_chunk: Callable[[int, object], Awaitable[None] | None],
    ) -> None:
        """Walk through ``chunks`` calling ``on_chunk(index, chunk)`` for each.

        The supplied chunks list overrides chunk_count if shorter; otherwise
        chunk_count caps the iteration.
        """
        n = min(len(chunks), self.chunk_count) if self.chunk_count else len(chunks)
        for i in range(n):
            delay = self.inter_chunk_ms + self._rng.uniform(
                -self.inter_chunk_jitter, self.inter_chunk_jitter
            )
            if self.burst_size and i > 0 and i % self.burst_size == 0:
                delay += self.burst_pause_ms
            await asyncio.sleep(max(0.0, delay) / 1000.0)
            result = on_chunk(i, chunks[i])
            if asyncio.iscoroutine(result):
                await result
