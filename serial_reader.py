import json
import math
import threading
import time
from datetime import datetime, timezone

import serial

from storage import Storage


class SerialReader:
    def __init__(self, port="COM7", baudrate=9600):
        self.port = port
        self.baudrate = baudrate

        self._lock = threading.Lock()
        self._connection_lock = threading.Lock()
        self._stop = threading.Event()
        self._thread = None
        self._connection = None

        self._connected = False
        self._measurement = None
        self._last_valid_time = None
        self._last_error = None
        self._invalid_messages = 0

        self._storage = Storage()
        self._energy_wh = self._storage.load_energy()
        self._storage_error = None
        self._stored_measurements = 0

        self._previous_time = None
        self._previous_power = None
        self._previous_state = None
        self._session_started = False

    def start(self):
        if self._thread and self._thread.is_alive():
            return

        self._stop.clear()

        self._thread = threading.Thread(
            target=self._run,
            name="arduino-serial",
            daemon=True,
        )
        self._thread.start()

    def stop(self):
        self._stop.set()

        if self._thread:
            self._thread.join(timeout=3)

    def send_command(self, command):
        allowed = {
            "EMAIL_START",
            "EMAIL_DONE",
            "EMAIL_ERROR",
        }

        if command not in allowed:
            raise ValueError("Comando no permitido.")

        with self._connection_lock:
            connection = self._connection

            if connection is None or not connection.is_open:
                raise ConnectionError("Arduino no está conectado.")

            message = (command + "\n").encode("ascii")
            written = connection.write(message)

            if written != len(message):
                raise ConnectionError("El comando quedó incompleto.")

        print(f"[SERIAL] Comando enviado: {command}")

    def snapshot(self):
        with self._lock:
            age = None

            if self._last_valid_time is not None:
                age = time.monotonic() - self._last_valid_time

            valid = (
                self._connected
                and age is not None
                and age < 5
            )

            return {
                "mode": "REAL",
                "serial_connected": self._connected,
                "data_valid": valid,
                "port": self.port,
                "baudrate": self.baudrate,
                "age_seconds": (
                    round(age, 2) if age is not None else None
                ),
                "measurement": (
                    dict(self._measurement)
                    if self._measurement is not None
                    else None
                ),
                "energy_wh": self._energy_wh,
                "storage_ok": self._storage_error is None,
                "storage_error": self._storage_error,
                "stored_measurements_this_run": (
                    self._stored_measurements
                ),
                "last_error": self._last_error,
                "invalid_messages": self._invalid_messages,
            }

    @staticmethod
    def _validate(data):
        if not isinstance(data, dict):
            raise ValueError("El JSON debe ser un objeto.")

        if "error" in data:
            raise ValueError(
                f"Arduino reportó: {data['error']}"
            )

        for field in ("voltage", "current_ma", "power_mw"):
            value = data.get(field)

            if (
                isinstance(value, bool)
                or not isinstance(value, (int, float))
                or not math.isfinite(value)
            ):
                raise ValueError(
                    f"Campo ausente o inválido: {field}"
                )

        state = data.get("state")

        if (
            not isinstance(state, str)
            or state not in {
                "NORMAL",
                "UNA_CARGA",
                "SIN_CARGA",
            }
        ):
            raise ValueError("Estado ausente o inválido.")

        return {
            "voltage": data["voltage"],
            "current_ma": data["current_ma"],
            "power_mw": data["power_mw"],
            "current_a": data["current_ma"] / 1000,
            "power_w": data["power_mw"] / 1000,
            "state": state,
            "received_at": datetime.now(
                timezone.utc
            ).isoformat(),
        }

    def _register_invalid(self, error, raw):
        detail = f"{error}; mensaje recibido: {raw[:160]!r}"

        with self._lock:
            self._invalid_messages += 1
            self._last_error = detail

        print(f"[SERIAL] Mensaje descartado: {detail}")

    def _process_measurement(self, measurement):
        now = time.monotonic()

        with self._lock:
            energy = self._energy_wh

        events = []

        if not self._session_started:
            events.append((
                "SESSION_START",
                "Primera lectura de esta ejecución. "
                "Energía anterior recuperada de SQLite.",
            ))

        if self._previous_time is None:
            if self._session_started:
                events.append((
                    "ACQUISITION_RESUMED",
                    "Adquisición reanudada. No se estimó energía "
                    "durante la desconexión.",
                ))

        else:
            elapsed = now - self._previous_time

            if 0 < elapsed <= 2:
                # Energía de consumo: no restar por lecturas
                # negativas pequeñas del sensor.
                previous_power = max(self._previous_power, 0.0)
                current_power = max(measurement["power_w"], 0.0)

                energy += (
                    (previous_power + current_power)
                    / 2
                    * elapsed
                    / 3600
                )

            else:
                events.append((
                    "MEASUREMENT_GAP",
                    f"Intervalo de {elapsed:.3f} segundos. "
                    "No se sumó energía en ese intervalo.",
                ))

        if measurement["state"] != self._previous_state:
            events.append((
                "STATE_CHANGE",
                f"{self._previous_state or 'INICIO'}"
                f" -> {measurement['state']}",
            ))

        storage_error = None
        saved = False

        try:
            self._storage.save_measurement(
                measurement,
                energy,
                events,
            )
            saved = True

        except Exception as error:
            storage_error = type(error).__name__

            with self._lock:
                previous_error = self._storage_error

            if previous_error != storage_error:
                print(
                    "[SQLITE] No se pudo guardar la lectura. "
                    f"Tipo: {storage_error}. "
                    "La adquisición continúa."
                )

        self._session_started = True
        self._previous_time = now
        self._previous_power = measurement["power_w"]
        self._previous_state = measurement["state"]

        measurement["energy_wh"] = energy

        with self._lock:
            self._measurement = measurement
            self._last_valid_time = now
            self._last_error = None
            self._energy_wh = energy
            self._storage_error = storage_error

            if saved:
                self._stored_measurements += 1

    def _run(self):
        while not self._stop.is_set():
            connection = None

            try:
                print(
                    f"[SERIAL] Abriendo {self.port} "
                    f"a {self.baudrate} baudios..."
                )

                connection = serial.Serial(
                    port=self.port,
                    baudrate=self.baudrate,
                    timeout=1,
                    write_timeout=2,
                )

                with self._connection_lock:
                    self._connection = connection

                self._previous_time = None
                self._previous_power = None

                with self._lock:
                    self._connected = True
                    self._last_valid_time = None

                print(
                    "[SERIAL] Puerto abierto. "
                    "Esperando mediciones."
                )

                buffer = b""

                while not self._stop.is_set():
                    fragment = connection.read_until(b"\n")

                    if not fragment:
                        continue

                    buffer += fragment

                    if len(buffer) > 4096:
                        self._register_invalid(
                            "Mensaje demasiado largo",
                            buffer,
                        )
                        buffer = b""
                        continue

                    if not buffer.endswith(b"\n"):
                        continue

                    raw = buffer
                    buffer = b""

                    if not raw.strip():
                        continue

                    try:
                        text = raw.decode("utf-8").strip()
                        measurement = self._validate(
                            json.loads(text)
                        )

                    except (
                        UnicodeDecodeError,
                        ValueError,
                        TypeError,
                    ) as error:
                        self._register_invalid(error, raw)
                        continue

                    self._process_measurement(measurement)

            except (serial.SerialException, OSError) as error:
                with self._lock:
                    self._last_error = str(error)

                print(f"[SERIAL] Error: {error}")

            finally:
                with self._connection_lock:
                    self._connection = None

                    if connection is not None:
                        connection.close()

                with self._lock:
                    self._connected = False

            if not self._stop.is_set():
                print(
                    "[SERIAL] Reintentando conexión "
                    "en 3 segundos..."
                )
                self._stop.wait(3)