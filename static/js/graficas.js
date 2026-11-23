/* ==========================================
   DV POWER MONITOR
   Mediciones reales + energía desde Python
   Simulación separada: /?modo=simulacion
   ========================================== */

"use strict";

const parametros = new URLSearchParams(window.location.search);

const modoSimulacion =
    parametros.get("modo") === "simulacion";

const intervaloMs = 500;
const maxMuestras = 100;

let energiaSimulada = 0;
let ultimoTiempoSimulado = null;
let ultimaMuestra = null;
let ultimaMedicion = null;
let alertaReconocida = false;
let claveAlerta = null;
let consultaActiva = false;

const elemento = id => document.getElementById(id);

const led1 = elemento("led1");
const led2 = elemento("led2");
const simularFalla = elemento("simularFalla");
const estadoAlerta = elemento("estadoAlerta");
const indicadorAlerta = elemento("indicadorAlerta");
const botonReset = elemento("botonReset");
const botonEmail = elemento("botonEmail");
const estadoEmail = elemento("estadoEmail");
const indicadorEmail = elemento("indicadorEmail");

function serie(nombre, color, eje) {
    return {
        label: nombre,
        data: [],
        borderColor: color,
        backgroundColor: color,
        yAxisID: eje,
        tension: 0.25,
        borderWidth: 2,
        pointRadius: 2,
        pointHoverRadius: 5
    };
}

function eje(posicion, color, mostrarGrid = false) {
    return {
        type: "linear",
        position: posicion,
        ticks: {
            color,
            maxTicksLimit: 6
        },
        grid: {
            drawOnChartArea: mostrarGrid,
            color: "#334155"
        },
        title: {
            display: false
        }
    };
}

let grafica = null;

if (typeof Chart !== "undefined") {
    grafica = new Chart(
        elemento("graficaTelemetria"),
        {
            type: "line",
            data: {
                labels: [],
                datasets: [
                    serie("Voltaje (V)", "#38bdf8", "voltaje"),
                    serie("Corriente (A)", "#34d399", "corriente"),
                    serie("Potencia (W)", "#fbbf24", "potencia"),
                    serie("Energía (Wh)", "#c4b5fd", "energia")
                ]
            },
            options: {
                responsive: true,
                maintainAspectRatio: false,
                animation: false,
                interaction: {
                    mode: "index",
                    intersect: false
                },
                plugins: {
                    legend: {
                        onClick: (evento, item, legend) => {
                            const chart = legend.chart;
                            const indice = item.datasetIndex;

                            chart.setDatasetVisibility(
                                indice,
                                !chart.isDatasetVisible(indice)
                            );

                            chart.update();
                        },
                        labels: {
                            color: "#ffffff",
                            usePointStyle: true,
                            padding: 15
                        }
                    },
                    tooltip: {
                        mode: "index",
                        intersect: false
                    }
                },
                scales: {
                    x: {
                        ticks: {
                            color: "#94a3b8",
                            maxTicksLimit: 6
                        },
                        grid: {
                            color: "#253247"
                        },
                        title: {
                            display: true,
                            text: "Hora de recepción — Puerto Rico",
                            color: "#94a3b8"
                        }
                    },
                    voltaje: eje("left", "#38bdf8", true),
                    corriente: eje("right", "#34d399"),
                    potencia: eje("left", "#fbbf24"),
                    energia: eje("right", "#c4b5fd")
                }
            }
        }
    );
}

const formatoHora = new Intl.DateTimeFormat("es-PR", {
    timeZone: "America/Puerto_Rico",
    hour: "2-digit",
    minute: "2-digit",
    second: "2-digit",
    hour12: false
});

function cambiarIndicador(id, clase) {
    elemento(id).className = "led-indicador " + clase;
}

