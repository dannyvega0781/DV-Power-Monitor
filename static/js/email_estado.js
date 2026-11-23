"use strict";

(() => {
    const parametros = new URLSearchParams(window.location.search);

    // La simulación conserva su prueba visual.
    if (parametros.get("modo") === "simulacion") {
        return;
    }

    const indicador = document.getElementById("indicadorEmail");
    const texto = document.getElementById("estadoEmail");
    const boton = document.getElementById("botonEmail");

    if (!indicador || !texto || !boton) {
        return;
    }

    const caja = boton.closest(".control-box");
    const nota = caja.querySelector(".nota");

    boton.disabled = true;
    boton.textContent = "Envío automático";

    if (nota) {
        nota.textContent =
            "Alertas automáticas activas — Estado del último envío";
    }

    // Estilos exclusivos del indicador de email.
    const estilos = document.createElement("style");

    estilos.textContent = `
        #indicadorEmail.email-enviando {
            background: #38bdf8;
            border-color: #bae6fd;
            box-shadow: 0 0 15px #38bdf8;
            animation: parpadeo 0.5s infinite;
        }

        #indicadorEmail.email-enviado {
            background: #38bdf8;
            border-color: #bae6fd;
            box-shadow: 0 0 15px #38bdf8;
            animation: none;
        }

        #indicadorEmail.email-error {
            background: #ef4444;
            border-color: #fca5a5;
            box-shadow: 0 0 15px #ef4444;
            animation: none;
        }
    `;

    document.head.appendChild(estilos);

    const formato = new Intl.DateTimeFormat("es-PR", {
        timeZone: "America/Puerto_Rico",
        hour: "2-digit",
        minute: "2-digit",
        second: "2-digit",
        hour12: true
    });

    function mostrarEstado(datos) {
        let clase = "apagado";
        let color = "#94a3b8";

        if (datos.status === "sending") {
            clase = "email-enviando";
            color = "#38bdf8";
        } else if (datos.status === "sent") {
            clase = "email-enviado";
            color = "#38bdf8";
        } else if (
            datos.status === "error" ||
            datos.status === "partial"
        ) {
            clase = "email-error";
            color = "#f87171";
        }

        indicador.className = "led-indicador " + clase;

        let mensaje = datos.message || "Esperando una alerta";

        if (datos.updated_at) {
            const fecha = new Date(datos.updated_at);

            if (Number.isFinite(fecha.getTime())) {
                mensaje += " — " + formato.format(fecha);
            }
        }

        texto.textContent = mensaje;
        texto.style.color = color;

        if (nota) {
            nota.textContent = datos.led_warning
                ? "Aviso: no se confirmó el envío del comando al LED físico."
                : "Alertas automáticas activas — Estado del último envío";
        }
    }

    let consultando = false;

    async function consultar() {
        if (consultando) {
            return;
        }

        consultando = true;

        const controlador = new AbortController();
        const temporizador = setTimeout(
            () => controlador.abort(),
            3000
        );

        try {
            const respuesta = await fetch("/api/email/estado", {
                cache: "no-store",
                signal: controlador.signal
            });

            if (!respuesta.ok) {
                throw new Error("HTTP " + respuesta.status);
            }

            mostrarEstado(await respuesta.json());

        } catch (error) {
            indicador.className = "led-indicador apagado";
            texto.textContent =
                "No se pudo consultar el estado del email";
            texto.style.color = "#fbbf24";

        } finally {
            clearTimeout(temporizador);
            consultando = false;
        }
    }

    consultar();
    setInterval(consultar, 500);
})();