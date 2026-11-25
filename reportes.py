from datetime import date

from flask import Blueprint, flash, render_template, request, url_for

from auth import login_required
from servicios import (
    ESTADOS_CHEQUE,
    ESTADOS_VENCIMIENTO,
    RANGOS_FECHA,
    auditoria_cheques,
    cheques_reporte,
    conciliacion_mensual,
    facturas_por_vencer,
    numero_csv,
    obtener_proveedores,
    pagos_por_mes,
    parsear_fecha,
    presets_corte,
    responder_csv,
    resolver_rango,
    resumen_antiguedad,
    top_proveedores,
)

reportes_bp = Blueprint("reportes", __name__, url_prefix="/reportes")


def url_csv(endpoint):
    return url_for(endpoint, **request.args.to_dict())


def comunes(csv_endpoint, titulo, descripcion="", **extra):
    datos = {
        "proveedores": obtener_proveedores(),
        "rangos": RANGOS_FECHA,
        "csv_url": url_csv(csv_endpoint),
        "titulo": titulo,
        "descripcion": descripcion,
    }
    datos.update(extra)
    return datos


def fecha_corte_actual():
    return parsear_fecha(request.args.get("fecha_corte", ""), date.today())


def proveedor_actual():
    return request.args.get("proveedor_id", "").strip()


def obtener_rango():
    preset = request.args.get("rango", "12m") or "12m"
    rango = resolver_rango(
        preset, request.args.get("desde", ""), request.args.get("hasta", "")
    )

    if rango is None:
        flash("El rango de fechas no es válido. Se aplicaron los últimos 12 meses.", "warning")
        preset = "12m"
        rango = resolver_rango(preset)

    return preset, rango[0], rango[1]


def estado_cheque_actual():
    estado = request.args.get("estado", "").strip()
    return estado if estado in ESTADOS_CHEQUE else ""


def datos_antiguedad():
    corte = fecha_corte_actual()
    proveedor_id = proveedor_actual()
    return (
        resumen_antiguedad(fecha_corte=corte, proveedor_id=proveedor_id),
        corte,
        proveedor_id,
    )


def datos_pagos_mensuales():
    preset, desde, hasta = obtener_rango()
    proveedor_id = proveedor_actual()
    return (
        pagos_por_mes(desde, hasta, proveedor_id=proveedor_id),
        preset,
        desde,
        hasta,
        proveedor_id,
    )


def datos_facturas_vencer():
    corte = fecha_corte_actual()
    proveedor_id = proveedor_actual()
    dias = request.args.get("dias", "30").strip()
    estado = request.args.get("estado", "Todas").strip()
    if estado not in ESTADOS_VENCIMIENTO:
        estado = "Todas"
    return (
        facturas_por_vencer(
            fecha_corte=corte, dias=dias, proveedor_id=proveedor_id, estado=estado
        ),
        corte,
        proveedor_id,
        dias,
        estado,
    )


def datos_cheques():
    preset, desde, hasta = obtener_rango()
    estado = estado_cheque_actual()
    banco = request.args.get("banco", "").strip()
    return (
        cheques_reporte(estado=estado, banco=banco, desde=desde, hasta=hasta),
        preset,
        desde,
        hasta,
        estado,
        banco,
    )


def datos_auditoria():
    preset, desde, hasta = obtener_rango()
    usuario = request.args.get("usuario", "").strip()
    estado = request.args.get("estado_nuevo", "").strip()
    if estado not in ESTADOS_CHEQUE:
        estado = ""
    return (
        auditoria_cheques(desde, hasta, usuario=usuario, estado_nuevo=estado),
        preset,
        desde,
        hasta,
        usuario,
        estado,
    )


def datos_conciliacion():
    preset, desde, hasta = obtener_rango()
    proveedor_id = proveedor_actual()
    return (
        conciliacion_mensual(desde, hasta, proveedor_id=proveedor_id),
        preset,
        desde,
        hasta,
        proveedor_id,
    )


def datos_top():
    corte = fecha_corte_actual()
    proveedor_id = proveedor_actual()
    limite = request.args.get("limite", "10").strip()
    return (
        top_proveedores(
            fecha_corte=corte, limite=limite, proveedor_id=proveedor_id
        ),
        corte,
        proveedor_id,
        limite,
    )


@reportes_bp.route("/")
@login_required
def index():
    return render_template("reportes/index.html")


@reportes_bp.route("/antiguedad")
@login_required
def antiguedad():
    resumen, corte, proveedor_id = datos_antiguedad()
    return render_template(
        "reportes/antiguedad.html",
        **comunes(
            "reportes.antiguedad_csv",
            titulo="Antigüedad de saldos",
            descripcion="Saldos pendientes por proveedor y días de atraso a la fecha de corte.",
            resumen=resumen,
            fecha_corte=corte,
            proveedor_id=proveedor_id,
            presets=presets_corte(),
        ),
    )


