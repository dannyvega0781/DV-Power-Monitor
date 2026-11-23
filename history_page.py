import hmac
import secrets
import time
from datetime import date, datetime, timedelta, timezone

from flask import (
    abort,
    flash,
    redirect,
    render_template_string,
    request,
    session,
    url_for,
)

from notifications import enviar_email
from recipients import listar_destinatarios, validar_email


ZONA_PR = timezone(timedelta(hours=-4))
MAX_EVENTOS_EMAIL = 1000

NOMBRES = {
    "SESSION_START": "Inicio de adquisición",
    "STATE_CHANGE": "Cambio de estado",
    "ACQUISITION_RESUMED": "Adquisición reanudada",
    "MEASUREMENT_GAP": "Intervalo sin energía estimada",
    "EMAIL_START": "Intento de email",
    "EMAIL_ACCEPTED": "Email aceptado por Gmail",
    "EMAIL_PARTIAL": "Email parcialmente aceptado",
    "EMAIL_ERROR": "Error de email",
    "GRAPH_ERROR": "Imagen no disponible",
    "LED_COMMAND_ERROR": "Comando del LED no enviado",
    "HISTORY_EMAIL_START": "Envío manual del historial",
    "HISTORY_EMAIL_ACCEPTED": "Historial aceptado por Gmail",
    "HISTORY_EMAIL_PARTIAL": "Historial parcialmente aceptado",
    "HISTORY_EMAIL_ERROR": "Error al enviar el historial",
}


