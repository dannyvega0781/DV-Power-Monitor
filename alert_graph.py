import io
import threading
from collections import deque
from datetime import datetime, timedelta, timezone

import matplotlib

# Permite generar imágenes sin abrir ventanas.
matplotlib.use("Agg")

import matplotlib.dates as mdates
from matplotlib.figure import Figure


ZONA_PR = timezone(timedelta(hours=-4))
bloqueo_grafica = threading.Lock()


class HistorialGrafica:
    def __init__(self):
        self._muestras = deque(maxlen=1200)
        self._lock = threading.Lock()
        self._stop = threading.Event()
        self._thread = None

    def start(self, reader):
        self._stop.clear()

        self._thread = threading.Thread(
            target=self._capturar,
            args=(reader,),
            name="historial-grafica",
            daemon=True,
        )
        self._thread.start()

    def stop(self):
        self._stop.set()

        if self._thread:
            self._thread.join(timeout=2)

    def _capturar(self, reader):
        ultima_fecha = None

        while not self._stop.is_set():
            datos = reader.snapshot()

            if datos["data_valid"]:
                muestra = datos["measurement"]

                if muestra["received_at"] != ultima_fecha:
                    ultima_fecha = muestra["received_at"]

                    with self._lock:
                        self._muestras.append(dict(muestra))

            self._stop.wait(0.1)

    def crear_imagen(self, evento):
        fecha_evento = datetime.fromisoformat(
            evento["received_at"]
        )

        inicio = fecha_evento - timedelta(seconds=60)

        with self._lock:
            muestras = [
                dict(muestra)
                for muestra in self._muestras
                if inicio <= datetime.fromisoformat(
                    muestra["received_at"]
                ) <= fecha_evento
            ]

        # Asegurar que la lectura que disparó la alerta
        # esté incluida aunque el capturador aún no la tenga.
        muestras = [
            muestra
            for muestra in muestras
            if muestra["received_at"] != evento["received_at"]
        ]
        muestras.append(dict(evento))

        muestras.sort(key=lambda muestra: muestra["received_at"])

        fechas = [
            datetime.fromisoformat(muestra["received_at"])
            .astimezone(ZONA_PR)
            for muestra in muestras
        ]

        instante = fecha_evento.astimezone(ZONA_PR)

        descripcion = {
            "UNA_CARGA": "Consumo reducido",
            "SIN_CARGA": "Sin consumo de las cargas",
            "NORMAL": "Consumo normal",
        }.get(evento["state"], evento["state"])

        with bloqueo_grafica:
            figura = Figure(
                figsize=(11, 8),
                dpi=140,
                facecolor="#0b1220",
            )

            ejes = figura.subplots(3, 1, sharex=True)

            series = [
                ("voltage", "Voltaje (V)", "#38bdf8"),
                ("current_a", "Corriente (A)", "#34d399"),
                ("power_w", "Potencia (W)", "#fbbf24"),
            ]

            for eje, (campo, etiqueta, color) in zip(ejes, series):
                eje.set_facecolor("#172033")

                eje.plot(
                    fechas,
                    [muestra[campo] for muestra in muestras],
                    color=color,
                    linewidth=1.8,
                    marker=".",
                    markersize=3,
                )

                eje.axvline(
                    instante,
                    color="#f87171",
                    linestyle="--",
                    linewidth=1.5,
                )

                eje.scatter(
                    [instante],
                    [evento[campo]],
                    color="#f87171",
                    s=45,
                    zorder=5,
                )

                eje.set_ylabel(etiqueta, color=color)
                eje.tick_params(colors="#cbd5e1")
                eje.grid(color="#334155", alpha=0.6)

                for borde in eje.spines.values():
                    borde.set_color("#475569")

            ejes[1].axhline(
                0.040,
                color="#f87171",
                linestyle=":",
                label="Umbral sin carga: 0.040 A",
            )

            ejes[1].axhline(
                0.247,
                color="#c4b5fd",
                linestyle=":",
                label="Umbral normal: 0.247 A",
            )

            ejes[1].legend(
                loc="best",
                facecolor="#172033",
                edgecolor="#475569",
                labelcolor="white",
                fontsize=8,
            )

            ejes[-1].xaxis.set_major_formatter(
                mdates.DateFormatter(
                    "%H:%M:%S",
                    tz=ZONA_PR,
                )
            )

            ejes[-1].set_xlabel(
                "Hora de recepción — Puerto Rico (UTC-4)",
                color="#cbd5e1",
            )

            figura.suptitle(
                "DV Power Monitor\n"
                f"{descripcion} — {instante:%d/%m/%Y %H:%M:%S}",
                color="white",
                fontsize=15,
            )

            figura.text(
                0.08,
                0.035,
                "Rojo: lectura que originó el aviso. "
                f"Muestras disponibles: {len(muestras)}.\n"
                "Ventana de hasta 60 s previos. "
                "No se identifica la causa física ni el grupo afectado.",
                color="#cbd5e1",
                fontsize=9,
            )

            figura.subplots_adjust(
                top=0.88,
                bottom=0.14,
                left=0.10,
                right=0.97,
                hspace=0.15,
            )

            salida = io.BytesIO()
            figura.savefig(
                salida,
                format="png",
                facecolor=figura.get_facecolor(),
            )

            return salida.getvalue()