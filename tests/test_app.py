from __future__ import annotations

import asyncio
from datetime import date, datetime

from bjtu_rooms import app as app_module
from bjtu_rooms.models import SyncState
from bjtu_rooms.storage import get_connection, init_db, save_sync_state


def test_needs_startup_sync_uses_last_successful_date() -> None:
    today = date(2026, 9, 22)

    assert app_module._needs_startup_sync(SyncState(None, None, "never", ""), today)
    assert app_module._needs_startup_sync(
        SyncState(date(2026, 9, 21), datetime(2026, 9, 21, 8), "ok", ""),
        today,
    )
    assert not app_module._needs_startup_sync(
        SyncState(today, datetime(2026, 9, 22, 8), "error", "later attempt failed"),
        today,
    )


def test_lifespan_starts_one_sync_and_waits_for_it(monkeypatch, tmp_path) -> None:
    db_path = tmp_path / "rooms.sqlite3"
    events: list[str] = []
    release_sync = asyncio.Event()

    monkeypatch.setattr(app_module, "get_connection", lambda: get_connection(db_path))
    monkeypatch.setattr(app_module, "_current_local_date", lambda: date(2026, 9, 22))

    async def fake_startup_sync() -> None:
        events.append("started")
        await release_sync.wait()
        events.append("finished")

    monkeypatch.setattr(app_module, "_startup_sync", fake_startup_sync)

    async def exercise_lifespan() -> None:
        async with app_module.lifespan(object()):
            await asyncio.sleep(0)
            assert events == ["started"]

            async def release_after_context_exits() -> None:
                await asyncio.sleep(0)
                release_sync.set()

            asyncio.create_task(release_after_context_exits())

    asyncio.run(exercise_lifespan())

    assert events == ["started", "finished"]


def test_lifespan_skips_sync_after_success_today(monkeypatch, tmp_path) -> None:
    db_path = tmp_path / "rooms.sqlite3"
    conn = get_connection(db_path)
    init_db(conn)
    save_sync_state(
        conn,
        synced_day=date(2026, 9, 22),
        status="ok",
        message="done",
    )
    conn.close()
    calls = 0

    monkeypatch.setattr(app_module, "get_connection", lambda: get_connection(db_path))
    monkeypatch.setattr(app_module, "_current_local_date", lambda: date(2026, 9, 22))

    async def fake_startup_sync() -> None:
        nonlocal calls
        calls += 1

    monkeypatch.setattr(app_module, "_startup_sync", fake_startup_sync)

    async def exercise_lifespan() -> None:
        async with app_module.lifespan(object()):
            await asyncio.sleep(0)

    asyncio.run(exercise_lifespan())

    assert calls == 0


def test_status_includes_runtime_shutdown_time(monkeypatch, tmp_path) -> None:
    db_path = tmp_path / "rooms.sqlite3"
    monkeypatch.setattr(app_module, "get_connection", lambda: get_connection(db_path))
    shutdown_at = datetime.fromisoformat("2026-09-22T15:30:00+08:00")
    application = app_module.create_app(shutdown_at=shutdown_at)
    status_endpoint = next(
        route.endpoint for route in application.routes if getattr(route, "path", None) == "/api/status"
    )

    payload = status_endpoint()

    assert payload["runtime"] == {"shutdown_at": "2026-09-22T15:30:00+08:00"}


def test_status_returns_null_shutdown_time_when_disabled(monkeypatch, tmp_path) -> None:
    db_path = tmp_path / "rooms.sqlite3"
    monkeypatch.setattr(app_module, "get_connection", lambda: get_connection(db_path))
    application = app_module.create_app()
    status_endpoint = next(
        route.endpoint for route in application.routes if getattr(route, "path", None) == "/api/status"
    )

    payload = status_endpoint()

    assert payload["runtime"] == {"shutdown_at": None}
