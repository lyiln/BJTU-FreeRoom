from __future__ import annotations

import argparse
import asyncio
from contextlib import suppress
from datetime import datetime, timedelta
import logging
import webbrowser

import uvicorn

from .app import create_app

DEFAULT_SHUTDOWN_AFTER_MINUTES = 30


def _non_negative_int(value: str) -> int:
    parsed = int(value)
    if parsed < 0:
        raise argparse.ArgumentTypeError("must be zero or greater")
    return parsed


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Start the BJTU local room finder.")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", default=8000, type=int)
    parser.add_argument("--no-browser", action="store_true")
    parser.add_argument(
        "--shutdown-after-minutes",
        default=DEFAULT_SHUTDOWN_AFTER_MINUTES,
        type=_non_negative_int,
        help="Stop the local service after this many minutes; use 0 to disable (default: 30).",
    )
    return parser


async def _request_shutdown_after(server: uvicorn.Server, delay_seconds: float) -> None:
    await asyncio.sleep(delay_seconds)
    logging.getLogger("uvicorn.error").info("Automatic shutdown time reached")
    server.should_exit = True


async def _serve_with_shutdown(
    server: uvicorn.Server,
    shutdown_after_seconds: float,
) -> None:
    shutdown_task: asyncio.Task[None] | None = None
    if shutdown_after_seconds > 0:
        shutdown_task = asyncio.create_task(
            _request_shutdown_after(server, shutdown_after_seconds)
        )
    try:
        await server.serve()
    finally:
        if shutdown_task is not None:
            shutdown_task.cancel()
            with suppress(asyncio.CancelledError):
                await shutdown_task


def main() -> None:
    args = build_parser().parse_args()

    shutdown_after_seconds = args.shutdown_after_minutes * 60
    shutdown_at = None
    if shutdown_after_seconds > 0:
        shutdown_at = datetime.now().astimezone() + timedelta(seconds=shutdown_after_seconds)

    application = create_app(shutdown_at=shutdown_at)
    config = uvicorn.Config(
        application,
        host=args.host,
        port=args.port,
        reload=False,
    )
    server = uvicorn.Server(config)

    url = f"http://{args.host}:{args.port}"
    if not args.no_browser:
        webbrowser.open(url)
    asyncio.run(_serve_with_shutdown(server, shutdown_after_seconds))


if __name__ == "__main__":
    main()
