import hmac
import os
import secrets
import sqlite3
import threading
from datetime import timedelta

from flask import (
    abort,
    flash,
    redirect,
    render_template_string,
    request,
    session,
    url_for,
)
from werkzeug.security import (
    check_password_hash,
    generate_password_hash,
)

import main as sistema

from recipients import (
    MAX_RECIPIENTS,
    anadir_destinatario,
    eliminar_destinatario,
    inicializar_destinatarios,
    listar_destinatarios,
)


app = sistema.app

password_admin = os.environ.get("DV_ADMIN_PASSWORD", "")

if not password_admin:
    raise RuntimeError(
        "Falta DV_ADMIN_PASSWORD en la configuración "
        "de ejecución de PyCharm."
    )

hash_admin = generate_password_hash(password_admin)
del password_admin

app.secret_key = (
    os.environ.get("DV_SESSION_SECRET")
    or secrets.token_hex(32)
)

app.config.update(
    SESSION_COOKIE_HTTPONLY=True,
    SESSION_COOKIE_SAMESITE="Lax",
    PERMANENT_SESSION_LIFETIME=timedelta(minutes=30),
    MAX_CONTENT_LENGTH=16384,
)

inicializar_destinatarios()


PLANTILLA = """
<!DOCTYPE html>
<html lang="es">
<head>
    <meta charset="UTF-8">
    <meta name="viewport"
          content="width=device-width, initial-scale=1">

    <title>{{ titulo }} — DV Power Monitor</title>

    <link rel="stylesheet"
          href="{{ url_for('static', filename='css/style.css') }}">

    <style>
        .configuracion {
            max-width: 720px;
            margin: 30px auto;
        }

        .configuracion h1 {
            color: #38bdf8;
        }

        .configuracion label {
            display: block;
            margin: 18px 0 8px;
        }

        .configuracion input:not([type="hidden"]) {
            width: 100%;
            padding: 12px;
            border: 1px solid #475569;
            border-radius: 7px;
            background: #0b1220;
            color: white;
            font-size: 16px;
        }

        .configuracion button,
        .configuracion .enlace,
        .configuracion summary {
            display: inline-block;
            padding: 10px 16px;
            border-radius: 7px;
            margin: 10px 8px 0 0;
        }

        .configuracion button,
        .configuracion summary {
            background: #2563eb;
            color: white;
            border: none;
            cursor: pointer;
            font-size: 14px;
        }

        .configuracion .enlace {
            color: #7dd3fc;
        }

        .configuracion .eliminar {
            background: #7f1d1d;
            margin: 0;
        }

        .configuracion .fila {
            display: flex;
            justify-content: space-between;
            align-items: center;
            gap: 15px;
            border-bottom: 1px solid #334155;
            padding: 14px 0;
        }

        .configuracion .correo {
            overflow-wrap: anywhere;
            min-width: 0;
        }

        .configuracion .error {
            color: #f87171;
        }

        .configuracion .exito {
            color: #34d399;
        }

        .configuracion .aviso {
            color: #fbbf24;
        }

        .configuracion details {
            margin: 20px 0;
        }

        .configuracion .acciones {
            margin-top: 25px;
        }

        @media (max-width: 500px) {
            .configuracion .fila {
                align-items: flex-start;
                flex-direction: column;
            }
        }
    </style>
</head>

<body>
<main class="configuracion panel">
    <h1>DV Power Monitor</h1>
    <h2>{{ titulo }}</h2>

    {% for categoria, mensaje in get_flashed_messages(
        with_categories=true
    ) %}
        <p class="{{ categoria }}" role="status">
            {{ mensaje }}
        </p>
    {% endfor %}

    {% if error %}
        <p class="error" role="alert">{{ error }}</p>
    {% endif %}

    {% if administrador %}
        <p>Sesión de administrador activa.</p>

        <h3>Destinatarios de alertas</h3>

        <p>
            {{ destinatarios|length }} de {{ limite }} correos.
            Las próximas alertas usarán esta lista.
        </p>

        {% if not destinatarios %}
            <p class="aviso">
                No hay destinatarios. No se enviarán correos
                hasta que añadas al menos uno.
            </p>
        {% endif %}

        {% for destinatario in destinatarios %}
            <div class="fila">
                <span class="correo">
                    {{ destinatario.email }}
                </span>

                <form method="post"
                      action="{{ url_for(
                          'borrar_destinatario',
                          identificador=destinatario.id
                      ) }}">
                    <input type="hidden"
                           name="csrf"
                           value="{{ csrf }}">

                    <button type="submit"
                            class="eliminar"
                            aria-label="Eliminar {{ destinatario.email }}">
                        Eliminar
                    </button>
                </form>
            </div>
        {% endfor %}

        {% if destinatarios|length < limite %}
            <details>
                <summary>Añadir destinatario</summary>

                <form method="post"
                      action="{{ url_for('guardar_destinatario') }}">
                    <input type="hidden"
                           name="csrf"
                           value="{{ csrf }}">

                    <label for="email">
                        Correo electrónico
                    </label>

                    <input type="email"
                           id="email"
                           name="email"
                           placeholder="nombre@ejemplo.com"
                           autocomplete="email"
                           maxlength="254"
                           required>

                    <button type="submit">Guardar</button>
                </form>
            </details>
        {% else %}
            <p class="aviso">
                Límite alcanzado. Elimina un destinatario
                para añadir otro.
            </p>
        {% endif %}

        <p class="nota">
            Añadir un correo no envía un mensaje inmediatamente.
            El cambio se aplicará al próximo intento de envío.
            Un envío que ya esté en curso conserva su lista.
        </p>

        <div class="acciones">
            <a class="enlace"
               href="{{ url_for('inicio') }}">
                Volver al dashboard
            </a>

            <form method="post"
                  action="{{ url_for('cerrar_sesion') }}">
                <input type="hidden"
                       name="csrf"
                       value="{{ csrf }}">

                <button type="submit">Cerrar sesión</button>
            </form>
        </div>

    {% else %}
        <p>
            Los visitantes pueden consultar el dashboard
            sin iniciar sesión.
        </p>

        <form method="post"
              action="{{ url_for('acceso_admin') }}">
            <input type="hidden"
                   name="csrf"
                   value="{{ csrf }}">

            <label for="password">
                Contraseña de administrador
            </label>

            <input type="password"
                   id="password"
                   name="password"
                   autocomplete="current-password"
                   maxlength="512"
                   required>

            <button type="submit">Entrar</button>
        </form>

        <a class="enlace"
           href="{{ url_for('inicio') }}">
            Continuar como visitante
        </a>
    {% endif %}
</main>
</body>
</html>
"""


