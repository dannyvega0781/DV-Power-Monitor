from datetime import datetime


class EpisodeTracker:
    @staticmethod
    def initialize(connection):
        connection.executescript("""
            CREATE TABLE IF NOT EXISTS fault_episodes (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                started_at TEXT NOT NULL,
                recovered_at TEXT,
                last_observed_at TEXT NOT NULL,
                initial_state TEXT NOT NULL,
                last_state TEXT NOT NULL,
                observed_seconds REAL NOT NULL DEFAULT 0,
                uncertain_start INTEGER NOT NULL DEFAULT 0,
                has_gaps INTEGER NOT NULL DEFAULT 0
            );

            CREATE UNIQUE INDEX IF NOT EXISTS one_open_fault_episode
            ON fault_episodes ((1))
            WHERE recovered_at IS NULL;
        """)

    @staticmethod
    def record(connection, measurement, elapsed, continuous):
        timestamp = measurement["received_at"]
        state = measurement["state"]

        row = connection.execute(
            """
            SELECT
                id,
                started_at,
                last_state,
                observed_seconds,
                uncertain_start,
                has_gaps
            FROM fault_episodes
            WHERE recovered_at IS NULL
            """
        ).fetchone()

        def event(kind, detail):
            connection.execute(
                """
                INSERT INTO events (
                    received_at, kind, detail
                )
                VALUES (?, ?, ?)
                """,
                (timestamp, kind, detail),
            )

        # No existe un episodio abierto.
        if row is None:
            if state == "NORMAL":
                return

            uncertain = not continuous

            cursor = connection.execute(
                """
                INSERT INTO fault_episodes (
                    started_at,
                    last_observed_at,
                    initial_state,
                    last_state,
                    uncertain_start
                )
                VALUES (?, ?, ?, ?, ?)
                """,
                (
                    timestamp,
                    timestamp,
                    state,
                    state,
                    int(uncertain),
                ),
            )

            detail = (
                f"Episodio #{cursor.lastrowid}: {state}. "
                "Inicio del registro de condición "
                "anormal confirmada."
            )

            if uncertain:
                detail += (
                    " La condición ya estaba presente "
                    "al iniciar o reanudar; "
                    "su inicio real es desconocido."
                )

            event("Inicio de episodio", detail)
            return

        (
            identifier,
            started,
            previous,
            observed,
            uncertain,
            had_gaps,
        ) = row

        gap = not continuous

        if continuous:
            observed += elapsed

        gaps = bool(had_gaps) or gap

        if gap and not had_gaps:
            event(
                "Episodio con interrupción",
                (
                    f"Episodio #{identifier}: faltan "
                    "observaciones o hubo reinicio. "
                    "No se asume continuidad "
                    "durante ese periodo."
                ),
            )

        # Recuperación: cerrar el episodio existente.
        if state == "NORMAL":
            connection.execute(
                """
                UPDATE fault_episodes
                SET
                    recovered_at = ?,
                    last_observed_at = ?,
                    last_state = ?,
                    observed_seconds = ?,
                    has_gaps = ?
                WHERE id = ?
                """,
                (
                    timestamp,
                    timestamp,
                    state,
                    observed,
                    int(gaps),
                    identifier,
                ),
            )

            span = (
                datetime.fromisoformat(timestamp)
                - datetime.fromisoformat(started)
            ).total_seconds()

            detail = (
                f"Episodio #{identifier}: "
                "recuperación a NORMAL. "
                "Tiempo observado estimado: "
                f"{observed:.1f} s. "
            )

            if span >= 0:
                detail += (
                    "Intervalo entre primera detección "
                    "y recuperación: "
                    f"{span:.1f} s. "
                )

            else:
                detail += (
                    "El reloj del sistema cambió; "
                    "intervalo de fechas no válido. "
                )

            if uncertain or gaps:
                detail += (
                    "Registro incompleto: inicio desconocido "
                    "y/o periodos sin observación. "
                )

            detail += (
                "No representa downtime de producción confirmado."
            )

            event("Recuperación de episodio", detail)

        # Sigue anormal: mantener el mismo episodio.
        else:
            connection.execute(
                """
                UPDATE fault_episodes
                SET
                    last_observed_at = ?,
                    last_state = ?,
                    observed_seconds = ?,
                    has_gaps = ?
                WHERE id = ?
                """,
                (
                    timestamp,
                    state,
                    observed,
                    int(gaps),
                    identifier,
                ),
            )

            if state != previous:
                event(
                    "Cambio dentro del episodio",
                    (
                        f"Episodio #{identifier}: "
                        f"{previous} -> {state}. "
                        "Continúa el mismo episodio; "
                        "no se crea otra parada."
                    ),
                )