import os
import smtplib
import ssl

from email.message import EmailMessage
from email.utils import formataddr

from recipients import (
    inicializar_destinatarios,
    listar_destinatarios,
    validar_email,
)


def enviar_email(
    asunto,
    contenido,
    imagen_png=None,
    destinatarios=None,
):
    usuario = os.environ.get(
        "DV_EMAIL_USER", ""
    ).strip()

    password = os.environ.get(
        "DV_EMAIL_PASSWORD", ""
    ).replace(" ", "").strip()

    if not usuario:
        raise ValueError(
            "Falta configurar DV_EMAIL_USER."
        )

    if not password:
        raise ValueError(
            "Falta configurar DV_EMAIL_PASSWORD."
        )

    validar_email(usuario)

    automatico = destinatarios is None

    # Sin lista puntual: usar destinatarios automáticos.
    if destinatarios is None:
        inicializar_destinatarios()

        destinatarios = [
            registro["email"]
            for registro in listar_destinatarios()
        ]

    if automatico:
        from personal_alerts import automatic_recipients

        destinatarios = automatic_recipients(
            destinatarios
        )

    if not isinstance(destinatarios, (list, tuple)):
        raise ValueError(
            "La lista de destinatarios no es válida."
        )

    unicos = {}

    for direccion in destinatarios:
        email = validar_email(direccion)
        unicos.setdefault(email.lower(), email)

    destinatarios = list(unicos.values())

    if not destinatarios:
        raise ValueError(
            "Selecciona al menos un destinatario."
        )

    if not automatico and len(destinatarios) > 10:
        raise ValueError(
            "Máximo 10 destinatarios por envío."
        )

    mensaje = EmailMessage()

    mensaje["From"] = formataddr(
        ("DV Power Monitor", usuario)
    )

    mensaje["To"] = "undisclosed-recipients:;"
    mensaje["Subject"] = asunto
    mensaje.set_content(contenido)

    if imagen_png is not None:
        mensaje.add_attachment(
            imagen_png,
            maintype="image",
            subtype="png",
            filename="DV_Power_Monitor_Alerta.png",
        )

    contexto = ssl.create_default_context()

    with smtplib.SMTP_SSL(
        "smtp.gmail.com",
        465,
        context=contexto,
        timeout=20,
    ) as servidor:
        servidor.login(usuario, password)

        rechazados = servidor.send_message(
            mensaje,
            from_addr=usuario,
            to_addrs=destinatarios,
        )

    return {
        "aceptados": [
            direccion
            for direccion in destinatarios
            if direccion not in rechazados
        ],
        "rechazados": list(rechazados),
    }


def probar_email():
    print("[EMAIL] Iniciando envío de prueba...")

    try:
        resultado = enviar_email(
            "DV Power Monitor — Prueba de correo",
            (
                "Esta es una prueba de envío de DV Power Monitor.\n\n"
                "No corresponde a una falla del equipo.\n"
                "No se incluyen mediciones en esta prueba.\n\n"
                "Remitente del sistema: DV Power Monitor.\n"
            ),
        )

    except ValueError as error:
        print(f"[EMAIL] Configuración: {error}")
        return False

    except smtplib.SMTPAuthenticationError:
        print(
            "[EMAIL] Gmail rechazó la autenticación. "
            "Revisa la cuenta y la contraseña de aplicación."
        )
        return False

    except (smtplib.SMTPException, OSError):
        print(
            "[EMAIL] No se pudo completar el envío. "
            "Revisa Internet y la configuración."
        )
        return False

    print(
        "[EMAIL] Gmail aceptó el mensaje para "
        f"{len(resultado['aceptados'])} destinatario(s)."
    )

    if resultado["rechazados"]:
        print(
            "[EMAIL] Destinatarios rechazados: "
            + ", ".join(resultado["rechazados"])
        )

    print(
        "[EMAIL] Comprueba la bandeja de entrada y Spam."
    )

    return not resultado["rechazados"]