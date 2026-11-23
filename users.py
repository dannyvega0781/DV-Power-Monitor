import hmac
import re
import secrets
import sqlite3
import threading
import time

from collections import defaultdict, deque
from contextlib import closing

from flask import (
    abort,
    flash,
    redirect,
    render_template,
    request,
    session,
    url_for,
)

from werkzeug.security import (
    check_password_hash,
    generate_password_hash,
)

from recipients import validar_email
from storage import DB_PATH

import personal_alerts


MAX_USERS = 10


def conectar():
    connection = sqlite3.connect(
        DB_PATH,
        timeout=10,
    )
    connection.row_factory = sqlite3.Row
    return connection


def inicializar():
    with closing(conectar()) as connection, connection:
        connection.execute("""
            CREATE TABLE IF NOT EXISTS app_users (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                username TEXT NOT NULL COLLATE NOCASE UNIQUE,
                password_hash TEXT NOT NULL,
                email TEXT,
                session_version TEXT NOT NULL,
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
            )
        """)


def obtener_usuario(identificador):
    with closing(conectar()) as connection:
        row = connection.execute(
            "SELECT * FROM app_users WHERE id = ?",
            (identificador,),
        ).fetchone()

    return dict(row) if row else None


def csrf_token():
    if "csrf" not in session:
        session["csrf"] = secrets.token_hex(32)

    return session["csrf"]


def comprobar_csrf():
    esperado = session.get("csrf", "")
    recibido = request.form.get("csrf", "")

    if (
        not esperado
        or not hmac.compare_digest(esperado, recibido)
    ):
        abort(
            400,
            description="Formulario vencido. Recarga la página.",
        )


def validar_password(password):
    if not 10 <= len(password) <= 128:
        raise ValueError(
            "La contraseña debe tener entre 10 y 128 caracteres."
        )