def token_csrf():
    if "csrf" not in session:
        session["csrf"] = secrets.token_hex(32)

    return session["csrf"]


def comprobar_csrf():
    esperado = session.get("csrf", "")
    recibido = request.form.get("csrf", "")

    if (
        not esperado
        or not recibido
        or not hmac.compare_digest(esperado, recibido)
    ):
        abort(
            400,
            description="Formulario vencido. Recarga la página.",
        )


def es_administrador():
    return session.get("admin") is True


@app.route("/admin/login", methods=["GET", "POST"])
def acceso_admin():
    if es_administrador():
        return redirect(url_for("configuracion_admin"))

    error = None

    if request.method == "POST":
        comprobar_csrf()

        if check_password_hash(
            hash_admin,
            request.form.get("password", ""),
        ):
            session.clear()
            session["admin"] = True
            session.permanent = True

            return redirect(url_for("configuracion_admin"))

        error = "Contraseña incorrecta."

    return render_template_string(
        PLANTILLA,
        titulo="Acceso de administrador",
        error=error,
        administrador=False,
        csrf=token_csrf(),
    )


@app.route("/admin/configuracion")
def configuracion_admin():
    if not es_administrador():
        return redirect(url_for("acceso_admin"))

    return render_template_string(
        PLANTILLA,
        titulo="Configuración",
        error=None,
        administrador=True,
        destinatarios=listar_destinatarios(),
        limite=MAX_RECIPIENTS,
        csrf=token_csrf(),
    )


