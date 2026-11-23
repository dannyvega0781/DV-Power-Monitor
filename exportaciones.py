"""Descargas de historial y mediciones para el administrador."""

import csv
import io

from contextlib import closing
from datetime import datetime
from html import escape as escape_html
from xml.sax.saxutils import escape

from flask import (
    abort,
    request,
    send_file,
    session,
    url_for,
)

from history_page import (
    NOMBRES,
    ZONA_PR,
    periodo,
)


MAX_CSV = 100000
MAX_PDF = 1000


def fecha_pr(value):
    return datetime.fromisoformat(
        value
    ).astimezone(ZONA_PR).strftime(
        "%d/%m/%Y %I:%M:%S %p"
    )


def texto_csv(value):
    text = str(value)

    # Evita que Excel interprete detalles como fórmulas.
    if (
        text.lstrip().startswith(
            ("=", "+", "-", "@")
        )
        or text.startswith(
            ("\t", "\r", "\n")
        )
    ):
        return "'" + text

    return text


def consultar(
    store,
    desde,
    hasta,
    tipo,
    limite,
):
    inicio, final = periodo(
        desde,
        hasta,
    )

    condicion = (
        "julianday(received_at) >= julianday(?) "
        "AND julianday(received_at) < julianday(?)"
    )

    if tipo == "eventos":
        consulta = (
            "SELECT id, received_at, kind, detail "
            "FROM events"
        )

    elif tipo == "mediciones":
        consulta = (
            "SELECT id, received_at, voltage, current_ma, "
            "power_mw, state, energy_wh "
            "FROM measurements"
        )

    else:
        raise ValueError(
            "Tipo de exportación inválido."
        )

    with closing(store._connect()) as db:
        # Las consultas usan una misma vista de SQLite.
        db.execute("BEGIN")

        filas = db.execute(
            consulta
            + " WHERE "
            + condicion
            + " ORDER BY id ASC LIMIT ?",
            (
                inicio,
                final,
                limite + 1,
            ),
        ).fetchall()

        resumen = db.execute(
            (
                "SELECT COUNT(*), MIN(voltage), MAX(voltage), "
                "AVG(current_ma), AVG(power_mw) "
                "FROM measurements WHERE "
            )
            + condicion,
            (
                inicio,
                final,
            ),
        ).fetchone()

    if len(filas) > limite:
        raise ValueError(
            f"El periodo supera el límite de {limite:,} filas. "
            "Selecciona un periodo más corto. "
            "No se descargaron datos parciales."
        )

    return filas, resumen


def crear_csv(filas, tipo):
    texto = io.StringIO(
        newline=""
    )

    writer = csv.writer(texto)

    if tipo == "eventos":
        writer.writerow([
            "ID",
            "Fecha y hora (PR UTC-4)",
            "Código",
            "Evento",
            "Detalle",
        ])

        for ident, fecha, clase, detalle in filas:
            writer.writerow([
                ident,
                fecha_pr(fecha),
                texto_csv(clase),
                texto_csv(
                    NOMBRES.get(clase, clase)
                ),
                texto_csv(detalle),
            ])

    else:
        writer.writerow([
            "ID",
            "Fecha y hora (PR UTC-4)",
            "Voltaje (V)",
            "Corriente (mA)",
            "Potencia (W)",
            "Estado",
            "Energía acumulada (Wh)",
        ])

        for (
            ident,
            fecha,
            voltaje,
            corriente,
            potencia,
            estado,
            energia,
        ) in filas:
            writer.writerow([
                ident,
                fecha_pr(fecha),
                voltaje,
                corriente,
                potencia / 1000,
                texto_csv(estado),
                energia,
            ])

    # UTF-8 con BOM para reconocer las tildes en Excel.
    return io.BytesIO(
        texto.getvalue().encode(
            "utf-8-sig"
        )
    )