PAGINA = """
<!DOCTYPE html>
<html lang="es">
<head>
    <meta charset="UTF-8">

    <meta name="viewport"
          content="width=device-width, initial-scale=1">

    <title>Historial — DV Power Monitor</title>

    <link rel="stylesheet"
          href="{{ url_for('static', filename='css/style.css') }}">

    <style>
        .contenido {
            max-width: 1200px;
            margin: auto;
        }

        .filtros {
            display: flex;
            gap: 15px;
            align-items: end;
            flex-wrap: wrap;
        }

        label {
            display: block;
            margin: 10px 0;
        }

        input[type=date],
        input[type=email] {
            padding: 10px;
            background: #0b1220;
            color: white;
            border: 1px solid #475569;
            border-radius: 7px;
            font-size: 16px;
            max-width: 100%;
            box-sizing: border-box;
        }

        button,
        .boton {
            display: inline-block;
            background: #334155;
            color: #e2e8f0;
            border: 1px solid #64748b;
            border-radius: 7px;
            padding: 10px 15px;
            text-decoration: none;
            cursor: pointer;
            margin: 5px 5px 5px 0;
        }

        button:disabled {
            opacity: 0.5;
            cursor: default;
        }

        .tabla {
            overflow-x: auto;
        }

        table {
            width: 100%;
            border-collapse: collapse;
            text-align: left;
        }

        th,
        td {
            padding: 12px;
            border-bottom: 1px solid #334155;
            vertical-align: top;
        }

        th {
            color: #7dd3fc;
        }

        td:last-child {
            min-width: 220px;
            overflow-wrap: anywhere;
        }

        .error {
            color: #f87171;
        }

        .exito {
            color: #34d399;
        }

        .aviso {
            color: #fbbf24;
        }
    </style>
</head>

<body>
<main class="contenido">

    <header>
        <h1>DV Power Monitor</h1>
        <h2>Historial</h2>

        <a class="boton" href="{{ url_for('inicio') }}">
            Volver al dashboard
        </a>

        {% if not admin %}
            <a class="boton" href="/admin/login">
                Acceso administrador
            </a>
        {% endif %}
    </header>

    <section class="panel">

        <h2>Consultar periodo</h2>

        <p>
            Fechas y horas de Puerto Rico.
            Ambas fechas están incluidas.
        </p>

        <form method="get" class="filtros">

            <label>
                Desde<br>
                <input type="date"
                       name="desde"
                       value="{{ desde }}"
                       required>
            </label>

            <label>
                Hasta<br>
                <input type="date"
                       name="hasta"
                       value="{{ hasta }}"
                       required>
            </label>

            <button type="submit">
                Consultar / Actualizar
            </button>

        </form>

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

        {% if not error %}

            <p>
                {{ total }} eventos en el periodo.
                Se muestran hasta 50 por página.
            </p>

            <div class="tabla">
                <table>

                    <thead>
                        <tr>
                            <th>Fecha y hora (PR)</th>
                            <th>Evento</th>
                            <th>Detalle</th>
                        </tr>
                    </thead>

                    <tbody>
                    {% for evento in eventos %}
                        <tr>
                            <td>{{ evento.fecha }}</td>
                            <td>{{ evento.nombre }}</td>
                            <td>{{ evento.detail }}</td>
                        </tr>
                    {% endfor %}
                    </tbody>

                </table>
            </div>

            {% if not eventos %}
                <p>No hay eventos en esta consulta.</p>
            {% endif %}

            <a class="boton"
               href="{{ url_for(
                   'historial_pagina',
                   desde=desde,
                   hasta=hasta
               ) }}">
                Más recientes del periodo
            </a>

            {% if siguiente %}
                <a class="boton"
                   href="{{ url_for(
                       'historial_pagina',
                       desde=desde,
                       hasta=hasta,
                       antes=siguiente
                   ) }}">
                    Anteriores
                </a>
            {% endif %}

        {% endif %}

    </section>

    {% if admin and not error %}

        <section class="panel">

            <h2>Enviar historial por email</h2>

            <p>
                Se enviarán todos los eventos del periodo consultado,
                no solo esta página.
                Máximo {{ maximo }} eventos y
                10 destinatarios por envío.
            </p>

            <p>
                Marca solo quienes deban recibirlo.
                El correo puntual no se guardará
                en la lista automática.
            </p>

            {% if total > maximo %}
                <p class="aviso">
                    Selecciona un periodo más corto antes de enviar.
                </p>
            {% endif %}

            <form method="post"
                  action="{{ url_for('historial_enviar') }}">

                <input type="hidden"
                       name="csrf"
                       value="{{ csrf }}">

                <input type="hidden"
                       name="desde"
                       value="{{ desde }}">

                <input type="hidden"
                       name="hasta"
                       value="{{ hasta }}">

                {% for persona in destinatarios %}
                    <label>
                        <input type="checkbox"
                               name="destinatario"
                               value="{{ persona.id }}">
                        {{ persona.email }}
                    </label>
                {% endfor %}

                <label for="puntual">
                    Otro correo para este envío (opcional)
                </label>

                <input type="email"
                       id="puntual"
                       name="puntual"
                       maxlength="254"
                       placeholder="nombre@ejemplo.com">

                <p>
                    <button type="submit"
                            {% if not total or total > maximo %}
                                disabled
                            {% endif %}>
                        Enviar historial seleccionado
                    </button>
                </p>

            </form>

            <p class="nota">
                El envío contiene el historial en texto,
                sin gráfica adjunta.
                La aceptación por Gmail no garantiza
                entrega al buzón.
            </p>

        </section>

    {% elif not admin %}

        <section class="panel">
            <p>
                Consulta de solo lectura.
                El envío del historial requiere iniciar
                sesión como administrador.
            </p>
        </section>

    {% endif %}

</main>
</body>
</html>
"""


def periodo(desde, hasta):
    try:
        inicio = date.fromisoformat(desde)
        final = date.fromisoformat(hasta)

        if inicio > final:
            raise ValueError

        siguiente = final + timedelta(days=1)

    except (ValueError, TypeError, OverflowError):
        raise ValueError(
            "Selecciona un periodo de fechas válido."
        )

    return (
        datetime.combine(
            inicio,
            datetime.min.time(),
            ZONA_PR,
        ).isoformat(),
        datetime.combine(
            siguiente,
            datetime.min.time(),
            ZONA_PR,
        ).isoformat(),
    )


