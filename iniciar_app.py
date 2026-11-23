import threading

import iniciar_dashboard as base

from users import configurar_usuarios
from exportaciones import configurar_exportaciones


app = base.app
sistema = base.sistema

configurar_usuarios(base)

configurar_exportaciones(
    app,
    sistema.event_store,
)


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
    print("Adquisición y alertas generales: ACTIVAS")
    print("Portada, administrador y usuarios: HABILITADOS")
    print("Avisos personales: correo verificado, con o sin sesión")
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