function configurarPantalla() {
    document.querySelector(
        ".encabezado-titulo h3"
    ).textContent = modoSimulacion
        ? "MODO SIMULACIÓN"
        : "MODO REAL";

    const panelGrafica =
        elemento("graficaTelemetria").closest(".panel");

    panelGrafica.querySelector("p").textContent =
        modoSimulacion
            ? "Datos simulados — No son lecturas reales"
            : "Mediciones reales — Arduino Mega + INA219";

    const estadoConexion = document.createElement("p");
    estadoConexion.id = "estadoConexion";
    estadoConexion.setAttribute("aria-live", "polite");
    estadoConexion.textContent = "Iniciando...";
    panelGrafica.appendChild(estadoConexion);

    const estadoAlmacenamiento = document.createElement("p");
    estadoAlmacenamiento.id = "estadoAlmacenamiento";
    estadoAlmacenamiento.className = "nota";
    estadoAlmacenamiento.textContent = modoSimulacion
        ? "Energía simulada en este navegador."
        : "Esperando estado de SQLite...";
    panelGrafica.appendChild(estadoAlmacenamiento);

    if (!grafica) {
        const aviso = document.createElement("p");
        aviso.textContent =
            "No se pudo cargar Chart.js. " +
            "Las tarjetas seguirán actualizándose.";
        aviso.style.color = "#fbbf24";
        panelGrafica.appendChild(aviso);
    }

    const panelControles = document.querySelector(
        ".panel-controles"
    ).closest(".panel");

    panelControles.querySelector("p").textContent =
        modoSimulacion
            ? "Interruptores virtuales — Solo simulación"
            : "Indicadores de consumo total — " +
              "Control mediante interruptores físicos";

    const cajas = [led1, led2].map(
        control => control.closest(".control-box")
    );

    if (!modoSimulacion) {
        cajas[0].querySelector("h3").textContent =
            "CONSUMO DETECTADO";

        cajas[1].querySelector("h3").textContent =
            "NIVEL NORMAL";

        cajas.forEach(caja => {
            caja.querySelector(".switch").hidden = true;
            caja.querySelector(".nota").textContent =
                "Solo lectura";
        });

        led1.disabled = true;
        led2.disabled = true;

        simularFalla.disabled = true;
        simularFalla.checked = false;
        simularFalla.closest("label").hidden = true;
    }

    botonReset.textContent = "RECONOCER";
    botonReset.title =
        "Reconoce la alerta en este navegador. " +
        "No cambia Arduino ni reinicia la energía.";

    botonEmail.textContent = modoSimulacion
        ? "Probar indicador"
        : "Envío automático";

    botonEmail.disabled = !modoSimulacion;

    estadoEmail.textContent = modoSimulacion
        ? "Sin enviar"
        : "Consultando estado del email...";

    botonEmail.closest(".control-box")
        .querySelector(".nota").textContent =
        modoSimulacion
            ? "Prueba visual — No envía correos"
            : "Alertas automáticas activas";

    // email_estado.js actualiza después el panel de email.
    const panelComponentes =
        [...document.querySelectorAll("section.panel")]
            .find(panel =>
                panel.querySelector("h2")?.textContent.trim() ===
                "Componentes del sistema"
            );

    if (panelComponentes) {
        const parrafos = panelComponentes.querySelectorAll("p");

        parrafos[parrafos.length - 1].textContent =
            modoSimulacion
                ? "Estado: Modo simulación"
                : "Estado: Adquisición real por USB serial";

        const descripcion = document.createElement("p");
        descripcion.textContent =
            "Cuatro módulos LED de 12 V en dos grupos. " +
            "Un INA219 mide el consumo total.";

        panelComponentes.appendChild(descripcion);
    }

    elemento("valorEnergia").title = modoSimulacion
        ? "Energía ficticia calculada en este navegador."
        : "Energía calculada en Python y guardada en SQLite. " +
          "No incluye intervalos sin medición superiores a 2 segundos.";

    mostrarSinMediciones();
}

function mostrarSinMediciones() {
    elemento("valorVoltaje").textContent = "-- V";
    elemento("valorCorriente").textContent = "-- A";
    elemento("valorPotencia").textContent = "-- W";
    elemento("valorEnergia").textContent = "-- Wh";

    cambiarIndicador("indicadorLed1", "apagado");
    cambiarIndicador("indicadorLed2", "apagado");

    elemento("estadoLed1").textContent = "SIN DATOS";
    elemento("estadoLed2").textContent = "SIN DATOS";
}

function mostrarAlerta(clave, mensaje) {
    if (clave !== claveAlerta) {
        alertaReconocida = false;
        claveAlerta = clave;
    }

    if (clave === null) {
        indicadorAlerta.className = "led-indicador apagado";
        estadoAlerta.style.color = "#34d399";
        estadoAlerta.textContent = mensaje;
        botonReset.disabled = true;
        return;
    }

    indicadorAlerta.className = "led-indicador alarma";
    estadoAlerta.style.color = "#f87171";

    estadoAlerta.textContent = mensaje +
        (alertaReconocida
            ? " (Reconocida en este navegador)"
            : "");

    botonReset.disabled = false;
}

