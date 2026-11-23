import sys
import threading
import time
from datetime import datetime, timedelta, timezone

from flask import (
    Flask,
    jsonify,
    render_template,
    request,
    url_for,
)

from alert_graph import HistorialGrafica
from history_page import configurar_historial
from notifications import enviar_email, probar_email
from serial_reader import SerialReader
from storage import Storage


app = Flask(__name__)

reader = SerialReader(port='/dev/serial/by-id/usb-Arduino__www.arduino.cc__0042_2433331393035101F1C1-if00', baudrate=9600)
historial = HistorialGrafica()
event_store = Storage()

detener_monitor = threading.Event()
bloqueo_email = threading.Lock()
bloqueo_estado_email = threading.Lock()

estado_email = {
    "status": "idle",
    "message": "Esperando una alerta",
    "updated_at": None,
    "led_warning": False,
}


def actualizar_estado_email(status, message, led_warning=False):
    with bloqueo_estado_email:
        estado_email.update({
            "status": status,
            "message": message,
            "updated_at": datetime.now(
                timezone.utc
            ).isoformat(),
            "led_warning": led_warning,
        })


def fecha_puerto_rico(fecha_iso):
    zona = timezone(timedelta(hours=-4))

    return datetime.fromisoformat(
        fecha_iso
    ).astimezone(zona).strftime(
        "%d/%m/%Y %I:%M:%S %p"
    )


@app.route("/")
def inicio():
    pagina = render_template("dashboard.html")

    script = (
        '<script src="'
        + url_for(
            "static",
            filename="js/email_estado.js",
            v="1",
        )
        + '"></script>'
    )

    return pagina.replace(
        "</body>",
        script + "\n</body>",
        1,
    )


@app.route("/api/mediciones")
def mediciones():
    response = jsonify(reader.snapshot())
    response.headers["Cache-Control"] = "no-store"
    return response


@app.route("/api/email/estado")
def consultar_estado_email():
    with bloqueo_estado_email:
        datos = dict(estado_email)

    response = jsonify(datos)
    response.headers["Cache-Control"] = "no-store"
    return response


@app.route("/api/eventos")
def consultar_eventos():
    try:
        limit = int(request.args.get("limit", "50"))

        before = request.args.get("before_id")
        before = int(before) if before is not None else None

        if not 1 <= limit <= 100:
            raise ValueError

        if before is not None and before < 1:
            raise ValueError

    except (TypeError, ValueError):
        return jsonify({
            "error": "Parámetros de historial inválidos"
        }), 400

    try:
        datos = event_store.list_events(limit, before)

    except Exception:
        app.logger.exception(
            "No se pudo consultar el historial"
        )

        return jsonify({
            "error": "Historial temporalmente no disponible"
        }), 503

    response = jsonify(datos)
    response.headers["Cache-Control"] = "no-store"
    return response


def registrar_evento(kind, detail):
    try:
        event_store.add_event(kind, detail)

    except Exception:
        app.logger.exception(
            "No se pudo registrar el evento %s",
            kind,
        )


def comando_seguro(comando):
    try:
        reader.send_command(comando)
        return True

    except (ConnectionError, OSError, ValueError):
        print(f"[LED] No se pudo enviar {comando}.")
        return False


def preparar_alerta(medicion):
    if medicion["state"] == "UNA_CARGA":
        titulo = "Consumo reducido"

        explicacion = (
            "Arduino clasificó la corriente total en el intervalo "
            "desde 40 mA hasta menos de 247 mA."
        )

    elif medicion["state"] == "SIN_CARGA":
        titulo = "Sin consumo de las cargas"

        explicacion = (
            "Arduino confirmó corriente total inferior a 40 mA."
        )

    else:
        raise ValueError(
            "El estado no corresponde a una alerta."
        )

    contenido = (
        "DV POWER MONITOR — ALERTA AUTOMÁTICA\n\n"
        f"Condición detectada: {titulo}\n"
        f"Estado: {medicion['state']}\n"
        "Fecha de recepción: "
        f"{fecha_puerto_rico(medicion['received_at'])}"
        " — Puerto Rico\n\n"
        "MEDICIONES RECIBIDAS\n"
        f"Voltaje: {medicion['voltage']:.3f} V\n"
        f"Corriente total: {medicion['current_a']:.4f} A\n"
        f"Potencia total: {medicion['power_w']:.3f} W\n\n"
        "CRITERIO DE DETECCIÓN\n"
        f"{explicacion}\n"
        "Los cambios posteriores a la primera lectura "
        "requieren 2 segundos de confirmación en Arduino.\n\n"
        "REVISIÓN SUGERIDA\n"
        "Comprueba la fuente de 12 V, los interruptores físicos, "
        "las cargas y sus conexiones.\n\n"
        "Un INA219 mide el consumo total: no identifica el grupo "
        "afectado ni confirma la causa física.\n"
    )

    return f"DV Power Monitor — {titulo}", contenido


