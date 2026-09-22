from __future__ import annotations

import json
import sqlite3
from collections import defaultdict
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Any

from .models import Occupancy, Preference, Room, SyncState

ROOT_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = ROOT_DIR / "data"
DB_PATH = DATA_DIR / "rooms.sqlite3"
SETTINGS_PATH = DATA_DIR / "settings.json"


def get_connection(path: Path = DB_PATH) -> sqlite3.Connection:
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row
    return conn


def init_db(conn: sqlite3.Connection) -> None:
    conn.executescript(
        """
        create table if not exists rooms (
            id integer primary key autoincrement,
            raw_name text not null unique,
            building text not null,
            room text not null,
            campus text not null default ''
        );

        create table if not exists occupancies (
            id integer primary key autoincrement,
            room_id integer not null references rooms(id) on delete cascade,
            day text not null,
            start_period integer not null,
            end_period integer not null,
            source text not null default ''
        );

        create index if not exists idx_occupancies_day_room
            on occupancies(day, room_id);

        create table if not exists preferences (
            id integer primary key check (id = 1),
            preferred_buildings text not null,
            preferred_room_prefixes text not null
        );

        create table if not exists sync_state (
            id integer primary key check (id = 1),
            last_sync_date text,
            last_sync_at text,
            status text not null default 'never',
            message text not null default ''
        );
        """
    )
    conn.execute(
        """
        insert or ignore into preferences (id, preferred_buildings, preferred_room_prefixes)
        values (1, ?, ?)
        """,
        (json.dumps(["yf"]), json.dumps(["4", "5", "6"])),
    )
    conn.execute(
        """
        insert or ignore into sync_state (id, status, message)
        values (1, 'never', 'No sync has run yet.')
        """
    )
    conn.commit()


def load_settings(path: Path = SETTINGS_PATH) -> dict[str, Any]:
    if not path.exists():
        return {}
    return json.loads(path.read_text(encoding="utf-8"))


def save_settings(settings: dict[str, Any], path: Path = SETTINGS_PATH) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(settings, indent=2, ensure_ascii=False), encoding="utf-8")


def get_preference(conn: sqlite3.Connection) -> Preference:
    row = conn.execute("select * from preferences where id = 1").fetchone()
    if not row:
        return Preference()
    return Preference(
        preferred_buildings=tuple(json.loads(row["preferred_buildings"])),
        preferred_room_prefixes=tuple(json.loads(row["preferred_room_prefixes"])),
    )


def save_preference(conn: sqlite3.Connection, preference: Preference) -> None:
    conn.execute(
        """
        insert into preferences (id, preferred_buildings, preferred_room_prefixes)
        values (1, ?, ?)
        on conflict(id) do update set
            preferred_buildings = excluded.preferred_buildings,
            preferred_room_prefixes = excluded.preferred_room_prefixes
        """,
        (
            json.dumps(list(preference.preferred_buildings), ensure_ascii=False),
            json.dumps(list(preference.preferred_room_prefixes), ensure_ascii=False),
        ),
    )
    conn.commit()


def upsert_rooms_and_occupancies(
    conn: sqlite3.Connection,
    rooms: list[Room],
    occupancies: list[Occupancy],
    synced_day: date,
) -> None:
    with conn:
        for room in rooms:
            conn.execute(
                """
                insert into rooms (raw_name, building, room, campus)
                values (?, ?, ?, ?)
                on conflict(raw_name) do update set
                    building = excluded.building,
                    room = excluded.room,
                    campus = excluded.campus
                """,
                (room.raw_name, room.building, room.room, room.campus),
            )

        affected_days = {occupancy.day for occupancy in occupancies} or {synced_day}
        conn.executemany(
            "delete from occupancies where day = ?",
            [(day.isoformat(),) for day in affected_days],
        )
        room_ids = {
            row["raw_name"]: row["id"]
            for row in conn.execute("select id, raw_name from rooms").fetchall()
        }
        inserted_keys: set[tuple[str, date, int, int]] = set()
        for occupancy in occupancies:
            occupancy_key = (
                occupancy.raw_room_name,
                occupancy.day,
                occupancy.start_period,
                occupancy.end_period,
            )
            if occupancy_key in inserted_keys:
                continue
            inserted_keys.add(occupancy_key)
            room_id = room_ids.get(occupancy.raw_room_name)
            if room_id is None:
                continue
            conn.execute(
                """
                insert into occupancies (room_id, day, start_period, end_period, source)
                values (?, ?, ?, ?, ?)
                """,
                (
                    room_id,
                    occupancy.day.isoformat(),
                    occupancy.start_period,
                    occupancy.end_period,
                    occupancy.source,
                ),
            )


def occupancy_retention_window(reference_day: date) -> tuple[date, date]:
    week_start = reference_day - timedelta(days=reference_day.isoweekday() - 1)
    return week_start, week_start + timedelta(days=13)


def prune_occupancies_outside_retention_window(
    conn: sqlite3.Connection,
    reference_day: date,
) -> int:
    keep_start, keep_end = occupancy_retention_window(reference_day)
    cursor = conn.execute(
        """
        delete from occupancies
        where day < ? or day > ?
        """,
        (keep_start.isoformat(), keep_end.isoformat()),
    )
    conn.commit()
    return cursor.rowcount


def load_rooms(conn: sqlite3.Connection) -> list[Room]:
    rows = conn.execute(
        "select raw_name, building, room, campus from rooms order by building, room"
    ).fetchall()
    return [
        Room(
            raw_name=row["raw_name"],
            building=row["building"],
            room=row["room"],
            campus=row["campus"],
        )
        for row in rows
    ]


def load_occupancy_by_room(conn: sqlite3.Connection, day: date) -> dict[str, list[Occupancy]]:
    rows = conn.execute(
        """
        select rooms.raw_name, occupancies.day, occupancies.start_period,
               occupancies.end_period, occupancies.source
        from occupancies
        join rooms on rooms.id = occupancies.room_id
        where occupancies.day = ?
        """,
        (day.isoformat(),),
    ).fetchall()
    grouped: dict[str, list[Occupancy]] = defaultdict(list)
    for row in rows:
        grouped[row["raw_name"]].append(
            Occupancy(
                raw_room_name=row["raw_name"],
                day=date.fromisoformat(row["day"]),
                start_period=row["start_period"],
                end_period=row["end_period"],
                source=row["source"],
            )
        )
    return grouped


def get_sync_state(conn: sqlite3.Connection) -> SyncState:
    row = conn.execute("select * from sync_state where id = 1").fetchone()
    if not row:
        return SyncState(None, None, "never", "No sync has run yet.")
    return SyncState(
        last_sync_date=date.fromisoformat(row["last_sync_date"]) if row["last_sync_date"] else None,
        last_sync_at=datetime.fromisoformat(row["last_sync_at"]) if row["last_sync_at"] else None,
        status=row["status"],
        message=row["message"],
    )


def save_sync_state(
    conn: sqlite3.Connection,
    *,
    synced_day: date | None,
    status: str,
    message: str,
) -> None:
    conn.execute(
        """
        insert into sync_state (id, last_sync_date, last_sync_at, status, message)
        values (1, ?, ?, ?, ?)
        on conflict(id) do update set
            last_sync_date = coalesce(excluded.last_sync_date, sync_state.last_sync_date),
            last_sync_at = excluded.last_sync_at,
            status = excluded.status,
            message = excluded.message
        """,
        (
            synced_day.isoformat() if synced_day else None,
            datetime.now().isoformat(timespec="seconds"),
            status,
            message,
        ),
    )
    conn.commit()
