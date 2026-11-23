"use strict";

(() => {
    const filas = document.getElementById("historialFilas");

    if (!filas) {
        return;
    }

    const panel = filas.closest("section");

    if (!panel) {
        return;
    }

    const simulado = new URLSearchParams(
        location.search
    ).get("modo") === "simulacion";

    const titulo = document.createElement("h2");
    titulo.textContent = "Historial";

    const texto = document.createElement("p");

    texto.textContent = simulado
        ? "La simulación no guarda eventos en el historial real."
        : "Consulta los eventos guardados por fecha. " +
          "El administrador puede enviar un periodo " +
          "a los destinatarios que seleccione.";

    const enlace = document.createElement("a");

    enlace.href = "/historial";
    enlace.target = "_blank";
    enlace.rel = "noopener";
    enlace.textContent = "Abrir historial";

    enlace.style.cssText =
        "display:inline-block;" +
        "padding:10px 16px;" +
        "background:#334155;" +
        "color:#7dd3fc;" +
        "border:1px solid #64748b;" +
        "border-radius:7px;" +
        "text-decoration:none";

    const info = document.createElement("details");
    const resumen = document.createElement("summary");

    resumen.textContent = "Canales de notificación";

    resumen.style.cssText =
        "cursor:pointer;" +
        "color:#7dd3fc;" +
        "margin-top:16px";

    const detalle = document.createElement("p");

    detalle.textContent =
        "Email: implementado en modo real. " +
        "SMS y WhatsApp: ilustrativos, no implementados.";

    info.append(resumen, detalle);
    panel.replaceChildren(titulo, texto);

    if (!simulado) {
        panel.appendChild(enlace);
    }

    panel.appendChild(info);
})();