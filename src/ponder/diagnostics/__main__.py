"""Launch the diagnostic panel: orchestrator runtime + FastAPI server in one process.

Usage:
    python -m ponder.diagnostics                        # default runtime, port 8080
    python -m ponder.diagnostics --runtime persuasion   # persuasion demo runtime
    python -m ponder.diagnostics --port 9090

Open http://localhost:8080/ in a browser.
"""

from __future__ import annotations

import argparse
import asyncio
import logging
import sys

import uvicorn

from ponder.audit import current_trace_id, new_id
from ponder.diagnostics.runtime_factory import build_panel_runtime
from ponder.diagnostics.persuasion_runtime import build_persuasion_runtime
from ponder.diagnostics.server import create_app

_RUNTIMES = {
    "panel": build_panel_runtime,
    "persuasion": build_persuasion_runtime,
}


async def run_all(host: str, port: int, max_seconds: float | None, runtime: str) -> None:
    current_trace_id.set(new_id())
    rt, state, context = _RUNTIMES[runtime]()
    await context.start()

    app = create_app(rt, state, context)
    config = uvicorn.Config(app, host=host, port=port, log_level="warning", access_log=False)
    server = uvicorn.Server(config)

    print(f"\n  Diagnostic panel:  http://{host}:{port}/")
    print(f"  runtime:           {runtime}")
    print(f"  trace_id:          {current_trace_id.get()}")
    print(f"  specialists:       {[sp.name for sp in rt.specialists]}")
    print(f"  Ctrl+C to stop.\n")

    runtime_task = asyncio.create_task(
        rt.run(max_runtime_seconds=max_seconds)
    )
    server_task = asyncio.create_task(server.serve())

    try:
        # Stop when either ends (or on Ctrl+C).
        done, pending = await asyncio.wait(
            [runtime_task, server_task],
            return_when=asyncio.FIRST_COMPLETED,
        )
        for t in pending:
            t.cancel()
    finally:
        # Make sure runtime exit flag is set so its loop terminates.
        rt.blackboard.set("should_exit", True)
        await context.stop()
        await asyncio.gather(runtime_task, server_task, return_exceptions=True)


def main() -> None:
    parser = argparse.ArgumentParser(description="Run the Ponder diagnostic panel.")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8080)
    parser.add_argument(
        "--runtime",
        choices=list(_RUNTIMES),
        default="panel",
        help="Which runtime to wire behind the panel (default: panel).",
    )
    parser.add_argument(
        "--max-seconds",
        type=float,
        default=None,
        help="Optional cap on runtime lifetime (default: run until interrupted).",
    )
    args = parser.parse_args()

    logging.basicConfig(level=logging.WARNING, format="%(message)s")

    try:
        asyncio.run(run_all(args.host, args.port, args.max_seconds, args.runtime))
    except KeyboardInterrupt:
        print("\nstopped.", file=sys.stderr)


if __name__ == "__main__":
    main()
