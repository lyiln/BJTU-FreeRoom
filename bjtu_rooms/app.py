from __future__ import annotations

import asyncio
from contextlib import asynccontextmanager
from dataclasses import asdict
from datetime import date, datetime
from pathlib import Path

from fastapi import FastAPI, HTTPException, Query
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from .core import building_label, search_empty_rooms, validate_period_range
from .credentials import CredentialError, get_username, save_credentials
from .models import MAX_PERIOD, Preference, SyncState
from .storage import (
    ROOT_DIR,
    get_connection,
    get_preference,
    get_sync_state,
    init_db,
    load_occupancy_by_room,
    load_rooms,
    prune_occupancies_outside_retention_window,
    save_preference,
)
from .sync import sync_today

STATIC_DIR = ROOT_DIR / "static"


class PreferencePayload(BaseModel):
    preferred_buildings: list[str] = Field(default_factory=lambda: ["yf"])
    preferred_room_prefixes: list[str] = Field(default_factory=lambda: ["4", "5", "6"])


class CredentialPayload(BaseModel):
    username: str
    password: str


@asynccontextmanager
async def lifespan(app: FastAPI):
    current_day = _current_local_date()
    conn = get_connection()
    init_db(conn)
    prune_occupancies_outside_retention_window(conn, current_day)
    state = get_sync_state(conn)
    conn.close()
    startup_sync_task: asyncio.Task[None] | None = None
    if _needs_startup_sync(state, current_day):
        startup_sync_task = asyncio.create_task(_startup_sync())
    try:
        yield
    finally:
        if startup_sync_task is not None:
            await startup_sync_task


async def _startup_sync() -> None:
    try:
        await sync_today()
    except Exception:
        pass


def _current_local_date() -> date:
    return date.today()


def _needs_startup_sync(state: SyncState, current_day: date) -> bool:
    return state.last_sync_date != current_day


def create_app(shutdown_at: datetime | None = None) -> FastAPI:
    app = FastAPI(title="BJTU Room Finder", lifespan=lifespan)
    app.state.shutdown_at = shutdown_at
    app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")

    @app.get("/")
    def index() -> FileResponse:
        return FileResponse(STATIC_DIR / "index.html")

    @app.get("/api/status")
    def status():
        conn = get_connection()
        init_db(conn)
        sync_state = get_sync_state(conn)
        rooms_count = conn.execute("select count(*) as count from rooms").fetchone()["count"]
        conn.close()
        return {
            "sync": {
                "last_sync_date": sync_state.last_sync_date.isoformat()
                if sync_state.last_sync_date
                else None,
                "last_sync_at": sync_state.last_sync_at.isoformat()
                if sync_state.last_sync_at
                else None,
                "status": sync_state.status,
                "message": sync_state.message,
            },
            "runtime": {
                "shutdown_at": app.state.shutdown_at.isoformat()
                if app.state.shutdown_at
                else None,
            },
            "rooms_count": rooms_count,
            "has_username": bool(get_username()),
        }

    @app.get("/api/buildings")
    def buildings():
        conn = get_connection()
        init_db(conn)
        rooms = load_rooms(conn)
        conn.close()
        seen: set[str] = set()
        items = []
        for room in sorted(rooms, key=lambda item: (item.building, item.room)):
            building = room.building.lower()
            if not building or building in seen:
                continue
            seen.add(building)
            label = building_label(building)
            items.append(
                {
                    "value": building,
                    "label": f"{label} ({building.upper()})" if label != building else building.upper(),
                }
            )
        return {"items": items}

    @app.get("/api/search")
    def search(
        date_: date = Query(alias="date"),
        start_period: int = Query(ge=1, le=MAX_PERIOD),
        end_period: int = Query(ge=1, le=MAX_PERIOD),
        building: str | None = None,
    ):
        try:
            validate_period_range(start_period, end_period)
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

        conn = get_connection()
        init_db(conn)
        rooms = load_rooms(conn)
        occupancy_by_room = load_occupancy_by_room(conn, date_)
        preference = get_preference(conn)
        conn.close()

        results = search_empty_rooms(
            rooms,
            occupancy_by_room,
            date_,
            start_period,
            end_period,
            preference,
            building_filter=building,
        )
        return {"items": [asdict(item) for item in results], "count": len(results)}

    @app.get("/api/preferences")
    def read_preferences():
        conn = get_connection()
        init_db(conn)
        preference = get_preference(conn)
        conn.close()
        return {
            "preferred_buildings": list(preference.preferred_buildings),
            "preferred_room_prefixes": list(preference.preferred_room_prefixes),
        }

    @app.put("/api/preferences")
    def update_preferences(payload: PreferencePayload):
        preference = Preference(
            preferred_buildings=tuple(_clean_items(payload.preferred_buildings)),
            preferred_room_prefixes=tuple(_clean_items(payload.preferred_room_prefixes)),
        )
        conn = get_connection()
        init_db(conn)
        save_preference(conn, preference)
        conn.close()
        return {"ok": True}

    @app.post("/api/credentials")
    def update_credentials(payload: CredentialPayload):
        try:
            save_credentials(payload.username, payload.password)
        except CredentialError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        return {"ok": True, "username": payload.username}

    @app.post("/api/sync")
    async def sync(headed: bool = False):
        try:
            message = await sync_today(headed=headed)
        except Exception as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        return {"ok": True, "message": message}

    return app


def _clean_items(items: list[str]) -> list[str]:
    return [item.strip().lower() for item in items if item.strip()]


app = create_app()
