"""Inicia en Windows la misma aplicación copiada desde la Raspberry Pi."""
import getpass
import json
import os
import re
import runpy
import secrets
import socket
import sys
import threading
import time
import urllib.request
import webbrowser
from pathlib import Path

ROOT = Path(__file__).resolve().parent


def validar_configuracion(datos):
    nombres = ("DV_EMAIL_USER", "DV_EMAIL_PASSWORD", "DV_ADMIN_PASSWORD", "DV_SESSION_SECRET")
    if not isinstance(datos, dict) or any(
        not isinstance(datos.get(nombre), str) or not datos[nombre] for nombre in nombres
    ):
        raise ValueError("La configuración está incompleta.")
    if not re.fullmatch(r"[^\s@]+@[^\s@]+\.[^\s@]+", datos["DV_EMAIL_USER"]):
        raise ValueError("El correo remitente no es válido.")
    datos["DV_EMAIL_PASSWORD"] = datos["DV_EMAIL_PASSWORD"].replace(" ", "").strip()
    if len(datos["DV_EMAIL_PASSWORD"]) != 16:
        raise ValueError("La contraseña de aplicación de Gmail debe tener 16 caracteres.")
    return {nombre: datos[nombre] for nombre in nombres}


def cargar_configuracion(archivo, forzar=False):
    archivo = Path(archivo)
    if archivo.is_file() and not forzar:
        return validar_configuracion(json.loads(archivo.read_text(encoding="utf-8")))
    print("CONFIGURACIÓN INICIAL DE LA LAPTOP")
    print("Las contraseñas no se muestran al escribirlas.")
    correo = input("Correo remitente [dvmonitor.alertas@gmail.com]: ").strip()
    clave = getpass.getpass("Contraseña de aplicación de Gmail: ")
    admin = getpass.getpass("Contraseña del administrador: ")
    confirmar = getpass.getpass("Confirma la contraseña del administrador: ")
    if not admin or admin != confirmar:
        raise ValueError("Las contraseñas del administrador no coinciden o están vacías.")
    datos = validar_configuracion({
        "DV_EMAIL_USER": correo or "dvmonitor.alertas@gmail.com",
        "DV_EMAIL_PASSWORD": clave,
        "DV_ADMIN_PASSWORD": admin,
        "DV_SESSION_SECRET": secrets.token_hex(32),
    })
    archivo.parent.mkdir(parents=True, exist_ok=True)
    temporal = archivo.with_suffix(".tmp")
    descriptor = os.open(temporal, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(descriptor, "w", encoding="utf-8") as salida:
        json.dump(datos, salida, ensure_ascii=False)
    temporal.replace(archivo)
    print("Configuración guardada para este usuario de Windows.")
    return datos


def elegir_puerto(puertos):
    if not puertos:
        raise RuntimeError("No se detectaron puertos. Conecta el Arduino por USB a la laptop.")
    print("\nPUERTOS DISPONIBLES")
    for numero, puerto in enumerate(puertos, 1):
        print(f"{numero}. {puerto.device} - {puerto.description}")
    if len(puertos) == 1:
        print("Se utilizará el único puerto disponible.")
        return puertos[0].device
    while True:
        valor = input("Número del puerto del Arduino: ").strip()
        if valor.isdigit() and 1 <= int(valor) <= len(puertos):
            return puertos[int(valor) - 1].device
        print("Selecciona uno de los números de la lista.")


def comprobar_puerto_web():
    with socket.socket() as conexion:
        conexion.settimeout(1)
        if conexion.connect_ex(("127.0.0.1", 5000)) == 0:
            raise RuntimeError("El puerto 5000 ya está ocupado. Cierra la otra instancia del servidor.")


def abrir_dashboard():
    for _ in range(60):
        try:
            with urllib.request.urlopen("http://127.0.0.1:5000/", timeout=1) as respuesta:
                if respuesta.status == 200:
                    webbrowser.open("http://127.0.0.1:5000/")
                    return
        except Exception:
            pass
        time.sleep(0.5)
    print("Si el navegador no abrió, visita http://127.0.0.1:5000/")


def main():
    from serial.tools import list_ports

    os.chdir(ROOT)
    sys.path.insert(0, str(ROOT))
    if not (ROOT / "iniciar_app.py").is_file():
        raise RuntimeError("Coloca lanzar_windows.py junto a iniciar_app.py.")
    comprobar_puerto_web()
    carpeta = Path(os.environ.get("LOCALAPPDATA") or Path.home()) / "DVPowerMonitor"
    configuracion = cargar_configuracion(
        carpeta / "config.json", forzar="--configurar" in sys.argv,
    )
    os.environ.update(configuracion)
    os.environ["MPLBACKEND"] = "Agg"
    puertos = sorted(list_ports.comports(), key=lambda puerto: puerto.device)
    puerto = elegir_puerto(puertos)

    # main se importa una sola vez. El lector todavía no se ha iniciado.
    import main as sistema
    sistema.reader.port = puerto

    print(f"\nArduino seleccionado: {puerto}")
    print("Dashboard de la laptop: http://127.0.0.1:5000/")
    print("Desde otros dispositivos usa la dirección que Flask muestra como Running on.")
    print("Conserva esta ventana abierta durante la demostración.")
    threading.Thread(target=abrir_dashboard, daemon=True).start()
    runpy.run_path(str(ROOT / "iniciar_app.py"), run_name="__main__")


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\nPrograma detenido.")
    except Exception as error:
        print(f"\nNo se pudo iniciar: {type(error).__name__}: {error}")
        sys.exit(1)
