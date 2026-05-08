"""Async-aware blackboard with subscription-driven activation.

Components watch keys; writes notify watchers via an asyncio.Queue of
(key, old_value, new_value) tuples. Watchers decide whether to act.
"""

from __future__ import annotations

import asyncio
import time
from dataclasses import dataclass
from typing import Any, Callable, Iterable, Optional


@dataclass
class StateChange:
    key: str
    old_value: Any
    new_value: Any
    written_at: float  # monotonic seconds, for ordering


class Blackboard:
    """In-memory async-safe state container with subscription notification.

    Reads and writes are O(1) dict operations; subscription notification is
    O(subscribers) per write. The whole runtime is single-event-loop, so no
    locks needed — asyncio's cooperative scheduling guarantees atomicity at
    await boundaries.
    """

    def __init__(self) -> None:
        self._state: dict[str, Any] = {}
        # subscribers[key] = list of asyncio.Queue
        self._subscribers: dict[str, list[asyncio.Queue]] = {}
        # Wildcard subscribers see all changes (for the dispatcher).
        self._wildcard: list[asyncio.Queue] = []

    # ── Read / write ────────────────────────────────────────────────────────

    def get(self, key: str, default: Any = None) -> Any:
        return self._state.get(key, default)

    def set(self, key: str, value: Any) -> StateChange:
        """Write a value; notify any subscribers. Returns the StateChange."""
        old = self._state.get(key)
        self._state[key] = value
        change = StateChange(
            key=key, old_value=old, new_value=value, written_at=time.monotonic()
        )
        self._notify(change)
        return change

    def update(self, updates: dict[str, Any]) -> list[StateChange]:
        """Atomic-feeling batch update. Notifies subscribers per key."""
        return [self.set(k, v) for k, v in updates.items()]

    def keys(self) -> Iterable[str]:
        return self._state.keys()

    def snapshot(self) -> dict[str, Any]:
        return dict(self._state)

    # ── Subscription ────────────────────────────────────────────────────────

    def subscribe(self, keys: Iterable[str]) -> asyncio.Queue:
        """Subscribe to writes on specific keys. Returns a queue; consume StateChange items.

        Pass an empty iterable to subscribe to *all* writes.
        """
        q: asyncio.Queue = asyncio.Queue()
        keys_list = list(keys)
        if not keys_list:
            self._wildcard.append(q)
        else:
            for k in keys_list:
                self._subscribers.setdefault(k, []).append(q)
        return q

    def _notify(self, change: StateChange) -> None:
        for q in self._subscribers.get(change.key, []):
            q.put_nowait(change)
        for q in self._wildcard:
            q.put_nowait(change)