@reportes_bp.route("/antiguedad.csv")
@login_required
def antiguedad_csv():
    resumen, _, _ = datos_antiguedad()
    totales = resumen["totales"]
    filas = [
        [
            fila["proveedor"],
            fila["facturas"],
            numero_csv(fila["corriente"]),
            numero_csv(fila["rango_1_30"]),
            numero_csv(fila["rango_31_60"]),
            numero_csv(fila["rango_61_90"]),
            numero_csv(fila["rango_mas_90"]),
            numero_csv(fila["total"]),
        ]
        for fila in resumen["filas"]
    ]
    filas.append(
        [
            "Total",
            totales["facturas"],
            numero_csv(totales["corriente"]),
            numero_csv(totales["rango_1_30"]),
            numero_csv(totales["rango_31_60"]),
            numero_csv(totales["rango_61_90"]),
            numero_csv(totales["rango_mas_90"]),
            numero_csv(totales["total"]),
        ]
    )
    encabezados = [
        "Proveedor",
        "Facturas",
        "Corriente",
        "1 a 30",
        "31 a 60",
        "61 a 90",
        "Mas de 90",
        "Total",
    ]
    return responder_csv("antiguedad.csv", encabezados, filas)


@reportes_bp.route("/pagos-mensuales")
@login_required
def pagos_mensuales():
    resumen, preset, desde, hasta, proveedor_id = datos_pagos_mensuales()
    return render_template(
        "reportes/pagos_mensuales.html",
        **comunes(
            "reportes.pagos_mensuales_csv",
            titulo="Pagos por mes y método",
            descripcion="Pagos efectivos por mes. Los cheques solo cuentan al estar compensados.",
            resumen=resumen,
            rango_actual=preset,
            desde=desde,
            hasta=hasta,
            proveedor_id=proveedor_id,
        ),
    )


@reportes_bp.route("/pagos-mensuales.csv")
@login_required
def pagos_mensuales_csv():
    resumen, _, _, _, _ = datos_pagos_mensuales()
    totales = resumen["totales"]
    filas = [
        [
            fila["mes"],
            fila["proveedor"],
            numero_csv(fila["efectivo"]),
            numero_csv(fila["transferencia"]),
            numero_csv(fila["cheque"]),
            numero_csv(fila["otro"]),
            numero_csv(fila["total"]),
        ]
        for fila in resumen["filas"]
    ]
    filas.append(
        [
            "Total",
            "",
            numero_csv(totales["efectivo"]),
            numero_csv(totales["transferencia"]),
            numero_csv(totales["cheque"]),
            numero_csv(totales["otro"]),
            numero_csv(totales["total"]),
        ]
    )
    encabezados = [
        "Mes",
        "Proveedor",
        "Efectivo",
        "Transferencia",
        "Cheque compensado",
        "Otro",
        "Total",
    ]
    return responder_csv("pagos_mensuales.csv", encabezados, filas)


@reportes_bp.route("/facturas-por-vencer")
@login_required
def facturas_vencer():
    filas, corte, proveedor_id, dias, estado = datos_facturas_vencer()
    return render_template(
        "reportes/facturas_por_vencer.html",
        **comunes(
            "reportes.facturas_vencer_csv",
            titulo="Facturas por vencer y vencidas",
            descripcion="Facturas con saldo dentro del horizonte elegido. Días negativos son atraso.",
            filas=filas,
            fecha_corte=corte,
            proveedor_id=proveedor_id,
            dias=dias,
            estado=estado,
            estados=ESTADOS_VENCIMIENTO,
            presets=presets_corte(),
        ),
    )


@reportes_bp.route("/facturas-por-vencer.csv")
@login_required
def facturas_vencer_csv():
    filas, _, _, _, _ = datos_facturas_vencer()
    filas_csv = [
        [
            fila["numero_factura"],
            fila["proveedor_nombre"],
            fila["fecha_vencimiento"],
            fila["dias"],
            numero_csv(fila["saldo"]),
            fila["estado"],
        ]
        for fila in filas
    ]
    encabezados = [
        "Numero factura",
        "Proveedor",
        "Vencimiento",
        "Dias",
        "Saldo",
        "Estado",
    ]
    return responder_csv("facturas_por_vencer.csv", encabezados, filas_csv)


@reportes_bp.route("/cheques")
@login_required
def cheques():
    resumen, preset, desde, hasta, estado, banco = datos_cheques()
    return render_template(
        "reportes/cheques.html",
        **comunes(
            "reportes.cheques_csv",
            titulo="Reporte de cheques",
            descripcion="Cheques por estado y banco. Afecta saldo muestra el monto efectivo.",
            resumen=resumen,
            rango_actual=preset,
            desde=desde,
            hasta=hasta,
            estado=estado,
            banco=banco,
            estados=ESTADOS_CHEQUE,
        ),
    )


