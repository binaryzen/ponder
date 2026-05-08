"""Runtime: wires Blackboard + Dispatcher + Specialists; manages lifecycle.

Activation sources:
  - State change: when a specialist's watched key is written, the runtime
    evaluates that specialist's should_activate predicate and submits to the
    dispatcher if true.
  - Tick: specialists with tick_seconds set fire on a recurring timer.

Exit conditions:
  - blackboard["should_exit"] = True
  - asyncio.CancelledError (e.g., Ctrl+C)
  - max_runtime_seconds elapsed (safety cap)

Idle detection:
  - Reported via runtime.is_idle(); useful for tests and demos.
"""

from __future__ import annotations

import asyncio
import time
from typing import Iterable, Optional

from ponder.audit import (
    AuditEvent,
    EventType,
    current_parent_span_id,
    current_trace_id,
    emit,
    emit_pipeline_event,
    new_id,
    now_iso,
)
from ponder.orchestrator.blackboard import Blackboard, StateChange
from ponder.orchestrator.dispatcher import Dispatcher
from ponder.orchestrator.specialist import Specialist


EXIT_KEY = "should_exit"


class Runtime:
    def __init__(
        self,
        specialists: Iterable[Specialist],
        worker_count: int = 4,
        model_concurrency: int = 1,
    ) -> None:
        self.blackboard = Blackboard()
        self.dispatcher = Dispatcher(
            self.blackboard,
            worker_count=worker_count,
            model_concurrency=model_concurrency,
        )
        self.specialists: list[Specialist] = list(specialists)
        # Map of key -> list of specialists watching it.
        self._watchers: dict[str, list[Specialist]] = {}
        for sp in self.specialists:
            for key in sp.watches:
                self._watchers.setdefault(key, []).append(sp)
        self._tickers: list[Specialist] = [
            sp for sp in self.specialists if sp.tick_seconds is not None
        ]
        self._supervisor_tasks: list[asyncio.Task] = []

    # ── Lifecycle ───────────────────────────────────────────────────────────

    async def run(self, max_runtime_seconds: Optional[float] = None) -> None:
        """Run until exit flag, cancellation, or max_runtime exceeded."""
        if not current_trace_id.get():
            current_trace_id.set(new_id())
        turn_span = emit_pipeline_event(
            "runtime_started",
            payload={
                "specialists": [sp.name for sp in self.specialists],
                "worker_count": self.dispatcher._worker_count,
                "model_concurrency": self.dispatcher._model_sem._value,
            },
        )
        current_parent_span_id.set(turn_span)

        await self.dispatcher.start()
        # Wildcard subscription: dispatcher activates watching specialists on writes.
        change_q = self.blackboard.subscribe([])
        self._supervisor_tasks.append(asyncio.create_task(self._react_to_changes(change_q)))
        for sp in self._tickers:
            self._supervisor_tasks.append(asyncio.create_task(self._tick_loop(sp)))

        start = time.monotonic()
        try:
            while True:
                if self.blackboard.get(EXIT_KEY):
                    break
                if max_runtime_seconds is not None:
                    if time.monotonic() - start >= max_runtime_seconds:
                        break
                await asyncio.sleep(0.05)
        finally:
            for t in self._supervisor_tasks:
                t.cancel()
            await asyncio.gather(*self._supervisor_tasks, return_exceptions=True)
            self._supervisor_tasks.clear()
            await self.dispatcher.stop()
            emit_pipeline_event(
                "runtime_stopped",
                payload={
                    "elapsed_seconds": round(time.monotonic() - start, 3),
                    "exit_flag": bool(self.blackboard.get(EXIT_KEY)),
                },
            )

    def is_idle(self) -> bool:
        return self.dispatcher.idle

    # ── Reactions ───────────────────────────────────────────────────────────

    async def _react_to_changes(self, change_q: asyncio.Queue) -> None:
        while True:
            change: StateChange = await change_q.get()
            for sp in self._watchers.get(change.key, []):
                try:
                    fire = sp.should_activate(self.blackboard, change)
                except Exception as e:
                    emit(AuditEvent(
                        trace_id=current_trace_id.get() or "",
                        span_id=new_id(),
                        parent_span_id=current_parent_span_id.get() or None,
                        emitted_at=now_iso(),
                        event_type=EventType.PIPELINE,
                        region=sp.name,
                        domain="default",
                        notation_version=1,
                        payload={
                            "boundary": "predicate_failed",
                            "key": change.key,
                            "error": repr(e),
                        },
                    ))
                    continue
                if fire:
                    self.dispatcher.submit(sp, cause=f"key:{change.key}")

    async def _tick_loop(self, sp: Specialist) -> None:
        assert sp.tick_seconds is not None
        while True:
            await asyncio.sleep(sp.tick_seconds)
            self.dispatcher.submit(sp, cause="tick")