def crear_pdf(
    filas,
    resumen,
    desde,
    hasta,
):
    import reportlab

    from pathlib import Path

    from reportlab.pdfbase import pdfmetrics
    from reportlab.pdfbase.ttfonts import TTFont

    from reportlab.lib import colors
    from reportlab.lib.enums import TA_CENTER
    from reportlab.lib.pagesizes import letter

    from reportlab.lib.styles import (
        ParagraphStyle,
        getSampleStyleSheet,
    )

    from reportlab.platypus import (
        LongTable,
        Paragraph,
        SimpleDocTemplate,
        Spacer,
        Table,
        TableStyle,
    )

    salida = io.BytesIO()

    doc = SimpleDocTemplate(
        salida,
        pagesize=letter,
        rightMargin=36,
        leftMargin=36,
        topMargin=42,
        bottomMargin=42,
        title="Historial - DV Power Monitor",
        author="DV Power Monitor",
    )

    fuentes = (
        Path(reportlab.__file__).parent
        / "fonts"
    )

    pdfmetrics.registerFont(
        TTFont(
            "DVRegular",
            str(fuentes / "Vera.ttf"),
        )
    )

    pdfmetrics.registerFont(
        TTFont(
            "DVBold",
            str(fuentes / "VeraBd.ttf"),
        )
    )

    estilos = getSampleStyleSheet()

    estilos["BodyText"].fontName = "DVRegular"
    estilos["Heading2"].fontName = "DVBold"

    titulo = ParagraphStyle(
        "TituloDV",
        parent=estilos["Title"],
        fontSize=20,
        leading=24,
        fontName="DVBold",
        textColor=colors.HexColor(
            "#0369a1"
        ),
        alignment=TA_CENTER,
    )

    celda = ParagraphStyle(
        "CeldaDV",
        parent=estilos["BodyText"],
        fontSize=8,
        leading=11,
        spaceAfter=0,
    )

    def parrafo(value):
        texto = escape(
            str(value)
        ).replace(
            "\n",
            "<br/>",
        )

        return Paragraph(
            texto,
            celda,
        )

    elementos = [
        Paragraph(
            "DV Power Monitor",
            titulo,
        ),
        Paragraph(
            "Informe de eventos del sistema",
            estilos["Heading2"],
        ),
        Paragraph(
            (
                f"Periodo: {desde} al {hasta}, inclusive. "
                "Hora de Puerto Rico (UTC-4)."
            ),
            estilos["BodyText"],
        ),
        Paragraph(
            "Generado: "
            + datetime.now(ZONA_PR).strftime(
                "%d/%m/%Y %I:%M:%S %p"
            ),
            estilos["BodyText"],
        ),
        Spacer(1, 14),
    ]

    (
        cantidad,
        minimo,
        maximo,
        corriente,
        potencia,
    ) = resumen

    valores = [
        [
            "Eventos exportados",
            str(len(filas)),
        ],
        [
            "Mediciones del periodo",
            str(cantidad),
        ],
        [
            "Voltaje mínimo / máximo",
            (
                f"{minimo:.3f} / {maximo:.3f} V"
                if cantidad
                else "Sin mediciones"
            ),
        ],
        [
            "Corriente promedio por muestra",
            (
                f"{corriente:.2f} mA"
                if cantidad
                else "Sin mediciones"
            ),
        ],
        [
            "Potencia promedio por muestra",
            (
                f"{potencia / 1000:.3f} W"
                if cantidad
                else "Sin mediciones"
            ),
        ],
    ]

    tabla_resumen = Table(
        [
            [
                parrafo(a),
                parrafo(b),
            ]
            for a, b in valores
        ],
        colWidths=[
            270,
            270,
        ],
    )

    tabla_resumen.setStyle(
        TableStyle([
            (
                "BACKGROUND",
                (0, 0),
                (0, -1),
                colors.HexColor("#e0f2fe"),
            ),
            (
                "GRID",
                (0, 0),
                (-1, -1),
                0.4,
                colors.HexColor("#cbd5e1"),
            ),
            (
                "VALIGN",
                (0, 0),
                (-1, -1),
                "TOP",
            ),
            (
                "TOPPADDING",
                (0, 0),
                (-1, -1),
                7,
            ),
            (
                "BOTTOMPADDING",
                (0, 0),
                (-1, -1),
                7,
            ),
        ])
    )

    elementos.extend([
        tabla_resumen,
        Spacer(1, 12),
        Paragraph(
            (
                "Los eventos documentan condiciones observadas; "
                "no confirman la causa física de una falla "
                "ni downtime de producción. Los promedios son "
                "por muestra y no estiman valores durante "
                "periodos sin datos."
            ),
            estilos["BodyText"],
        ),
        Spacer(1, 12),
    ])

    if filas:
        datos = [[
            parrafo("Fecha y hora (PR)"),
            parrafo("Evento"),
            parrafo("Detalle"),
        ]]

        for ident, fecha, clase, detalle in filas:
            datos.append([
                parrafo(
                    fecha_pr(fecha)
                ),
                parrafo(
                    NOMBRES.get(clase, clase)
                ),
                parrafo(
                    f"#{ident} - {detalle}"
                ),
            ])

        tabla = LongTable(
            datos,
            colWidths=[
                105,
                120,
                315,
            ],
            repeatRows=1,
            splitByRow=1,
            splitInRow=1,
        )

        tabla.setStyle(
            TableStyle([
                (
                    "BACKGROUND",
                    (0, 0),
                    (-1, 0),
                    colors.HexColor("#e0f2fe"),
                ),
                (
                    "ROWBACKGROUNDS",
                    (0, 1),
                    (-1, -1),
                    [
                        colors.white,
                        colors.HexColor("#f8fafc"),
                    ],
                ),
                (
                    "GRID",
                    (0, 0),
                    (-1, -1),
                    0.3,
                    colors.HexColor("#cbd5e1"),
                ),
                (
                    "VALIGN",
                    (0, 0),
                    (-1, -1),
                    "TOP",
                ),
                (
                    "TOPPADDING",
                    (0, 0),
                    (-1, -1),
                    6,
                ),
                (
                    "BOTTOMPADDING",
                    (0, 0),
                    (-1, -1),
                    6,
                ),
            ])
        )

        elementos.append(tabla)

    else:
        elementos.append(
            Paragraph(
                "No hay eventos en el periodo seleccionado.",
                estilos["BodyText"],
            )
        )

    def pie(canvas, documento):
        canvas.saveState()

        canvas.setFont(
            "DVRegular",
            8,
        )

        canvas.setFillColor(
            colors.HexColor("#475569")
        )

        canvas.drawString(
            36,
            24,
            "DV Power Monitor | Historial",
        )

        canvas.drawRightString(
            576,
            24,
            f"Página {documento.page}",
        )

        canvas.restoreState()

    doc.build(
        elementos,
        onFirstPage=pie,
        onLaterPages=pie,
    )

    salida.seek(0)

    return salida


