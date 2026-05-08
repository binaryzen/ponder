"""FastAPI app for the diagnostic panel.

Embedded into the same Python process as the runtime so it can read state
directly via the StateStore + ContextService instances passed in. No HTTP
hop into the orchestrator process.

Endpoints:

  GET  /                       serves the panel HTML
  GET  /api/snapshot           components + full component state + context snapshot
  GET  /api/events             paginated audit events (cursor-based; for backfill)
  GET  /api/state/stream       SSE — state-change events as they happen
  GET  /api/events/stream      SSE — audit events as they arrive (live tail)
  POST /api/input              writes panel-supplied text into a designated input URN
  POST /api/interrupt          writes a user_interrupt URN
  GET  /api/health             status / specialist count / audit stream info
"""

from __future__ import annotations

import asyncio
import json
import threading
from pathlib import Path
from typing import Any

from fastapi import FastAPI
from fastapi.responses import HTMLResponse, StreamingResponse
from pydantic import BaseModel

from ponder.audit import service as audit_service
from ponder.orchestrator.runtime import Runtime
from ponder.orchestrator.state import (
    ContextService,
    StateStore,
    component_urn,
)


PANEL_HTML_PATH = Path(__file__).with_name("panel.html")


class InputPayload(BaseModel):
    text: str


class InterruptPayload(BaseModel):
    reason: str = "panel-issued"


def create_app(
    runtime: Runtime,
    state_store: StateStore,
    context_service: ContextService,
    input_urn_owner: str = "panel",
    input_urn_key: str = "request",
    interrupt_urn_owner: str = "user",
    interrupt_urn_key: str = "interrupt",
) -> FastAPI:
    """Build a FastAPI app bound to the given runtime + state + context.

    Caller wires this to the same event loop as the runtime.
    """
    app = FastAPI(title="Ponder Diagnostics", docs_url="/api/docs")

    @app.get("/", response_class=HTMLResponse)
    async def index() -> str:
        return PANEL_HTML_PATH.read_text(encoding="utf-8")

    @app.get("/api/snapshot")
    async def snapshot() -> dict[str, Any]:
        # Component descriptors (static — registered at runtime construction time).
        components = [
            {
                "name": sp.name,
                "watches": list(sp.watches),
                "priority": sp.priority,
                "needs_model": sp.needs_model,
                "tick_seconds": sp.tick_seconds,
            }
            for sp in runtime.specialists
        ]
        # All component-namespaced state, flat by URN.
        state = state_store.items_with_prefix("component:")
        # Computed context view across all registered providers.
        context = context_service.snapshot()
        return {"components": components, "state": state, "context": context}

    @app.get("/api/events")
    async def events(after: str = "0", limit: int = 100) -> dict[str, Any]:
        """Paginated audit events. Used for initial backfill on connect."""
        return audit_service.list_events(after=after, limit=limit)

    @app.get("/api/state/stream")
    async def state_stream() -> StreamingResponse:
        """SSE stream of blackboard state changes (component:* and context:* writes).

        New EventSource connection = new subscription queue. Each connected
        client gets every change written after they subscribe.
        """
        async def gen():
            queue = state_store.blackboard.subscribe([])
            yield ": connected\n\n"
            try:
                while True:
                    change = await queue.get()
                    payload = {
                        "key": change.key,
                        "value": change.new_value,
                    }
                    yield f"data: {json.dumps(payload, default=str)}\n\n"
            except asyncio.CancelledError:
                raise

        return StreamingResponse(
            gen(),
            media_type="text/event-stream",
            headers={
                "Cache-Control": "no-cache",
                "X-Accel-Buffering": "no",
                "Connection": "keep-alive",
            },
        )

    @app.get("/api/events/stream")
    async def events_stream() -> StreamingResponse:
        """SSE stream of audit events as they arrive in the Redis stream.

        Wraps the sync `audit_service.tail_events` in a thread executor so the
        FastAPI event loop stays unblocked. Per-connection thread; daemon, so
        process exit cleans up.
        """
        async def gen():
            loop = asyncio.get_running_loop()
            event_queue: asyncio.Queue = asyncio.Queue()
            stop_flag = threading.Event()

            def worker() -> None:
                try:
                    for evt in audit_service.tail_events(after="$", block_ms=1000):
                        if stop_flag.is_set():
                            break
                        try:
                            asyncio.run_coroutine_threadsafe(event_queue.put(evt), loop)
                        except RuntimeError:
                            break
                except Exception:
                    pass

            thread = threading.Thread(target=worker, daemon=True)
            thread.start()
            yield ": connected\n\n"
            try:
                while True:
                    evt = await event_queue.get()
                    yield f"data: {json.dumps(evt, default=str)}\n\n"
            except asyncio.CancelledError:
                stop_flag.set()
                raise

        return StreamingResponse(
            gen(),
            media_type="text/event-stream",
            headers={
                "Cache-Control": "no-cache",
                "X-Accel-Buffering": "no",
                "Connection": "keep-alive",
            },
        )

    @app.post("/api/input")
    async def submit_input(payload: InputPayload) -> dict[str, Any]:
        """Write the panel-supplied text to the designated input URN.

        Default: writes to component:panel:request. The runtime's
        input-bridge specialist watches that URN and forwards into the
        cognitive pipeline.
        """
        change = state_store.write(input_urn_owner, input_urn_key, payload.text)
        return {"ok": True, "wrote": change.key, "value": payload.text}

    @app.post("/api/interrupt")
    async def submit_interrupt(payload: InterruptPayload) -> dict[str, Any]:
        change = state_store.write(interrupt_urn_owner, interrupt_urn_key, payload.reason)
        return {"ok": True, "wrote": change.key, "value": payload.reason}

    @app.get("/api/health")
    async def health() -> dict[str, Any]:
        return {
            "ok": True,
            "specialists": len(runtime.specialists),
            "registered_context_urns": len(context_service.registered_urns()),
            "audit_stream": audit_service.stream_info(),
        }

    return app
