import os
import re
import sqlite3

from storage import DB_PATH


MAX_RECIPIENTS = 10


def validar_email(valor):
    email = valor.strip()

    # Validación práctica para direcciones habituales.
    # No comprueba que el buzón realmente exista.
    patron = (
        r"[A-Za-z0-9!#$%&'*+/=?^_`{|}~.-]+"
        r"@"
        r"[A-Za-z0-9](?:[A-Za-z0-9-]*[A-Za-z0-9])?"
        r"(?:\.[A-Za-z0-9](?:[A-Za-z0-9-]*[A-Za-z0-9])?)+"
    )

    if len(email) > 254 or not re.fullmatch(patron, email):
        raise ValueError("Escribe una dirección de correo válida.")

    local = email.split("@", 1)[0]

    if (
        len(local) > 64
        or local.startswith(".")
        or local.endswith(".")
        or ".." in local
    ):
        raise ValueError("Escribe una dirección de correo válida.")

    return email


def conectar():
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)

    connection = sqlite3.connect(DB_PATH, timeout=10)
    connection.execute("PRAGMA busy_timeout=10000")
    return connection


def inicializar_destinatarios():
    connection = conectar()

    try:
        connection.execute("BEGIN IMMEDIATE")

        connection.execute("""
            CREATE TABLE IF NOT EXISTS email_recipients (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                email TEXT NOT NULL COLLATE NOCASE UNIQUE
            )
        """)

        connection.execute("""
            CREATE TABLE IF NOT EXISTS app_settings (
                key TEXT PRIMARY KEY,
                value TEXT NOT NULL
            )
        """)

        migrado = connection.execute(
            "SELECT value FROM app_settings WHERE key = ?",
            ("email_recipients_initialized",),
        ).fetchone()

        # Importar la lista anterior una sola vez.
        # Eliminar correos después no volverá a importarlos.
        if migrado is None:
            existentes = {
                fila[0].lower()
                for fila in connection.execute(
                    "SELECT email FROM email_recipients"
                )
            }

            for valor in os.environ.get("DV_EMAIL_TO", "").split(","):
                if not valor.strip():
                    continue

                try:
                    email = validar_email(valor)
                except ValueError:
                    print(
                        "[EMAIL] Una dirección anterior no pudo "
                        "importarse. Revísala en Configuración."
                    )
                    continue

                if email.lower() in existentes:
                    continue

                if len(existentes) >= MAX_RECIPIENTS:
                    print(
                        "[EMAIL] Se alcanzó el límite de "
                        "10 destinatarios durante la importación."
                    )
                    break

                connection.execute(
                    "INSERT INTO email_recipients (email) VALUES (?)",
                    (email,),
                )
                existentes.add(email.lower())

            connection.execute(
                """
                INSERT INTO app_settings (key, value)
                VALUES (?, ?)
                """,
                ("email_recipients_initialized", "1"),
            )

        connection.commit()

    except Exception:
        connection.rollback()
        raise

    finally:
        connection.close()


def listar_destinatarios():
    with conectar() as connection:
        filas = connection.execute(
            """
            SELECT id, email
            FROM email_recipients
            ORDER BY id
            """
        ).fetchall()

    return [
        {"id": fila[0], "email": fila[1]}
        for fila in filas
    ]


def anadir_destinatario(valor):
    email = validar_email(valor)
    connection = conectar()

    try:
        connection.execute("BEGIN IMMEDIATE")

        repetido = connection.execute(
            """
            SELECT id FROM email_recipients
            WHERE email = ? COLLATE NOCASE
            """,
            (email,),
        ).fetchone()

        if repetido:
            raise ValueError("Ese correo ya está guardado.")

        cantidad = connection.execute(
            "SELECT COUNT(*) FROM email_recipients"
        ).fetchone()[0]

        if cantidad >= MAX_RECIPIENTS:
            raise ValueError(
                "Ya tienes 10 destinatarios. "
                "Elimina uno antes de añadir otro."
            )

        connection.execute(
            "INSERT INTO email_recipients (email) VALUES (?)",
            (email,),
        )

        connection.commit()

    except Exception:
        connection.rollback()
        raise

    finally:
        connection.close()


def eliminar_destinatario(identificador):
    with conectar() as connection:
        resultado = connection.execute(
            "DELETE FROM email_recipients WHERE id = ?",
            (identificador,),
        )

        if resultado.rowcount == 0:
            raise ValueError("Ese destinatario ya no está en la lista.")