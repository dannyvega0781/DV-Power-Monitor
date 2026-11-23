import json
import math
import time
from datetime import datetime

import serial


PUERTO = "COM7"
BAUDIOS = 9600

ESTADOS_VALIDOS = {
    "NORMAL",
    "UNA_CARGA",
    "SIN_CARGA",
}


def validar_medicion(datos):
    if not isinstance(datos, dict):
        raise ValueError("El mensaje no es un objeto JSON.")

    if "error" in datos:
        raise ValueError(f"Arduino reportó un error: {datos['error']}")

    campos = ("voltage", "current_ma", "power_mw", "state")

    for campo in campos:
        if campo not in datos:
            raise ValueError(f"Falta el campo: {campo}")

    for campo in ("voltage", "current_ma", "power_mw"):
        valor = datos[campo]

        if isinstance(valor, bool) or not isinstance(valor, (int, float)):
            raise ValueError(f"{campo} debe ser numérico.")

        if not math.isfinite(valor):
            raise ValueError(f"{campo} contiene un valor no válido.")

    if datos["state"] not in ESTADOS_VALIDOS:
        raise ValueError(f"Estado desconocido: {datos['state']}")

    return datos


def main():
    print("DV POWER MONITOR — PRUEBA SERIAL")
    print(f"Puerto: {PUERTO} | Velocidad: {BAUDIOS} baudios")
    print("Cierra el Monitor serial y el Serial Plotter del Arduino IDE.")
    print("Para terminar, presiona Ctrl+C en esta consola.\n")

    try:
        with serial.Serial(
            port=PUERTO,
            baudrate=BAUDIOS,
            timeout=1,
        ) as arduino:
            print("Puerto abierto. El Arduino puede reiniciarse.")
            print("Esperando mediciones...\n")

            ultima_recepcion = time.monotonic()
            aviso_sin_datos = False
            buffer = b""

            while True:
                fragmento = arduino.read_until(b"\n")
                ahora = time.monotonic()

                if fragmento:
                    buffer += fragmento

                    if len(buffer) > 4096:
                        print("AVISO: mensaje demasiado largo; se descarta.")
                        buffer = b""
                        continue

                    if buffer.endswith(b"\n"):
                        mensaje = buffer
                        buffer = b""

                        try:
                            linea = mensaje.decode("utf-8").strip()

                            if not linea:
                                continue

                            datos = validar_medicion(json.loads(linea))

                            voltaje = datos["voltage"]
                            corriente_a = datos["current_ma"] / 1000
                            potencia_w = datos["power_mw"] / 1000
                            estado = datos["state"]

                            hora = datetime.now().strftime("%H:%M:%S")

                            print(
                                f"{hora} | "
                                f"V: {voltaje:.3f} V | "
                                f"I: {corriente_a:.4f} A | "
                                f"P: {potencia_w:.3f} W | "
                                f"Estado: {estado}"
                            )

                            ultima_recepcion = ahora
                            aviso_sin_datos = False

                        except (
                            UnicodeDecodeError,
                            json.JSONDecodeError,
                            ValueError,
                            TypeError,
                        ) as error:
                            print(f"AVISO: {error}")

                if ahora - ultima_recepcion >= 5 and not aviso_sin_datos:
                    print(
                        "AVISO: no se han recibido mediciones válidas "
                        "durante 5 segundos."
                    )
                    aviso_sin_datos = True

    except serial.SerialException as error:
        print(f"\nERROR SERIAL: {error}")
        print(
            "Verifica COM7, el cable USB y que ninguna otra "
            "aplicación esté utilizando el puerto."
        )

    except KeyboardInterrupt:
        print("\nPrueba terminada.")

    finally:
        print("Conexión serial cerrada.")


if __name__ == "__main__":
    main()