function evaluarAlerta(medicion) {
    const causas = [];

    if (medicion.state === "UNA_CARGA") {
        causas.push("Consumo reducido");
    }

    if (medicion.state === "SIN_CARGA") {
        causas.push("Sin consumo de las cargas");
    }

    // Límites provisionales conservados del dashboard.
    // Las alertas automáticas de email actuales son por consumo.
    if (medicion.voltage < 11.5) {
        causas.push("Voltaje bajo");
    } else if (medicion.voltage > 12.5) {
        causas.push("Voltaje alto");
    }

    mostrarAlerta(
        causas.length ? causas.join("|") : null,
        causas.length ? causas.join(" — ") : "Sistema normal"
    );
}

function mostrarIndicadores(medicion) {
    if (modoSimulacion) {
        cambiarIndicador(
            "indicadorLed1",
            led1.checked ? "encendido" : "apagado"
        );

        cambiarIndicador(
            "indicadorLed2",
            led2.checked ? "encendido" : "apagado"
        );

        elemento("estadoLed1").textContent =
            led1.checked ? "ENCENDIDA" : "APAGADA";

        elemento("estadoLed2").textContent =
            led2.checked ? "ENCENDIDA" : "APAGADA";

        return;
    }

    const hayConsumo = medicion.state !== "SIN_CARGA";
    const normal = medicion.state === "NORMAL";

    cambiarIndicador(
        "indicadorLed1",
        hayConsumo ? "encendido" : "apagado"
    );

    cambiarIndicador(
        "indicadorLed2",
        normal ? "encendido" : "apagado"
    );

    elemento("estadoLed1").textContent =
        hayConsumo ? "CONSUMO PRESENTE" : "SIN CARGA";

    elemento("estadoLed2").textContent = normal
        ? "NORMAL — DOS GRUPOS ESTIMADOS"
        : medicion.state === "UNA_CARGA"
            ? "CONSUMO REDUCIDO"
            : "SIN CONSUMO";
}

function actualizarGrafica(medicion) {
    if (!grafica || medicion.received_at === ultimaMuestra) {
        return;
    }

    ultimaMuestra = medicion.received_at;

    grafica.data.labels.push(
        formatoHora.format(new Date(medicion.received_at))
    );

    const valores = [
        medicion.voltage,
        medicion.current_a,
        medicion.power_w,
        medicion.energy_wh
    ];

    valores.forEach((valor, indice) => {
        grafica.data.datasets[indice].data.push(valor);
    });

    if (grafica.data.labels.length > maxMuestras) {
        grafica.data.labels.shift();

        grafica.data.datasets.forEach(dataset => {
            dataset.data.shift();
        });
    }

    grafica.update("none");
}

function mostrarMedicion(medicion) {
    ultimaMedicion = medicion;

    elemento("valorVoltaje").textContent =
        medicion.voltage.toFixed(2) + " V";

    elemento("valorCorriente").textContent =
        medicion.current_a.toFixed(3) + " A";

    elemento("valorPotencia").textContent =
        medicion.power_w.toFixed(2) + " W";

    elemento("valorEnergia").textContent =
        medicion.energy_wh.toFixed(5) + " Wh";

    mostrarIndicadores(medicion);
    evaluarAlerta(medicion);
    actualizarGrafica(medicion);
}

function marcarSinDatos(mensaje) {
    ultimaMedicion = null;
    mostrarSinMediciones();

    elemento("estadoConexion").textContent = mensaje;
    elemento("estadoConexion").style.color = "#f87171";

    mostrarAlerta("SIN_DATOS", mensaje);

    // Cortar la línea para no dibujar continuidad
    // sobre un periodo en el que no hubo datos válidos.
    if (grafica && ultimaMuestra !== null) {
        grafica.data.labels.push(
            formatoHora.format(new Date())
        );

        grafica.data.datasets.forEach(dataset => {
            dataset.data.push(null);
        });

        if (grafica.data.labels.length > maxMuestras) {
            grafica.data.labels.shift();

            grafica.data.datasets.forEach(dataset => {
                dataset.data.shift();
            });
        }

        grafica.update("none");
        ultimaMuestra = null;
    }
}

function validarMedicion(medicion) {
    return medicion &&
        [
            "voltage",
            "current_a",
            "power_w",
            "energy_wh"
        ].every(
            campo =>
                typeof medicion[campo] === "number" &&
                Number.isFinite(medicion[campo])
        ) &&
        medicion.energy_wh >= 0 &&
        ["NORMAL", "UNA_CARGA", "SIN_CARGA"].includes(
            medicion.state
        ) &&
        typeof medicion.received_at === "string" &&
        Number.isFinite(Date.parse(medicion.received_at));
}