def consultar(store, desde, hasta, antes=None, limite=50):
    inicio, final = periodo(desde, hasta)

    condiciones = (
        "julianday(received_at) >= julianday(?) "
        "AND julianday(received_at) < julianday(?)"
    )

    with store._connect() as conexion:
        total = conexion.execute(
            "SELECT COUNT(*) FROM events WHERE " + condiciones,
            (inicio, final),
        ).fetchone()[0]

        valores = [inicio, final]

        if antes is not None:
            condiciones += " AND id < ?"
            valores.append(antes)

        valores.append(limite + 1)

        filas = conexion.execute(
            "SELECT id, received_at, kind, detail "
            "FROM events WHERE "
            + condiciones
            + " ORDER BY id DESC LIMIT ?",
            valores,
        ).fetchall()

    siguiente = (
        filas[limite - 1][0]
        if len(filas) > limite
        else None
    )

    eventos = []

    for identificador, instante, tipo, detalle in filas[:limite]:
        fecha = datetime.fromisoformat(
            instante
        ).astimezone(ZONA_PR)

        eventos.append({
            "id": identificador,
            "fecha": fecha.strftime(
                "%d/%m/%Y %I:%M:%S %p"
            ),
            "nombre": NOMBRES.get(tipo, tipo),
            "detail": detalle,
        })

    return eventos, total, siguiente


