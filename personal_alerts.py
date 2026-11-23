"""Correos verificados reciben alertas sin depender de la sesión."""

import hashlib
import hmac
import secrets
import sqlite3
import time

from contextlib import closing

from flask import (
    abort,
    flash,
    redirect,
    request,
    session,
    url_for,
)

from storage import DB_PATH


LEASE_SECONDS = 90
CODE_SECONDS = 900
ENABLED = False


def connect():
    db = sqlite3.connect(
        DB_PATH,
        timeout=10,
    )

    db.row_factory = sqlite3.Row

    return db


def initialize():
    with closing(connect()) as db, db:
        db.executescript("""
            CREATE TABLE IF NOT EXISTS personal_email (
                user_id INTEGER PRIMARY KEY,
                verified_email TEXT,
                pending_email TEXT,
                code_hash TEXT,
                expires REAL NOT NULL DEFAULT 0,
                attempts INTEGER NOT NULL DEFAULT 0,
                sent_at REAL NOT NULL DEFAULT 0
            );

            CREATE TABLE IF NOT EXISTS personal_sessions (
                token TEXT PRIMARY KEY,
                user_id INTEGER NOT NULL,
                version TEXT NOT NULL,
                last_seen REAL NOT NULL
            );
        """)

        # Se conserva esta tabla para compatibilidad.
        # La presencia ya no determina quién recibe alertas.
        db.execute(
            "DELETE FROM personal_sessions"
        )


def verified(user):
    with closing(connect()) as db:
        row = db.execute(
            """
            SELECT verified_email
            FROM personal_email
            WHERE user_id = ?
            """,
            (user["id"],),
        ).fetchone()

    return bool(
        row
        and user["email"]
        and row["verified_email"]
        and row["verified_email"].casefold()
        == user["email"].casefold()
    )


def revoke():
    """
    Elimina el registro de presencia de esta sesión.

    Cerrar sesión no desactiva las alertas del correo
    verificado.
    """
    token = session.pop(
        "presence_token",
        None,
    )

    if token:
        with closing(connect()) as db, db:
            db.execute(
                """
                DELETE FROM personal_sessions
                WHERE token = ?
                """,
                (token,),
            )


def touch(user):
    """
    Mantiene compatibilidad con users.py y presencia.js.

    Este registro no se utiliza para decidir
    quién recibe las alertas.
    """
    token = session.get(
        "presence_token"
    )

    if not token:
        token = secrets.token_urlsafe(32)
        session["presence_token"] = token

    now = time.time()

    with closing(connect()) as db, db:
        db.execute(
            """
            DELETE FROM personal_sessions
            WHERE last_seen < ?
            """,
            (now - LEASE_SECONDS,),
        )

        db.execute(
            """
            INSERT OR REPLACE INTO personal_sessions
            VALUES (?, ?, ?, ?)
            """,
            (
                token,
                user["id"],
                user["session_version"],
                now,
            ),
        )


def automatic_recipients(general):
    """
    Los usuarios con correo verificado reciben alertas
    independientemente de su sesión o navegador.
    """
    if not ENABLED:
        return general

    with closing(connect()) as db:
        registered = {
            row[0].casefold()
            for row in db.execute(
                """
                SELECT email
                FROM app_users
                WHERE email IS NOT NULL
                """
            )
            if row[0]
        }

        verified_users = db.execute(
            """
            SELECT DISTINCT u.email
            FROM app_users u

            JOIN personal_email e
                ON e.user_id = u.id

            WHERE u.email IS NOT NULL
              AND lower(e.verified_email) = lower(u.email)
            """
        ).fetchall()

    # Conserva los destinatarios generales que no pertenecen
    # a cuentas registradas.
    result = {
        email.casefold(): email
        for email in general
        if email.casefold() not in registered
    }

    # Añade los usuarios con correo verificado.
    # No se requiere una sesión activa.
    for row in verified_users:
        result.setdefault(
            row[0].casefold(),
            row[0],
        )

    return list(result.values())


