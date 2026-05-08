"""Specialist protocol — components that watch the blackboard and act on it.

A specialist declares:
  - name        : for audit / debugging
  - watches     : which blackboard keys it cares about (empty list = none / cron-only)
  - priority    : lower numbers run first when contending for dispatch
  - needs_model : whether it must hold the model semaphore while running

It implements:
  - should_activate(blackboard, change) -> bool
        Predicate evaluated when a watched key changes. Default: always True.
  - run(blackboard) -> dict | None
        The actual work. May be async. Returns a dict of blackboard updates,
        or None if no updates. Allowed to await arbitrary I/O.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Awaitable, Callable, Optional

from ponder.orchestrator.blackboard import Blackboard, StateChange


# Lower number = higher priority (asyncio.PriorityQueue is a min-heap).
DEFAULT_PRIORITY = 50


@dataclass
class Specialist:
    name: str
    watches: list[str] = field(default_factory=list)
    priority: int = DEFAULT_PRIORITY
    needs_model: bool = False
    # Sync or async; the runtime awaits coroutines automatically.
    run: Callable[[Blackboard], Optional[dict] | Awaitable[Optional[dict]]] = None
    # Sync predicate; evaluated synchronously when a watched key changes.
    should_activate: Callable[[Blackboard, StateChange], bool] = lambda bb, change: True
    # Tick interval in seconds; if set, the specialist also fires on a timer.
    tick_seconds: Optional[float] = None

    def __post_init__(self) -> None:
        if self.run is None:
            raise ValueError(f"Specialist {self.name!r} must provide a run() callable")