@app.route("/admin/destinatarios", methods=["POST"])
def guardar_destinatario():
    if not es_administrador():
        abort(403)

    comprobar_csrf()

    try:
        anadir_destinatario(request.form.get("email", ""))
        flash("Destinatario guardado.", "exito")

    except ValueError as error:
        flash(str(error), "error")

    except sqlite3.Error:
        flash(
            "No se pudo guardar. Inténtalo nuevamente.",
            "error",
        )

    return redirect(url_for("configuracion_admin"))


@app.route(
    "/admin/destinatarios/<int:identificador>/eliminar",
    methods=["POST"],
)
def borrar_destinatario(identificador):
    if not es_administrador():
        abort(403)

    comprobar_csrf()

    try:
        eliminar_destinatario(identificador)
        flash("Destinatario eliminado.", "exito")

    except ValueError as error:
        flash(str(error), "error")

    except sqlite3.Error:
        flash(
            "No se pudo eliminar. Inténtalo nuevamente.",
            "error",
        )

    return redirect(url_for("configuracion_admin"))


@app.route("/admin/logout", methods=["POST"])
def cerrar_sesion():
    comprobar_csrf()
    session.clear()
    return redirect(url_for("inicio"))


@app.after_request
def preparar_respuesta(response):
    if request.path.startswith("/admin"):
        response.headers["Cache-Control"] = "no-store"

    if (
        request.path == "/"
        and response.status_code == 200
        and response.mimetype == "text/html"
    ):
        administrador = es_administrador()

        etiqueta = (
            "Administrador · Configuración"
            if administrador
            else "Configuración"
        )

        rol = (
            "Administrador"
            if administrador
            else "Visitante · Solo lectura"
        )

        enlace = url_for("configuracion_admin")

        barra = (
            '<nav aria-label="Administración" '
            'style="display:flex;justify-content:space-between;'
            'align-items:center;gap:12px;flex-wrap:wrap;'
            'margin-bottom:16px;color:#94a3b8;">'
            f'<span>{rol}</span>'
            f'<a href="{enlace}" '
            'style="padding:10px 16px;background:#172033;'
            'color:#7dd3fc;border:1px solid #334155;'
            'border-radius:8px;text-decoration:none;">'
            f'{etiqueta}</a></nav>'
        )

        estilo = (
            "<style>"
            "[hidden]{display:none !important;}"
            "</style>"
        )

        pagina = response.get_data(as_text=True)

        pagina = pagina.replace(
            "</head>",
            estilo + "</head>",
            1,
        )

        pagina = pagina.replace(
            "<body>",
            "<body>" + barra,
            1,
        )

        response.set_data(pagina)
        response.headers["Cache-Control"] = "no-store"

    return response


if __name__ == "__main__":
    sistema.detener_monitor.clear()
    sistema.reader.start()
    sistema.historial.start(sistema.reader)

    monitor = threading.Thread(
        target=sistema.vigilar_estados,
        name="monitor-alertas",
        daemon=True,
    )
    monitor.start()

    print("\nDV POWER MONITOR")
    print("Adquisición y alertas automáticas: ACTIVAS")
    print("Configuración de destinatarios: HABILITADA")
    print("Laptop: http://127.0.0.1:5000/")
    print("Red local: http://192.168.1.153:5000/\n")

    try:
        app.run(
            host="0.0.0.0",
            port=5000,
            debug=False,
            use_reloader=False,
        )

    finally:
        sistema.detener_monitor.set()
        monitor.join(timeout=2)
        sistema.historial.stop()
        sistema.comando_seguro("EMAIL_ERROR")
        sistema.reader.stop()