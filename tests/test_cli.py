from __future__ import annotations

import asyncio

import pytest

from bjtu_rooms import cli


def test_parser_defaults_to_thirty_minute_shutdown() -> None:
    args = cli.build_parser().parse_args([])

    assert args.shutdown_after_minutes == 30


def test_parser_accepts_custom_and_disabled_shutdown() -> None:
    custom = cli.build_parser().parse_args(["--shutdown-after-minutes", "45"])
    disabled = cli.build_parser().parse_args(["--shutdown-after-minutes", "0"])

    assert custom.shutdown_after_minutes == 45
    assert disabled.shutdown_after_minutes == 0


def test_parser_rejects_negative_shutdown() -> None:
    with pytest.raises(SystemExit):
        cli.build_parser().parse_args(["--shutdown-after-minutes", "-1"])


def test_shutdown_timer_requests_server_exit() -> None:
    class FakeServer:
        should_exit = False

    server = FakeServer()

    asyncio.run(cli._request_shutdown_after(server, 0))

    assert server.should_exit is True


def test_serve_cancels_shutdown_timer_when_server_stops_early(monkeypatch) -> None:
    events: list[str] = []

    class FakeServer:
        async def serve(self) -> None:
            await asyncio.sleep(0)

    async def fake_shutdown_after(server, delay_seconds: float) -> None:
        events.append("started")
        try:
            await asyncio.Event().wait()
        finally:
            events.append("cancelled")

    monkeypatch.setattr(cli, "_request_shutdown_after", fake_shutdown_after)

    asyncio.run(cli._serve_with_shutdown(FakeServer(), 60))

    assert events == ["started", "cancelled"]
