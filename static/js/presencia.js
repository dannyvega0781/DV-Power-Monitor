/*
 * Renueva la presencia de esta sesión.
 * Al cerrar todas las páginas, caduca en hasta 90 segundos.
 */
(() => {
    const csrf = document.currentScript.dataset.csrf;

    let running = true;
    let busy = false;

    async function heartbeat() {
        if (!running || busy) {
            return;
        }

        busy = true;

        try {
            const response = await fetch(
                "/usuario/presencia",
                {
                    method: "POST",
                    credentials: "same-origin",
                    cache: "no-store",

                    headers: {
                        "Content-Type":
                            "application/x-www-form-urlencoded"
                    },

                    body: new URLSearchParams({csrf})
                }
            );

            if (
                response.status === 403
                || response.status === 400
            ) {
                running = false;
            }

        } catch (_) {
            // Sin conexión, el servidor deja vencer la presencia.

        } finally {
            busy = false;
        }
    }

    heartbeat();

    setInterval(heartbeat, 20000);

    window.addEventListener(
        "pageshow",
        heartbeat
    );

    document.addEventListener(
        "visibilitychange",
        () => {
            if (!document.hidden) {
                heartbeat();
            }
        }
    );
})();