def configure(
    app,
    actual,
    csrf_check,
    limit,
):
    global ENABLED

    initialize()
    ENABLED = True

    app.jinja_env.globals[
        "personal_verified"
    ] = verified

    def require_user():
        user = actual()

        if (
            not user
            or session.get("admin")
        ):
            abort(403)

        return user

    @app.post("/usuario/presencia")
    def personal_presence():
        csrf_check()

        touch(
            require_user()
        )

        return {
            "ok": True,
            "lease_seconds": LEASE_SECONDS,
        }

    @app.post("/usuario/verificacion/enviar")
    def personal_send_code():
        csrf_check()
        limit()

        user = require_user()

        if not user["email"]:
            flash(
                "Guarda primero tu correo en Mi cuenta.",
                "error",
            )

            return redirect(
                url_for("mi_cuenta")
            )

        code = (
            f"{secrets.randbelow(1000000):06d}"
        )

        # La sal aleatoria protege el código almacenado.
        salt = secrets.token_hex(16)

        digest = (
            salt
            + ":"
            + hashlib.sha256(
                (salt + code).encode()
            ).hexdigest()
        )

        now = time.time()

        with closing(connect()) as db, db:
            db.execute(
                "BEGIN IMMEDIATE"
            )

            row = db.execute(
                """
                SELECT sent_at
                FROM personal_email
                WHERE user_id = ?
                """,
                (user["id"],),
            ).fetchone()

            if (
                row
                and now - row["sent_at"] < 60
            ):
                flash(
                    "Espera un minuto antes de solicitar otro código.",
                    "error",
                )

                return redirect(
                    url_for("mi_cuenta")
                )

            db.execute(
                """
                INSERT INTO personal_email (
                    user_id,
                    pending_email,
                    code_hash,
                    expires,
                    attempts,
                    sent_at
                )
                VALUES (?, ?, ?, ?, 0, ?)

                ON CONFLICT(user_id) DO UPDATE SET
                    pending_email = excluded.pending_email,
                    code_hash = excluded.code_hash,
                    expires = excluded.expires,
                    attempts = 0,
                    sent_at = excluded.sent_at
                """,
                (
                    user["id"],
                    user["email"],
                    digest,
                    now + CODE_SECONDS,
                    now,
                ),
            )

        try:
            from notifications import enviar_email

            result = enviar_email(
                "DV Power Monitor — Verifica tu correo",
                (
                    f"Tu código de verificación es: {code}\n"
                    "Vence en 15 minutos. "
                    "Introdúcelo en Mi cuenta.\n"
                    "Este mensaje no corresponde a una alarma."
                ),
                destinatarios=[
                    user["email"]
                ],
            )

            if result["rechazados"]:
                raise ValueError(
                    "Correo rechazado"
                )

            flash(
                "Código enviado. Revisa tu correo y Spam.",
                "exito",
            )

        except Exception:
            app.logger.warning(
                "No se pudo enviar el código de verificación"
            )

            with closing(connect()) as db, db:
                db.execute(
                    """
                    UPDATE personal_email
                    SET
                        code_hash = NULL,
                        expires = 0,
                        sent_at = 0
                    WHERE user_id = ?
                      AND code_hash = ?
                    """,
                    (
                        user["id"],
                        digest,
                    ),
                )

            flash(
                "No se pudo enviar el código. "
                "Revisa Internet y la configuración del correo.",
                "error",
            )

        return redirect(
            url_for("mi_cuenta")
        )

    @app.post("/usuario/verificacion/confirmar")
    def personal_confirm_code():
        csrf_check()
        limit()

        user = require_user()

        code = request.form.get(
            "codigo",
            "",
        ).strip()

        now = time.time()
        valid = False

        with closing(connect()) as db, db:
            db.execute(
                "BEGIN IMMEDIATE"
            )

            row = db.execute(
                """
                SELECT *
                FROM personal_email
                WHERE user_id = ?
                """,
                (user["id"],),
            ).fetchone()

            if (
                row
                and row["code_hash"]
                and row["attempts"] < 5
                and row["expires"] > now
                and row["pending_email"] == user["email"]
            ):
                salt, digest = row[
                    "code_hash"
                ].split(":", 1)

                valid = hmac.compare_digest(
                    digest,
                    hashlib.sha256(
                        (salt + code).encode()
                    ).hexdigest(),
                )

                if valid:
                    db.execute(
                        """
                        UPDATE personal_email
                        SET
                            verified_email = ?,
                            code_hash = NULL,
                            expires = 0
                        WHERE user_id = ?
                        """,
                        (
                            user["email"],
                            user["id"],
                        ),
                    )

                else:
                    db.execute(
                        """
                        UPDATE personal_email
                        SET attempts = attempts + 1
                        WHERE user_id = ?
                        """,
                        (user["id"],),
                    )

        flash(
            (
                "Correo verificado. Recibirás avisos "
                "aunque cierres sesión o el navegador."
                if valid
                else
                "Código incorrecto, vencido o agotado. "
                "Solicita uno nuevo."
            ),
            "exito" if valid else "error",
        )

        return redirect(
            url_for("mi_cuenta")
        )