def enviar_alerta(medicion):
    with bloqueo_email:
        inicio_enviado = comando_seguro("EMAIL_START")

        actualizar_estado_email(
            "sending",
            "Preparando gráfica y enviando alerta",
            not inicio_enviado,
        )

        registrar_evento(
            "EMAIL_START",
            f"Intento de alerta por {medicion['state']}. "
            f"Lectura: {medicion['received_at']}.",
        )

        comando_final = "EMAIL_ERROR"
        estado_final = "error"
        mensaje_final = "No se pudo completar el envío"

        try:
            asunto, contenido = preparar_alerta(medicion)
            imagen = None

            try:
                imagen = historial.crear_imagen(medicion)

                contenido += (
                    "\nGRÁFICA ADJUNTA\n"
                    "La marca roja señala la lectura que originó "
                    "el aviso. Se incluyen las muestras disponibles "
                    "de hasta 60 segundos previos.\n"
                    "No es una captura del navegador.\n"
                )

            except Exception as error:
                print(
                    "[GRAFICA] Falló la generación: "
                    f"{type(error).__name__}"
                )

                registrar_evento(
                    "GRAPH_ERROR",
                    "No se generó la imagen; "
                    "se intentará enviar el texto.",
                )

                contenido += (
                    "\nNo se pudo generar la gráfica adjunta. "
                    "Se envían las mediciones en texto.\n"
                )

            resultado = enviar_email(
                asunto,
                contenido,
                imagen_png=imagen,
            )

            aceptados = len(resultado["aceptados"])
            rechazados = len(resultado["rechazados"])

            print(
                f"[EMAIL] Aceptados: {aceptados}. "
                f"Rechazados: {rechazados}. "
                f"Gráfica adjunta: {'sí' if imagen else 'no'}."
            )

            if rechazados:
                estado_final = "partial"

                mensaje_final = (
                    f"Envío parcial: {aceptados} aceptado(s), "
                    f"{rechazados} rechazado(s)"
                )

            else:
                comando_final = "EMAIL_DONE"
                estado_final = "sent"

                mensaje_final = (
                    f"Alerta aceptada para {aceptados} destinatario(s)"
                    + (
                        " — Gráfica adjunta"
                        if imagen is not None
                        else " — Sin gráfica"
                    )
                )

            return rechazados == 0

        except Exception as error:
            print(
                "[EMAIL] Falló el envío: "
                f"{type(error).__name__}. "
                "Revisa Internet y la configuración."
            )
            return False

        finally:
            fin_enviado = True

            if inicio_enviado:
                fin_enviado = comando_seguro(comando_final)

            tipos = {
                "sent": "EMAIL_ACCEPTED",
                "partial": "EMAIL_PARTIAL",
                "error": "EMAIL_ERROR",
            }

            registrar_evento(
                tipos[estado_final],
                mensaje_final,
            )

            if not inicio_enviado or not fin_enviado:
                registrar_evento(
                    "LED_COMMAND_ERROR",
                    "No se pudo escribir uno de los comandos "
                    "del LED azul.",
                )

            actualizar_estado_email(
                estado_final,
                mensaje_final,
                not inicio_enviado or not fin_enviado,
            )


def vigilar_estados():
    ultimo_estado = None
    ultima_muestra = None

    print("[MONITOR] Vigilancia automática iniciada.")

    while not detener_monitor.is_set():
        datos = reader.snapshot()

        if not datos["data_valid"]:
            detener_monitor.wait(0.2)
            continue

        medicion = datos["measurement"]

        if medicion["received_at"] == ultima_muestra:
            detener_monitor.wait(0.2)
            continue

        ultima_muestra = medicion["received_at"]
        estado = medicion["state"]

        if estado == ultimo_estado:
            detener_monitor.wait(0.2)
            continue

        anterior = ultimo_estado
        ultimo_estado = estado

        print(
            f"[MONITOR] Estado: {anterior or 'INICIO'} "
            f"-> {estado}"
        )

        if estado == "NORMAL":
            print(
                "[MONITOR] Preparado para una nueva falla."
            )

        elif not enviar_alerta(medicion):
            print(
                "[MONITOR] Envío incompleto. "
                "Sin reintento automático en esta etapa."
            )

        detener_monitor.wait(0.2)


def probar_email_con_led():
    reader.start()
    led_iniciado = False
    comando_final = "EMAIL_ERROR"
    correcto = False

    try:
        print(
            "[PRUEBA] Esperando una lectura válida, máximo 15 s."
        )

        limite = time.monotonic() + 15

        while time.monotonic() < limite:
            if reader.snapshot()["data_valid"]:
                break
            time.sleep(0.1)

        else:
            print("[PRUEBA] No llegaron mediciones válidas.")
            return False

        reader.send_command("EMAIL_START")
        led_iniciado = True
        time.sleep(3)

        correcto = probar_email()

        if correcto:
            comando_final = "EMAIL_DONE"

    except (ConnectionError, OSError, ValueError):
        print("[PRUEBA] Falló la comunicación con Arduino.")
        correcto = False

    finally:
        if led_iniciado:
            comando_seguro(comando_final)
            time.sleep(0.3)

        reader.stop()

    return correcto


configurar_historial(
    app,
    event_store,
    bloqueo_email,
    comando_seguro,
    actualizar_estado_email,
    registrar_evento,
)


if __name__ == "__main__":
    if "--probar-email-led" in sys.argv:
        try:
            correcto = probar_email_con_led()
        except KeyboardInterrupt:
            correcto = False

        sys.exit(0 if correcto else 1)

    if "--probar-email" in sys.argv:
        sys.exit(0 if probar_email() else 1)

    reader.start()
    historial.start(reader)

    monitor = threading.Thread(
        target=vigilar_estados,
        name="monitor-alertas",
        daemon=True,
    )
    monitor.start()

    print("\nDV POWER MONITOR")
    print("Alertas automáticas con gráfica: ACTIVAS")
    print("Laptop: http://127.0.0.1:5000/")
    print("Celular: http://192.168.1.153:5000/\n")

    try:
        app.run(
            host="0.0.0.0",
            port=5000,
            debug=False,
            use_reloader=False,
        )

    finally:
        detener_monitor.set()
        monitor.join(timeout=2)
        historial.stop()
        comando_seguro("EMAIL_ERROR")
        reader.stop()