def configurar_usuarios(base):
    app = base.app
    sistema = base.sistema

    inicializar()

    original_dashboard = app.view_functions["inicio"]

    intentos = defaultdict(deque)
    bloqueo_intentos = threading.Lock()

    def limitar():
        clave = (
            request.remote_addr,
            request.endpoint,
        )

        ahora = time.monotonic()

        with bloqueo_intentos:
            for vieja in list(intentos):
                while (
                    intentos[vieja]
                    and ahora - intentos[vieja][0] > 60
                ):
                    intentos[vieja].popleft()

                if not intentos[vieja]:
                    del intentos[vieja]

            cola = intentos[clave]

            if len(cola) >= 10:
                abort(
                    429,
                    description=(
                        "Demasiados intentos. Espera un minuto."
                    ),
                )

            cola.append(ahora)

    def actual():
        identificador = session.get("user_id")

        if not identificador:
            return None

        usuario = obtener_usuario(identificador)

        if (
            not usuario
            or not hmac.compare_digest(
                usuario["session_version"],
                session.get("user_version", ""),
            )
        ):
            personal_alerts.revoke()
            session.clear()
            return None

        return usuario

    def exigir_usuario():
        usuario = actual()

        if usuario is None or session.get("admin"):
            abort(403)

        return usuario

    def pagina(vista, **datos):
        response = app.make_response(
            render_template(
                "portal.html",
                vista=vista,
                usuario=actual(),
                admin=session.get("admin") is True,
                csrf=csrf_token(),
                limite=MAX_USERS,
                **datos,
            )
        )

        response.headers["Cache-Control"] = "no-store"
        return response

    @app.before_request
    def validar_sesion_usuario():
        if session.get("user_id"):
            actual()

        # El acceso administrador sustituye al de usuario.
        if (
            request.endpoint == "acceso_admin"
            and request.method == "POST"
        ):
            comprobar_csrf()
            personal_alerts.revoke()
            session.pop("user_id", None)
            session.pop("user_version", None)
            limitar()

    def portada():
        return pagina("inicio")

    # La página principal muestra el portal.
    # El dashboard existente se conserva en /dashboard.
    app.view_functions["inicio"] = portada

    app.add_url_rule(
        "/dashboard",
        "dashboard",
        original_dashboard,
    )

    @app.route("/registro", methods=["GET", "POST"])
    def registro():
        if request.method == "POST":
            comprobar_csrf()
            limitar()

            try:
                username = request.form.get(
                    "username", ""
                ).strip()

                password = request.form.get(
                    "password", ""
                )

                if not re.fullmatch(
                    r"[A-Za-z0-9_]{3,30}",
                    username,
                ):
                    raise ValueError(
                        "Usuario: 3 a 30 letras, números "
                        "o guion bajo."
                    )

                if username.lower() in {
                    "admin",
                    "administrador",
                }:
                    raise ValueError(
                        "Ese nombre está reservado."
                    )

                validar_password(password)

                if password != request.form.get(
                    "confirmar", ""
                ):
                    raise ValueError(
                        "Las contraseñas no coinciden."
                    )

                email = validar_email(
                    request.form.get("email", "")
                )

                password_hash = generate_password_hash(
                    password
                )

                with closing(conectar()) as connection, connection:
                    connection.execute("BEGIN IMMEDIATE")

                    count = connection.execute(
                        "SELECT COUNT(*) FROM app_users"
                    ).fetchone()[0]

                    if count >= MAX_USERS:
                        raise ValueError(
                            "Ya hay 10 usuarios registrados."
                        )

                    connection.execute(
                        """
                        INSERT INTO app_users (
                            username,
                            password_hash,
                            email,
                            session_version
                        )
                        VALUES (?, ?, ?, ?)
                        """,
                        (
                            username,
                            password_hash,
                            email,
                            secrets.token_hex(32),
                        ),
                    )

                flash(
                    "Cuenta creada. Ya puedes iniciar sesión. "
                    "Verifica tu correo en Mi cuenta para recibir avisos.",
                    "exito",
                )

                return redirect(
                    url_for("usuario_login")
                )

            except ValueError as error:
                flash(str(error), "error")

            except sqlite3.IntegrityError:
                flash(
                    "Ese nombre de usuario ya está registrado.",
                    "error",
                )

            except sqlite3.Error:
                flash(
                    "No se pudo guardar la cuenta. "
                    "Inténtalo nuevamente.",
                    "error",
                )

        return pagina("registro")

    @app.route(
        "/usuario/login",
        methods=["GET", "POST"],
    )
    def usuario_login():
        if request.method == "POST":
            comprobar_csrf()
            limitar()

            with closing(conectar()) as connection:
                usuario = connection.execute(
                    """
                    SELECT *
                    FROM app_users
                    WHERE username = ? COLLATE NOCASE
                    """,
                    (
                        request.form.get(
                            "username", ""
                        ).strip(),
                    ),
                ).fetchone()

            password = request.form.get(
                "password", ""
            )

            if (
                usuario
                and len(password) <= 128
                and check_password_hash(
                    usuario["password_hash"],
                    password,
                )
            ):
                personal_alerts.revoke()
                session.clear()

                session["user_id"] = usuario["id"]
                session["user_version"] = (
                    usuario["session_version"]
                )
                session.permanent = True

                personal_alerts.touch(dict(usuario))

                return redirect(
                    url_for("dashboard")
                )

            flash(
                "Usuario o contraseña incorrectos.",
                "error",
            )

        return pagina("login")

    @app.route(
        "/mi-cuenta",
        methods=["GET", "POST"],
    )
    def mi_cuenta():
        usuario = exigir_usuario()

        if request.method == "POST":
            comprobar_csrf()
            limitar()

            try:
                if not check_password_hash(
                    usuario["password_hash"],
                    request.form.get("actual", ""),
                ):
                    raise ValueError(
                        "La contraseña actual no es correcta."
                    )

                accion = request.form.get("accion")

                with closing(conectar()) as connection, connection:
                    if accion == "email":
                        valor = request.form.get(
                            "email", ""
                        ).strip()

                        email = (
                            validar_email(valor)
                            if valor
                            else None
                        )

                        connection.execute(
                            """
                            UPDATE app_users
                            SET email = ?
                            WHERE id = ?
                            """,
                            (email, usuario["id"]),
                        )

                        connection.execute(
                            """
                            DELETE FROM personal_email
                            WHERE user_id = ?
                            """,
                            (usuario["id"],),
                        )

                    elif accion == "password":
                        nuevo = request.form.get(
                            "nuevo", ""
                        )

                        validar_password(nuevo)

                        if nuevo != request.form.get(
                            "confirmar", ""
                        ):
                            raise ValueError(
                                "Las contraseñas nuevas "
                                "no coinciden."
                            )

                        version = secrets.token_hex(32)

                        connection.execute(
                            """
                            UPDATE app_users
                            SET
                                password_hash = ?,
                                session_version = ?
                            WHERE id = ?
                            """,
                            (
                                generate_password_hash(nuevo),
                                version,
                                usuario["id"],
                            ),
                        )

                        connection.execute(
                            """
                            DELETE FROM personal_sessions
                            WHERE user_id = ?
                            """,
                            (usuario["id"],),
                        )

                    elif accion == "eliminar":
                        connection.execute(
                            """
                            DELETE FROM app_users
                            WHERE id = ?
                            """,
                            (usuario["id"],),
                        )

                        connection.execute(
                            """
                            DELETE FROM personal_sessions
                            WHERE user_id = ?
                            """,
                            (usuario["id"],),
                        )

                        connection.execute(
                            """
                            DELETE FROM personal_email
                            WHERE user_id = ?
                            """,
                            (usuario["id"],),
                        )

                    else:
                        abort(400)

                if accion == "eliminar":
                    session.clear()

                    return redirect(
                        url_for("inicio")
                    )

                if accion == "password":
                    session["user_version"] = version

                flash("Cambios guardados.", "exito")

            except ValueError as error:
                flash(str(error), "error")

            except sqlite3.Error:
                flash(
                    "No se pudo guardar el cambio.",
                    "error",
                )

            return redirect(
                url_for("mi_cuenta")
            )

        return pagina("perfil")

    @app.route(
        "/cuenta/salir",
        methods=["POST"],
    )
    def cuenta_salir():
        comprobar_csrf()
        personal_alerts.revoke()
        session.clear()

        return redirect(
            url_for("inicio")
        )

    @app.route(
        "/admin/usuarios",
        methods=["GET", "POST"],
    )
    def administrar_usuarios():
        if session.get("admin") is not True:
            abort(403)

        if request.method == "POST":
            comprobar_csrf()

            try:
                identificador = int(
                    request.form.get("id", "")
                )

                with closing(conectar()) as connection, connection:
                    connection.execute(
                        """
                        DELETE FROM app_users
                        WHERE id = ?
                        """,
                        (identificador,),
                    )

                with closing(conectar()) as connection, connection:
                    connection.execute(
                        """
                        DELETE FROM personal_sessions
                        WHERE user_id = ?
                        """,
                        (identificador,),
                    )

                    connection.execute(
                        """
                        DELETE FROM personal_email
                        WHERE user_id = ?
                        """,
                        (identificador,),
                    )

                flash(
                    "Usuario eliminado. "
                    "Sus sesiones dejan de ser válidas.",
                    "exito",
                )

            except (ValueError, sqlite3.Error):
                flash(
                    "No se pudo eliminar el usuario.",
                    "error",
                )

            return redirect(
                url_for("administrar_usuarios")
            )

        with closing(conectar()) as connection:
            usuarios = connection.execute(
                """
                SELECT id, username, email
                FROM app_users
                ORDER BY id
                """
            ).fetchall()

        return pagina(
            "usuarios",
            usuarios=usuarios,
        )

    @app.route("/acerca")
    def acerca():
        return pagina("acerca")

    @app.route("/api/portal/estado")
    def portal_estado():
        import platform
        from pathlib import Path

        modelo = Path("/proc/device-tree/model")
        servidor = platform.system()

        if modelo.exists():
            nombre = modelo.read_text().strip("\x00\n")

            if "Raspberry Pi" in nombre:
                servidor = nombre

        datos = sistema.reader.snapshot()

        response = app.make_response({
            "server": servidor,
            "connected": datos["serial_connected"],
            "valid": datos["data_valid"],
            "state": (
                datos.get("measurement") or {}
            ).get("state"),
            "age_seconds": datos.get("age_seconds"),
            "storage_ok": datos.get("storage_ok"),
        })

        response.headers["Cache-Control"] = "no-store"
        return response

    personal_alerts.configure(
        app,
        actual,
        comprobar_csrf,
        limitar,
    )

    # Sustituir únicamente la barra de navegación anterior.
    app.after_request_funcs[None].remove(
        base.preparar_respuesta
    )

    @app.after_request
    def navegacion_portal(response):
        if response.mimetype == "text/html":
            response.headers["Cache-Control"] = "no-store"

        if (
            request.path == "/dashboard"
            and response.status_code == 200
        ):
            barra = render_template(
                "portal.html",
                vista="barra",
                usuario=actual(),
                admin=session.get("admin") is True,
                csrf=csrf_token(),
                limite=MAX_USERS,
            )

            html = response.get_data(as_text=True)

            html = html.replace(
                "</head>",
                "<style>"
                "[hidden]{display:none!important}"
                "</style></head>",
                1,
            )

            html = html.replace(
                "<body>",
                "<body>" + barra,
                1,
            )

            response.set_data(html)

        if (
            response.mimetype == "text/html"
            and response.status_code == 200
            and actual()
            and not session.get("admin")
        ):
            from markupsafe import escape

            script = (
                '<script src="/static/js/presencia.js" data-csrf="'
                + str(escape(csrf_token()))
                + '"></script>'
            )

            response.set_data(
                response.get_data(as_text=True).replace(
                    "</body>",
                    script + "</body>",
                    1,
                )
            )

        return response