async function consultarMediciones() {
    if (consultaActiva) {
        return;
    }

    consultaActiva = true;

    const controlador = new AbortController();
    const limite = setTimeout(
        () => controlador.abort(),
        3000
    );

    try {
        const respuesta = await fetch("/api/mediciones", {
            cache: "no-store",
            signal: controlador.signal
        });

        if (!respuesta.ok) {
            throw new Error("HTTP " + respuesta.status);
        }

        const datos = await respuesta.json();

        if (datos.mode !== "REAL") {
            throw new Error("La API no está en modo REAL");
        }

        const almacenamiento = elemento("estadoAlmacenamiento");

        if (datos.storage_ok === true) {
            almacenamiento.textContent =
                "SQLite: sin error actual — Lecturas guardadas " +
                "en esta ejecución: " +
                datos.stored_measurements_this_run;

            almacenamiento.style.color = "#94a3b8";
        } else {
            almacenamiento.textContent =
                "Aviso: no se está confirmando el guardado. " +
                "La adquisición puede continuar en memoria.";

            almacenamiento.style.color = "#f87171";
        }

        if (!datos.serial_connected) {
            marcarSinDatos(
                "Arduino desconectado — Intentando reconectar"
            );
            return;
        }

        if (!datos.data_valid) {
            marcarSinDatos(
                "Puerto abierto — Esperando mediciones válidas"
            );
            return;
        }

        if (!validarMedicion(datos.measurement)) {
            throw new Error(
                "Medición incompleta o inválida. " +
                "Comprueba que serial_reader.py esté actualizado."
            );
        }

        elemento("estadoConexion").textContent =
            "Arduino conectado — Datos reales — " +
            datos.measurement.state;

        elemento("estadoConexion").style.color = "#34d399";

        mostrarMedicion(datos.measurement);

    } catch (error) {
        console.error("Error consultando mediciones:", error);

        elemento("estadoAlmacenamiento").textContent =
            "Sin confirmación actual del almacenamiento.";

        elemento("estadoAlmacenamiento").style.color = "#fbbf24";

        marcarSinDatos(
            "No hay mediciones válidas disponibles — Reintentando"
        );

    } finally {
        clearTimeout(limite);
        consultaActiva = false;
    }
}

function actualizarSimulacion() {
    const ahora = performance.now();

    const segundos = ultimoTiempoSimulado === null
        ? 0
        : Math.min(
            (ahora - ultimoTiempoSimulado) / 1000,
            2
        );

    ultimoTiempoSimulado = ahora;

    const voltaje = simularFalla.checked
        ? 10.8
        : 12 + Math.random() * 0.2;

    const grupos =
        Number(led1.checked) + Number(led2.checked);

    const corriente = grupos * 0.24;
    const potencia = voltaje * corriente;

    energiaSimulada += potencia * segundos / 3600;

    const medicion = {
        voltage: voltaje,
        current_a: corriente,
        power_w: potencia,
        energy_wh: energiaSimulada,
        state: grupos === 2
            ? "NORMAL"
            : grupos === 1
                ? "UNA_CARGA"
                : "SIN_CARGA",
        received_at: new Date().toISOString()
    };

    elemento("estadoConexion").textContent =
        "SIMULACIÓN — Datos ficticios de este navegador";

    elemento("estadoConexion").style.color = "#fbbf24";

    mostrarMedicion(medicion);
}

botonReset.addEventListener("click", () => {
    if (claveAlerta === null) {
        return;
    }

    alertaReconocida = true;

    if (ultimaMedicion) {
        evaluarAlerta(ultimaMedicion);
    } else {
        mostrarAlerta(
            claveAlerta,
            elemento("estadoConexion").textContent
        );
    }
});

botonEmail.addEventListener("click", () => {
    if (!modoSimulacion) {
        return;
    }

    estadoEmail.textContent =
        "Prueba visual completada — No se envió correo";

    estadoEmail.style.color = "#38bdf8";
    indicadorEmail.className = "led-indicador encendido";
});

configurarPantalla();

if (modoSimulacion) {
    actualizarSimulacion();
    setInterval(actualizarSimulacion, intervaloMs);
} else {
    consultarMediciones();
    setInterval(consultarMediciones, intervaloMs);
}