def configurar_historial(
    app,
    store,
    bloqueo_email,
    comando,
    actualizar,
    registrar,
):
    control = {
        "ultimo_envio": float("-inf")
    }

    @app.route("/historial")
    def historial_pagina():
        hoy = datetime.now(ZONA_PR).date().isoformat()

        desde = request.args.get("desde", hoy)
        hasta = request.args.get("hasta", hoy)
        admin = session.get("admin") is True

        error = None
        eventos = []
        total = 0
        siguiente = None

        try:
            antes = request.args.get("antes")
            antes = int(antes) if antes is not None else None

            if antes is not None and antes < 1:
                raise ValueError("Página inválida.")

            eventos, total, siguiente = consultar(
                store,
                desde,
                hasta,
                antes,
            )

        except ValueError as fallo:
            error = str(fallo)

        except Exception:
            app.logger.exception(
                "Error consultando historial"
            )
            error = (
                "No se pudo consultar el historial. "
                "Inténtalo nuevamente."
            )

        if admin and "csrf" not in session:
            session["csrf"] = secrets.token_hex(32)

        respuesta = app.make_response(
            render_template_string(
                PAGINA,
                desde=desde,
                hasta=hasta,
                admin=admin,
                error=error,
                eventos=eventos,
                total=total,
                siguiente=siguiente,
                destinatarios=(
                    listar_destinatarios()
                    if admin
                    else []
                ),
                csrf=session.get("csrf", ""),
                maximo=MAX_EVENTOS_EMAIL,
            )
        )

        respuesta.headers["Cache-Control"] = "no-store"
        return respuesta

    @app.route("/historial/enviar", methods=["POST"])
    def historial_enviar():
        if session.get("admin") is not True:
            abort(403)

        esperado = session.get("csrf", "")
        recibido = request.form.get("csrf", "")

        if (
            not esperado
            or not hmac.compare_digest(esperado, recibido)
        ):
            abort(
                400,
                description=(
                    "Formulario vencido. Recarga la página."
                ),
            )

        desde = request.form.get("desde", "")
        hasta = request.form.get("hasta", "")

        retorno = url_for(
            "historial_pagina",
            desde=desde,
            hasta=hasta,
        )

        try:
            guardados = {
                str(persona["id"]): persona["email"]
                for persona in listar_destinatarios()
            }

            seleccion = request.form.getlist(
                "destinatario"
            )

            if any(
                identificador not in guardados
                for identificador in seleccion
            ):
                raise ValueError(
                    "La lista cambió. "
                    "Recarga y selecciona nuevamente."
                )

            correos = [
                guardados[identificador]
                for identificador in seleccion
            ]

            puntual = request.form.get(
                "puntual", ""
            ).strip()

            if puntual:
                correos.append(validar_email(puntual))

            correos = list({
                correo.lower(): correo
                for correo in correos
            }.values())

            if not 1 <= len(correos) <= 10:
                raise ValueError(
                    "Selecciona entre 1 y 10 destinatarios."
                )

            eventos, total, _ = consultar(
                store,
                desde,
                hasta,
                limite=MAX_EVENTOS_EMAIL,
            )

            if total == 0:
                raise ValueError(
                    "No hay eventos en ese periodo."
                )

            if total > MAX_EVENTOS_EMAIL:
                raise ValueError(
                    "Hay más de 1000 eventos. "
                    "Selecciona un periodo más corto."
                )

        except ValueError as fallo:
            flash(str(fallo), "error")
            return redirect(retorno)

        except Exception:
            app.logger.exception(
                "Error preparando historial"
            )
            flash(
                "No se pudo preparar el historial.",
                "error",
            )
            return redirect(retorno)

        if not bloqueo_email.acquire(blocking=False):
            flash(
                "Hay otro envío en curso. "
                "Espera y vuelve a intentar.",
                "aviso",
            )
            return redirect(retorno)

        if (
            time.monotonic() - control["ultimo_envio"]
            < 30
        ):
            bloqueo_email.release()

            flash(
                "Espera 30 segundos entre envíos manuales.",
                "aviso",
            )
            return redirect(retorno)

        control["ultimo_envio"] = time.monotonic()

        inicio_enviado = False
        fin = "EMAIL_ERROR"
        estado = "error"
        mensaje = "No se pudo enviar el historial"
        tipo = "HISTORY_EMAIL_ERROR"

        try:
            inicio_enviado = comando("EMAIL_START")

            actualizar(
                "sending",
                "Enviando historial seleccionado",
                not inicio_enviado,
            )

            registrar(
                "HISTORY_EMAIL_START",
                f"Periodo {desde} a {hasta}; "
                f"{total} eventos; "
                f"{len(correos)} destinatario(s).",
            )

            lineas = [
                "DV POWER MONITOR — HISTORIAL",
                (
                    f"Periodo: {desde} a {hasta}, "
                    "ambas fechas incluidas (Puerto Rico)."
                ),
                (
                    f"Eventos incluidos: {total}. "
                    "Orden: más recientes primero."
                ),
                "",
                (
                    "Este envío puntual no modifica "
                    "las alertas automáticas."
                ),
                "",
            ]

            for evento in eventos:
                lineas.append(
                    f"{evento['fecha']} | "
                    f"{evento['nombre']} | "
                    f"{evento['detail']}"
                )

            resultado = enviar_email(
                (
                    "DV Power Monitor — Historial "
                    f"{desde} a {hasta}"
                ),
                "\n".join(lineas),
                destinatarios=correos,
            )

            aceptados = len(
                resultado["aceptados"]
            )
            rechazados = len(
                resultado["rechazados"]
            )

            if rechazados:
                estado = "partial"
                tipo = "HISTORY_EMAIL_PARTIAL"

                mensaje = (
                    f"Historial: {aceptados} aceptado(s), "
                    f"{rechazados} rechazado(s)"
                )

            else:
                fin = "EMAIL_DONE"
                estado = "sent"
                tipo = "HISTORY_EMAIL_ACCEPTED"

                mensaje = (
                    "Historial aceptado por Gmail para "
                    f"{aceptados} destinatario(s)"
                )

            flash(
                mensaje,
                "exito" if not rechazados else "aviso",
            )

        except Exception as fallo:
            app.logger.warning(
                "Falló email de historial: %s",
                type(fallo).__name__,
            )

            flash(
                "No se pudo completar el envío. "
                "Revisa el estado del email.",
                "error",
            )

        finally:
            fin_enviado = (
                comando(fin)
                if inicio_enviado
                else False
            )

            registrar(
                tipo,
                mensaje
                + f". Periodo: {desde} a {hasta}.",
            )

            actualizar(
                estado,
                mensaje,
                not inicio_enviado or not fin_enviado,
            )

            bloqueo_email.release()

        return redirect(retorno)