
/* ====================================
   DV POWER MONITOR
   RELOJ DIGITAL - PUERTO RICO
   ==================================== */

function actualizarReloj() {

    const ahora = new Date();

    // Hora local de Puerto Rico
    const hora = new Intl.DateTimeFormat("es-PR", {
        timeZone: "America/Puerto_Rico",
        hour: "2-digit",
        minute: "2-digit",
        second: "2-digit",
        hour12: true
    }).format(ahora);

    // Fecha local de Puerto Rico
    const fecha = new Intl.DateTimeFormat("es-PR", {
        timeZone: "America/Puerto_Rico",
        weekday: "long",
        day: "numeric",
        month: "long",
        year: "numeric"
    }).format(ahora);

    // Mostrar hora
    document.getElementById("relojDigital")
        .textContent = hora;

    // Mostrar fecha
    document.getElementById("fechaActual")
        .textContent = fecha;
}

// Mostrar el reloj inmediatamente
actualizarReloj();

// Actualizar la hora cada segundo
setInterval(actualizarReloj, 1000);
