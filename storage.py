import sqlite3
import time
from datetime import datetime, timezone
from pathlib import Path

from episodes import EpisodeTracker


DB_PATH = (
    Path(__file__).resolve().parent
    / "data"
    / "dv_monitor.db"
)


class Storage:
    def __init__(self):
        self._last_saved_time = None

        DB_PATH.parent.mkdir(
            parents=True,
            exist_ok=True,
        )

        with self._connect() as connection:
            connection.execute(
                "PRAGMA journal_mode=WAL"
            )

            connection.executescript("""
                CREATE TABLE IF NOT EXISTS measurements (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    received_at TEXT NOT NULL,
                    voltage REAL NOT NULL,
                    current_ma REAL NOT NULL,
                    power_mw REAL NOT NULL,
                    state TEXT NOT NULL,
                    energy_wh REAL NOT NULL
                );

                CREATE TABLE IF NOT EXISTS events (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    received_at TEXT NOT NULL,
                    kind TEXT NOT NULL,
                    detail TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS totals (
                    id INTEGER PRIMARY KEY CHECK (id = 1),
                    energy_wh REAL NOT NULL
                );

                INSERT OR IGNORE INTO totals (
                    id, energy_wh
                )
                VALUES (1, 0);
            """)

            EpisodeTracker.initialize(connection)

    @staticmethod
    def _connect():
        connection = sqlite3.connect(
            DB_PATH,
            timeout=10,
        )

        connection.execute(
            "PRAGMA busy_timeout=10000"
        )

        return connection

    def load_energy(self):
        with self._connect() as connection:
            row = connection.execute(
                """
                SELECT energy_wh
                FROM totals
                WHERE id = 1
                """
            ).fetchone()

        return float(row[0])

    def save_measurement(
        self,
        measurement,
        energy_wh,
        events,
    ):
        now = time.monotonic()

        elapsed = (
            now - self._last_saved_time
            if self._last_saved_time is not None
            else 0
        )

        resumed = any(
            kind == "ACQUISITION_RESUMED"
            for kind, _ in events
        )

        continuous = (
            self._last_saved_time is not None
            and 0 < elapsed <= 2
            and not resumed
        )

        # Guardar todo en una misma transacción.
        with self._connect() as connection:
            connection.execute(
                """
                INSERT INTO measurements (
                    received_at,
                    voltage,
                    current_ma,
                    power_mw,
                    state,
                    energy_wh
                )
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (
                    measurement["received_at"],
                    measurement["voltage"],
                    measurement["current_ma"],
                    measurement["power_mw"],
                    measurement["state"],
                    energy_wh,
                ),
            )

            connection.execute(
                """
                UPDATE totals
                SET energy_wh = ?
                WHERE id = 1
                """,
                (energy_wh,),
            )

            for kind, detail in events:
                connection.execute(
                    """
                    INSERT INTO events (
                        received_at,
                        kind,
                        detail
                    )
                    VALUES (?, ?, ?)
                    """,
                    (
                        measurement["received_at"],
                        kind,
                        detail,
                    ),
                )

            EpisodeTracker.record(
                connection,
                measurement,
                elapsed,
                continuous,
            )

        # Avanzar solo si la transacción terminó correctamente.
        self._last_saved_time = now

    def summary(self):
        with self._connect() as connection:
            measurements = connection.execute(
                "SELECT COUNT(*) FROM measurements"
            ).fetchone()[0]

            events = connection.execute(
                "SELECT COUNT(*) FROM events"
            ).fetchone()[0]

            energy = connection.execute(
                """
                SELECT energy_wh
                FROM totals
                WHERE id = 1
                """
            ).fetchone()[0]

        return {
            "measurements": measurements,
            "events": events,
            "energy_wh": float(energy),
        }

    def add_event(
        self,
        kind,
        detail,
        received_at=None,
    ):
        timestamp = (
            received_at
            or datetime.now(timezone.utc).isoformat()
        )

        with self._connect() as connection:
            connection.execute(
                """
                INSERT INTO events (
                    received_at,
                    kind,
                    detail
                )
                VALUES (?, ?, ?)
                """,
                (timestamp, kind, detail),
            )

    def list_events(
        self,
        limit=50,
        before_id=None,
    ):
        limit = max(1, min(int(limit), 100))

        with self._connect() as connection:
            if before_id is None:
                rows = connection.execute(
                    """
                    SELECT
                        id,
                        received_at,
                        kind,
                        detail
                    FROM events
                    ORDER BY id DESC
                    LIMIT ?
                    """,
                    (limit + 1,),
                ).fetchall()

            else:
                rows = connection.execute(
                    """
                    SELECT
                        id,
                        received_at,
                        kind,
                        detail
                    FROM events
                    WHERE id < ?
                    ORDER BY id DESC
                    LIMIT ?
                    """,
                    (int(before_id), limit + 1),
                ).fetchall()

        has_more = len(rows) > limit
        rows = rows[:limit]

        return {
            "events": [
                {
                    "id": row[0],
                    "received_at": row[1],
                    "kind": row[2],
                    "detail": row[3],
                }
                for row in rows
            ],
            "has_more": has_more,
            "next_before_id": (
                rows[-1][0]
                if has_more
                else None
            ),
        }