def configurar_exportaciones(app, store):
    @app.get("/historial/exportar/<formato>")
    def exportar_historial(formato):
        if session.get("admin") is not True:
            abort(403)

        if formato not in {
            "csv",
            "pdf",
        }:
            abort(404)

        hoy = datetime.now(
            ZONA_PR
        ).date().isoformat()

        desde = request.args.get(
            "desde",
            hoy,
        )

        hasta = request.args.get(
            "hasta",
            hoy,
        )

        tipo = request.args.get(
            "tipo",
            "eventos",
        )

        if (
            tipo not in {
                "eventos",
                "mediciones",
            }
            or (
                formato == "pdf"
                and tipo != "eventos"
            )
        ):
            abort(
                400,
                description=(
                    "Formato o tipo de exportación inválido."
                ),
            )

        try:
            filas, resumen = consultar(
                store,
                desde,
                hasta,
                tipo,
                (
                    MAX_PDF
                    if formato == "pdf"
                    else MAX_CSV
                ),
            )

        except ValueError as error:
            abort(
                400,
                description=str(error),
            )

        except Exception:
            app.logger.exception(
                "No se pudo consultar la exportación"
            )

            abort(
                503,
                description=(
                    "No se pudo consultar SQLite. "
                    "Inténtalo nuevamente."
                ),
            )

        if formato == "csv":
            archivo = crear_csv(
                filas,
                tipo,
            )

            mime = "text/csv"

        else:
            try:
                archivo = crear_pdf(
                    filas,
                    resumen,
                    desde,
                    hasta,
                )

            except ImportError:
                abort(
                    503,
                    description=(
                        "Instala reportlab en el entorno "
                        "Python del proyecto: "
                        "python -m pip install reportlab"
                    ),
                )

            except Exception:
                app.logger.exception(
                    "No se pudo crear el PDF"
                )

                abort(
                    503,
                    description=(
                        "No se pudo generar el PDF. "
                        "Revisa la consola del servidor."
                    ),
                )

            mime = "application/pdf"

        respuesta = send_file(
            archivo,
            mimetype=mime,
            as_attachment=True,
            download_name=(
                f"DV_{tipo}_{desde}_{hasta}.{formato}"
            ),
            max_age=0,
        )

        respuesta.headers[
            "Cache-Control"
        ] = "no-store"

        return respuesta

    @app.after_request
    def botones_exportacion(response):
        if (
            request.path != "/historial"
            or response.status_code != 200
            or response.mimetype != "text/html"
            or session.get("admin") is not True
        ):
            return response

        hoy = datetime.now(
            ZONA_PR
        ).date().isoformat()

        desde = request.args.get(
            "desde",
            hoy,
        )

        hasta = request.args.get(
            "hasta",
            hoy,
        )

        try:
            periodo(
                desde,
                hasta,
            )

        except ValueError:
            return response

        botones = []

        opciones = [
            (
                "csv",
                "eventos",
                "Descargar eventos CSV",
            ),
            (
                "csv",
                "mediciones",
                "Descargar mediciones CSV",
            ),
            (
                "pdf",
                "eventos",
                "Descargar informe PDF",
            ),
        ]

        for formato, tipo, etiqueta in opciones:
            enlace = url_for(
                "exportar_historial",
                formato=formato,
                tipo=tipo,
                desde=desde,
                hasta=hasta,
            )

            botones.append(
                '<a class="boton" href="'
                + escape_html(enlace)
                + '">'
                + etiqueta
                + "</a>"
            )

        bloque = (
            '<section class="panel">'
            "<h2>Exportar periodo consultado</h2>"
            "<p>"
            "Se exportan los registros del periodo completo, "
            "no solo esta página. "
            "CSV: hasta 100 000 filas. "
            "PDF: hasta 1 000 eventos. "
            "La energía del CSV es acumulada."
            "</p>"
            + " ".join(botones)
            + "</section>"
        )

        response.set_data(
            response.get_data(
                as_text=True
            ).replace(
                "</main>",
                bloque + "</main>",
                1,
            )
        )

        return response