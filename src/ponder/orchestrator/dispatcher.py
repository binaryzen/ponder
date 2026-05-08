"""Priority-dispatching worker pool.

Holds an asyncio.PriorityQueue of pending activations. A configurable number
of workers pull from the queue concurrently. A separate semaphore gates
specialists that declare ``needs_model=True`` so they don't all hammer the
single LLM resource at once.
"""

from __future__ import annotations

import asyncio
import inspect
import itertools
import time
from dataclasses import dataclass, field
from typing import Optional

from ponder.audit import (
    AuditEvent,
    EventType,
    current_parent_span_id,
    current_trace_id,
    emit,
    new_id,
    now_iso,
)
from ponder.orchestrator.blackboard import Blackboard
from ponder.orchestrator.specialist import Specialist


@dataclass(order=True)
class _Activation:
    """Queue entry. Compared by (priority, seq) so equal priority is FIFO."""

    priority: int
    seq: int
    specialist: Specialist = field(compare=False)
    cause: str = field(default="", compare=False)  # short reason: "tick", "key:foo"


class Dispatcher:
    def __init__(
        self,
        blackboard: Blackboard,
        worker_count: int = 4,
        model_concurrency: int = 1,
    ) -> None:
        self._bb = blackboard
        self._queue: asyncio.PriorityQueue[_Activation] = asyncio.PriorityQueue()
        self._worker_count = worker_count
        self._model_sem = asyncio.Semaphore(model_concurrency)
        self._seq = itertools.count()
        self._workers: list[asyncio.Task] = []
        self._in_flight = 0

    # ── Lifecycle ───────────────────────────────────────────────────────────

    async def start(self) -> None:
        for i in range(self._worker_count):
            self._workers.append(asyncio.create_task(self._worker_loop(i)))

    async def stop(self) -> None:
        for w in self._workers:
            w.cancel()
        await asyncio.gather(*self._workers, return_exceptions=True)
        self._workers.clear()

    @property
    def idle(self) -> bool:
        return self._queue.empty() and self._in_flight == 0

    # ── Submission ──────────────────────────────────────────────────────────

    def submit(self, specialist: Specialist, cause: str = "") -> None:
        activation = _Activation(
            priority=specialist.priority,
            seq=next(self._seq),
            specialist=specialist,
            cause=cause,
        )
        self._queue.put_nowait(activation)

    # ── Worker loop ─────────────────────────────────────────────────────────

    async def _worker_loop(self, worker_id: int) -> None:
        while True:
            activation = await self._queue.get()
            self._in_flight += 1
            try:
                await self._execute(activation, worker_id)
            finally:
                self._in_flight -= 1
                self._queue.task_done()

    async def _execute(self, activation: _Activation, worker_id: int) -> None:
        sp = activation.specialist
        span_id = new_id()
        start_ts = now_iso()
        start_mono = time.monotonic()

        emit(AuditEvent(
            trace_id=current_trace_id.get() or "",
            span_id=span_id,
            parent_span_id=current_parent_span_id.get() or None,
            emitted_at=start_ts,
            event_type=EventType.PIPELINE,
            region=sp.name,
            domain="default",
            notation_version=1,
            payload={
                "boundary": "specialist_activated",
                "cause": activation.cause,
                "priority": sp.priority,
                "needs_model": sp.needs_model,
                "worker_id": worker_id,
            },
        ))

        # Optionally hold the model semaphore for the duration of run().
        async def do_run() -> Optional[dict]:
            result = sp.run(self._bb)
            if inspect.isawaitable(result):
                return await result
            return result

        try:
            if sp.needs_model:
                async with self._model_sem:
                    updates = await do_run()
            else:
                updates = await do_run()
        except Exception as e:
            emit(AuditEvent(
                trace_id=current_trace_id.get() or "",
                span_id=new_id(),
                parent_span_id=span_id,
                emitted_at=now_iso(),
                event_type=EventType.PIPELINE,
                region=sp.name,
                domain="default",
                notation_version=1,
                payload={
                    "boundary": "specialist_failed",
                    "error": repr(e),
                    "duration_ms": round((time.monotonic() - start_mono) * 1000, 2),
                },
            ))
            return

        if updates:
            self._bb.update(updates)

        emit(AuditEvent(
            trace_id=current_trace_id.get() or "",
            span_id=new_id(),
            parent_span_id=span_id,
            emitted_at=now_iso(),
            event_type=EventType.PIPELINE,
            region=sp.name,
            domain="default",
            notation_version=1,
            payload={
                "boundary": "specialist_completed",
                "duration_ms": round((time.monotonic() - start_mono) * 1000, 2),
                "writes": list(updates.keys()) if updates else [],
            },
        ))