@reportes_bp.route("/cheques.csv")
@login_required
def cheques_csv():
    resumen, _, _, _, _, _ = datos_cheques()
    totales = resumen["totales"]
    filas = [
        [
            fila["numero_cheque"],
            fila["numero_factura"],
            fila["proveedor_nombre"],
            fila["banco_emisor"],
            fila["fecha_cheque"],
            numero_csv(fila["monto"]),
            numero_csv(fila["monto_efectivo"]),
            fila["estado_cheque"],
            fila["dias"],
        ]
        for fila in resumen["filas"]
    ]
    filas.append(
        [
            "Total",
            "",
            "",
            "",
            "",
            numero_csv(totales["monto"]),
            numero_csv(totales["monto_efectivo"]),
            "",
            "",
        ]
    )
    encabezados = [
        "Numero cheque",
        "Numero factura",
        "Proveedor",
        "Banco emisor",
        "Fecha cheque",
        "Monto",
        "Afecta saldo",
        "Estado",
        "Dias",
    ]
    return responder_csv("reporte_cheques.csv", encabezados, filas)


@reportes_bp.route("/auditoria-cheques")
@login_required
def auditoria():
    filas, preset, desde, hasta, usuario, estado = datos_auditoria()
    return render_template(
        "reportes/auditoria_cheques.html",
        **comunes(
            "reportes.auditoria_csv",
            titulo="Auditoría de cheques",
            descripcion="Cada cambio de estado con fecha y usuario responsable.",
            filas=filas,
            rango_actual=preset,
            desde=desde,
            hasta=hasta,
            usuario=usuario,
            estado=estado,
            estados=ESTADOS_CHEQUE,
        ),
    )


@reportes_bp.route("/auditoria-cheques.csv")
@login_required
def auditoria_csv():
    filas, _, _, _, _, _ = datos_auditoria()
    filas_csv = [
        [
            fila["fecha_cambio"],
            fila["numero_cheque"],
            fila["numero_factura"],
            fila["proveedor_nombre"],
            fila["estado_anterior"] or "",
            fila["estado_nuevo"],
            fila["username"],
        ]
        for fila in filas
    ]
    encabezados = [
        "Fecha cambio",
        "Numero cheque",
        "Numero factura",
        "Proveedor",
        "Estado anterior",
        "Estado nuevo",
        "Usuario",
    ]
    return responder_csv("auditoria_cheques.csv", encabezados, filas_csv)


@reportes_bp.route("/conciliacion-mensual")
@login_required
def conciliacion():
    resumen, preset, desde, hasta, proveedor_id = datos_conciliacion()
    return render_template(
        "reportes/conciliacion_mensual.html",
        **comunes(
            "reportes.conciliacion_csv",
            titulo="Conciliación mensual",
            descripcion="Facturas emitidas contra pagos efectivos y saldo al cierre de cada mes.",
            resumen=resumen,
            rango_actual=preset,
            desde=desde,
            hasta=hasta,
            proveedor_id=proveedor_id,
        ),
    )


@reportes_bp.route("/conciliacion-mensual.csv")
@login_required
def conciliacion_csv():
    resumen, _, _, _, _ = datos_conciliacion()
    totales = resumen["totales"]
    filas = [
        [
            fila["mes"],
            fila["proveedor"],
            numero_csv(fila["emitido"]),
            numero_csv(fila["pagado"]),
            numero_csv(fila["variacion"]),
            numero_csv(fila["saldo_cierre"]),
        ]
        for fila in resumen["filas"]
    ]
    filas.append(
        [
            "Total",
            "",
            numero_csv(totales["emitido"]),
            numero_csv(totales["pagado"]),
            numero_csv(totales["variacion"]),
            numero_csv(totales["saldo_cierre"]),
        ]
    )
    encabezados = [
        "Mes",
        "Proveedor",
        "Emitido",
        "Pagado",
        "Variacion",
        "Saldo al cierre",
    ]
    return responder_csv("conciliacion_mensual.csv", encabezados, filas)


@reportes_bp.route("/top-proveedores")
@login_required
def top():
    resumen, corte, proveedor_id, limite = datos_top()
    return render_template(
        "reportes/top_proveedores.html",
        **comunes(
            "reportes.top_csv",
            titulo="Top proveedores",
            descripcion="Proveedores con mayor saldo pendiente a la fecha de corte.",
            resumen=resumen,
            fecha_corte=corte,
            proveedor_id=proveedor_id,
            limite=limite,
            presets=presets_corte(),
        ),
    )


@reportes_bp.route("/top-proveedores.csv")
@login_required
def top_csv():
    resumen, _, _, _ = datos_top()
    totales = resumen["totales"]
    filas = [
        [
            fila["posicion"],
            fila["proveedor"],
            fila["facturas"],
            numero_csv(fila["total"]),
            numero_csv(fila["vencido"]),
            f"{fila['porcentaje']:.1f}".replace(".", ","),
        ]
        for fila in resumen["filas"]
    ]
    filas.append(
        [
            "",
            "Total",
            totales["facturas"],
            numero_csv(totales["total"]),
            "",
            "100,0" if totales["total"] else "0,0",
        ]
    )
    encabezados = [
        "Posicion",
        "Proveedor",
        "Facturas",
        "Saldo total",
        "Saldo vencido",
        "Porcentaje",
    ]
    return responder_csv("top_proveedores.csv", encabezados, filas)
