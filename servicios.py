import csv
import io
from calendar import monthrange
from datetime import date, timedelta
from math import ceil

from flask import Response

from db import get_db

ROLES = ("administrador", "contador", "consultor")
ESTADOS = ("Pendiente", "Parcial", "Pagada", "Vencida")
METODOS_PAGO = ("Efectivo", "Transferencia", "Cheque", "Otro")
ESTADOS_CHEQUE = (
    "Emitido / En cartera",
    "Entregado",
    "Cobrado / Compensado",
    "Devuelto / Rechazado",
)
ESTADOS_CHEQUE_PENDIENTES = ("Emitido / En cartera", "Entregado")


def estado_factura(factura):
    saldo = round(float(factura["saldo"]), 2)
    if saldo <= 0:
        return "Pagada"

    try:
        vencimiento = date.fromisoformat(factura["fecha_vencimiento"])
    except (TypeError, ValueError):
        return "Pendiente"

    if vencimiento < date.today():
        return "Vencida"

    if saldo < round(float(factura["monto_total"]), 2):
        return "Parcial"

    return "Pendiente"


def obtener_facturas(estado=None, proveedor_id=None, buscar=""):
    filas = get_db().execute(
        "SELECT * FROM v_facturas_saldo ORDER BY fecha_vencimiento, id"
    ).fetchall()

    resultados = []
    for fila in filas:
        factura = dict(fila)
        factura["estado"] = estado_factura(factura)

        if estado and factura["estado"] != estado:
            continue

        if proveedor_id:
            try:
                if factura["proveedor_id"] != int(proveedor_id):
                    continue
            except (TypeError, ValueError):
                continue

        if buscar:
            texto = buscar.lower().strip()
            campos = (
                factura["numero_factura"],
                factura["concepto"],
                factura["proveedor_nombre"],
            )
            if not any(texto in str(campo).lower() for campo in campos):
                continue

        resultados.append(factura)

    return resultados


def obtener_factura(factura_id):
    fila = get_db().execute(
        "SELECT * FROM v_facturas_saldo WHERE id = ?", (factura_id,)
    ).fetchone()
    if fila is None:
        return None

    factura = dict(fila)
    factura["estado"] = estado_factura(factura)
    return factura


def obtener_cheques(estado=None, buscar=""):
    sql = """
        SELECT p.*, f.numero_factura, pr.nombre AS proveedor_nombre, v.monto_efectivo
        FROM pagos p
        JOIN facturas f ON f.id = p.factura_id
        JOIN proveedores pr ON pr.id = f.proveedor_id
        JOIN v_pagos_efectivos v ON v.id = p.id
        WHERE p.metodo = 'Cheque'
    """
    parametros = []

    if estado:
        sql += " AND p.estado_cheque = ?"
        parametros.append(estado)

    if buscar:
        texto = f"%{buscar.lower().strip()}%"
        sql += " AND (LOWER(p.numero_cheque) LIKE ? OR LOWER(f.numero_factura) LIKE ? OR LOWER(pr.nombre) LIKE ?)"
        parametros.extend((texto, texto, texto))

    sql += " ORDER BY p.fecha_cheque DESC, p.id DESC"
    return [dict(fila) for fila in get_db().execute(sql, parametros).fetchall()]


def obtener_pagos_exportar(proveedor_id=None, buscar=""):
    sql = """
        SELECT p.*, f.numero_factura, pr.nombre AS proveedor_nombre, v.monto_efectivo
        FROM pagos p
        JOIN facturas f ON f.id = p.factura_id
        JOIN proveedores pr ON pr.id = f.proveedor_id
        JOIN v_pagos_efectivos v ON v.id = p.id
        WHERE 1 = 1
    """
    parametros = []

    if proveedor_id:
        try:
            parametros.append(int(proveedor_id))
        except (TypeError, ValueError):
            return []
        sql += " AND f.proveedor_id = ?"

    if buscar:
        texto = f"%{buscar.lower().strip()}%"
        sql += " AND (LOWER(f.numero_factura) LIKE ? OR LOWER(pr.nombre) LIKE ? OR LOWER(COALESCE(p.numero_cheque, '')) LIKE ?)"
        parametros.extend((texto, texto, texto))

    sql += " ORDER BY p.fecha_pago DESC, p.id DESC"
    return [dict(fila) for fila in get_db().execute(sql, parametros).fetchall()]


def obtener_historial_pago(pago_id):
    sql = """
        SELECT h.*, u.username
        FROM pago_estado_historial h
        LEFT JOIN usuarios u ON u.id = h.usuario_id
        WHERE h.pago_id = ?
        ORDER BY h.id
    """
    return [dict(fila) for fila in get_db().execute(sql, (pago_id,)).fetchall()]


def obtener_usuarios(buscar=""):
    filas = get_db().execute(
        "SELECT id, username, rol, activo, creado_en FROM usuarios ORDER BY username, id"
    ).fetchall()

    resultados = []
    for fila in filas:
        usuario = dict(fila)
        if buscar and buscar.lower().strip() not in usuario["username"].lower():
            continue
        resultados.append(usuario)

    return resultados


def obtener_proveedores(buscar=""):
    filas = get_db().execute(
        "SELECT * FROM proveedores ORDER BY nombre, id"
    ).fetchall()

    resultados = []
    for fila in filas:
        proveedor = dict(fila)
        if buscar:
            texto = buscar.lower().strip()
            campos = (
                proveedor["nombre"],
                proveedor["telefono"],
                proveedor["email"],
                proveedor["notas"],
            )
            if not any(texto in str(campo or "").lower() for campo in campos):
                continue
        resultados.append(proveedor)

    return resultados


def obtener_pagos(factura_id=None):
    sql = "SELECT * FROM v_pagos_efectivos"
    parametros = ()

    if factura_id:
        sql += " WHERE factura_id = ?"
        parametros = (factura_id,)

    sql += " ORDER BY fecha_pago DESC, id DESC"
    filas = get_db().execute(sql, parametros).fetchall()
    return [dict(fila) for fila in filas]


def metricas_dashboard():
    facturas = obtener_facturas()
    mes_actual = date.today().strftime("%Y-%m")

    pagado_mes = sum(
        float(pago["monto_efectivo"])
        for pago in obtener_pagos()
        if str(pago["fecha_pago"]).startswith(mes_actual)
    )

    cheques = get_db().execute(
        "SELECT COALESCE(SUM(monto), 0) FROM pagos "
        "WHERE metodo = 'Cheque' AND estado_cheque IN (?, ?)",
        ESTADOS_CHEQUE_PENDIENTES,
    ).fetchone()[0]

    return {
        "total_por_pagar": round(
            sum(float(f["saldo"]) for f in facturas if f["saldo"] > 0), 2
        ),
        "total_vencido": round(
            sum(float(f["saldo"]) for f in facturas if f["estado"] == "Vencida"), 2
        ),
        "total_pagado_mes": round(pagado_mes, 2),
        "total_cheques_pendientes": round(float(cheques), 2),
    }


def paginar(elementos, pagina=1, por_pagina=20):
    try:
        pagina = int(pagina)
    except (TypeError, ValueError):
        pagina = 1

    pagina = max(1, pagina)
    total = len(elementos)
    total_paginas = max(1, ceil(total / por_pagina))
    pagina = min(pagina, total_paginas)
    inicio = (pagina - 1) * por_pagina

    return {
        "elementos": elementos[inicio : inicio + por_pagina],
        "pagina": pagina,
        "total_paginas": total_paginas,
        "total": total,
    }


def formato_moneda(valor):
    return f"RD$ {float(valor):,.2f}"


def valor_csv(valor):
    texto = "" if valor is None else str(valor)
    if texto.startswith(("=", "+", "-", "@", "\t", "\r")):
        return "'" + texto
    return texto


def numero_csv(valor):
    return f"{float(valor):.2f}".replace(".", ",")


def responder_csv(nombre, encabezados, filas):
    salida = io.StringIO()
    salida.write("\ufeff")
    escritor = csv.writer(salida, delimiter=";", lineterminator="\r\n")
    escritor.writerow([valor_csv(columna) for columna in encabezados])

    for fila in filas:
        escritor.writerow([valor_csv(celda) for celda in fila])

    respuesta = Response(salida.getvalue(), mimetype="text/csv; charset=utf-8")
    respuesta.headers["Content-Disposition"] = f'attachment; filename="{nombre}"'
    return respuesta


RANGOS_FECHA = (
    ("mes", "Mes actual"),
    ("3m", "Últimos 3 meses"),
    ("trimestre_actual", "Trimestre actual"),
    ("trimestre_anterior", "Trimestre anterior"),
    ("6m", "Últimos 6 meses"),
    ("12m", "Últimos 12 meses"),
    ("personalizado", "Personalizado"),
)

ESTADOS_VENCIMIENTO = ("Todas", "Vencida", "Por vencer")
CLAVES_ANTIGUEDAD = (
    "corriente",
    "rango_1_30",
    "rango_31_60",
    "rango_61_90",
    "rango_mas_90",
)


def sumar_meses(fecha, cantidad):
    indice = fecha.month - 1 + cantidad
    anio = fecha.year + indice // 12
    mes = indice % 12 + 1
    dia = min(fecha.day, monthrange(anio, mes)[1])
    return date(anio, mes, dia)


def inicio_mes(fecha):
    return fecha.replace(day=1)


def fin_mes(fecha):
    return date(fecha.year, fecha.month, monthrange(fecha.year, fecha.month)[1])


def inicio_trimestre(fecha):
    mes = ((fecha.month - 1) // 3) * 3 + 1
    return date(fecha.year, mes, 1)


def resolver_rango(preset, desde_texto="", hasta_texto="", hoy=None):
    hoy = hoy or date.today()

    if preset == "personalizado":
        try:
            desde = date.fromisoformat(desde_texto)
            hasta = date.fromisoformat(hasta_texto)
        except (TypeError, ValueError):
            return None
        return (desde, hasta) if desde <= hasta else None

    if preset == "mes":
        return inicio_mes(hoy), hoy
    if preset == "3m":
        return inicio_mes(sumar_meses(hoy, -2)), hoy
    if preset == "trimestre_actual":
        return inicio_trimestre(hoy), hoy
    if preset == "trimestre_anterior":
        hasta = inicio_trimestre(hoy) - timedelta(days=1)
        return inicio_trimestre(hasta), hasta
    if preset == "6m":
        return inicio_mes(sumar_meses(hoy, -5)), hoy
    return inicio_mes(sumar_meses(hoy, -11)), hoy


def presets_corte(hoy=None):
    hoy = hoy or date.today()
    fin_trimestre = inicio_trimestre(hoy) - timedelta(days=1)
    return (
        (hoy.isoformat(), "Hoy"),
        (fin_trimestre.isoformat(), "Fin del trimestre anterior"),
        (sumar_meses(hoy, -6).isoformat(), "Hace 6 meses"),
        (sumar_meses(hoy, -12).isoformat(), "Hace 12 meses"),
    )


def parsear_fecha(texto, por_defecto=None):
    if not texto:
        return por_defecto
    try:
        return date.fromisoformat(texto)
    except (TypeError, ValueError):
        return por_defecto


def meses_entre(desde, hasta):
    actual = inicio_mes(desde)
    final = inicio_mes(hasta)
    meses = []

    while actual <= final:
        meses.append(actual)
        actual = sumar_meses(actual, 1)

    return meses


def resumen_antiguedad(fecha_corte=None, proveedor_id=None, hoy=None):
    corte = fecha_corte or (hoy or date.today())
    agrupado = {}

    for factura in obtener_facturas(proveedor_id=proveedor_id):
        saldo = round(float(factura["saldo"]), 2)
        if saldo <= 0:
            continue

        try:
            vencimiento = date.fromisoformat(factura["fecha_vencimiento"])
        except (TypeError, ValueError):
            continue

        dias = (corte - vencimiento).days
        if dias <= 0:
            clave = "corriente"
        elif dias <= 30:
            clave = "rango_1_30"
        elif dias <= 60:
            clave = "rango_31_60"
        elif dias <= 90:
            clave = "rango_61_90"
        else:
            clave = "rango_mas_90"

        proveedor = factura["proveedor_id"]
        if proveedor not in agrupado:
            fila = {
                "proveedor_id": proveedor,
                "proveedor": factura["proveedor_nombre"],
                "facturas": 0,
                "total": 0.0,
            }
            for nombre in CLAVES_ANTIGUEDAD:
                fila[nombre] = 0.0
            agrupado[proveedor] = fila

        agrupado[proveedor]["facturas"] += 1
        agrupado[proveedor][clave] += saldo
        agrupado[proveedor]["total"] += saldo

    filas = sorted(
        agrupado.values(), key=lambda fila: (-fila["total"], fila["proveedor"])
    )

    totales = {"facturas": sum(fila["facturas"] for fila in filas), "total": 0.0}
    for nombre in CLAVES_ANTIGUEDAD:
        totales[nombre] = round(sum(fila[nombre] for fila in filas), 2)
    totales["total"] = round(sum(fila["total"] for fila in filas), 2)

    return {"filas": filas, "totales": totales}


def pagos_por_mes(desde, hasta, proveedor_id=None):
    pagos = obtener_pagos_exportar(proveedor_id=proveedor_id)
    desde_texto = desde.isoformat()
    hasta_texto = hasta.isoformat()
    proveedor = "Todos"

    if proveedor_id and pagos:
        proveedor = pagos[0]["proveedor_nombre"]

    filas = []
    for mes in meses_entre(desde, hasta):
        clave = mes.strftime("%Y-%m")
        fila = {
            "mes": clave,
            "proveedor": proveedor,
            "efectivo": 0.0,
            "transferencia": 0.0,
            "cheque": 0.0,
            "otro": 0.0,
            "total": 0.0,
        }

        for pago in pagos:
            fecha = str(pago["fecha_pago"])
            if fecha.startswith(clave) and desde_texto <= fecha <= hasta_texto:
                metodo = pago["metodo"].lower()
                monto = round(float(pago["monto_efectivo"]), 2)
                fila[metodo] += monto
                fila["total"] += monto

        for clave_monto in ("efectivo", "transferencia", "cheque", "otro", "total"):
            fila[clave_monto] = round(fila[clave_monto], 2)
        filas.append(fila)

    totales = {}
    for clave_monto in ("efectivo", "transferencia", "cheque", "otro", "total"):
        totales[clave_monto] = round(sum(f[clave_monto] for f in filas), 2)

    return {"filas": filas, "totales": totales}


def facturas_por_vencer(
    fecha_corte=None, dias=30, proveedor_id=None, estado="Todas", hoy=None
):
    corte = fecha_corte or (hoy or date.today())

    try:
        horizonte = int(dias)
    except (TypeError, ValueError):
        horizonte = 30
    horizonte = max(0, min(horizonte, 365))

    filas = []
    for factura in obtener_facturas(proveedor_id=proveedor_id):
        saldo = round(float(factura["saldo"]), 2)
        if saldo <= 0:
            continue

        try:
            vencimiento = date.fromisoformat(factura["fecha_vencimiento"])
        except (TypeError, ValueError):
            continue

        restantes = (vencimiento - corte).days
        if estado == "Vencida" and restantes >= 0:
            continue
        if estado == "Por vencer" and not 0 <= restantes <= horizonte:
            continue
        if estado == "Todas" and restantes > horizonte:
            continue

        fila = dict(factura)
        fila["dias"] = restantes
        fila["vencida"] = restantes < 0
        fila["estado"] = "Vencida" if restantes < 0 else "Por vencer"
        filas.append(fila)

    filas.sort(key=lambda fila: fila["dias"])
    return filas


def cheques_reporte(estado="", banco="", desde=None, hasta=None, hoy=None):
    hoy = hoy or date.today()
    filas = []

    for cheque in obtener_cheques(estado=estado):
        if banco and banco.lower().strip() not in str(
            cheque["banco_emisor"] or ""
        ).lower():
            continue

        fecha = parsear_fecha(cheque["fecha_cheque"])
        if desde and (fecha is None or fecha < desde):
            continue
        if hasta and (fecha is None or fecha > hasta):
            continue

        fila = dict(cheque)
        fila["dias"] = (hoy - fecha).days if fecha else None
        filas.append(fila)

    totales = {
        "cheques": len(filas),
        "monto": round(sum(float(f["monto"]) for f in filas), 2),
        "monto_efectivo": round(sum(float(f["monto_efectivo"]) for f in filas), 2),
    }
    return {"filas": filas, "totales": totales}


def auditoria_cheques(desde=None, hasta=None, usuario="", estado_nuevo=None):
    sql = """
        SELECT h.fecha_cambio, p.numero_cheque, f.numero_factura,
               pr.nombre AS proveedor_nombre, h.estado_anterior, h.estado_nuevo,
               COALESCE(u.username, '-') AS username
        FROM pago_estado_historial h
        JOIN pagos p ON p.id = h.pago_id
        JOIN facturas f ON f.id = p.factura_id
        JOIN proveedores pr ON pr.id = f.proveedor_id
        LEFT JOIN usuarios u ON u.id = h.usuario_id
        WHERE p.metodo = 'Cheque'
    """
    parametros = []

    if desde:
        sql += " AND substr(h.fecha_cambio, 1, 10) >= ?"
        parametros.append(desde.isoformat())
    if hasta:
        sql += " AND substr(h.fecha_cambio, 1, 10) <= ?"
        parametros.append(hasta.isoformat())
    if usuario:
        sql += " AND LOWER(COALESCE(u.username, '')) LIKE ?"
        parametros.append(f"%{usuario.lower().strip()}%")
    if estado_nuevo:
        sql += " AND h.estado_nuevo = ?"
        parametros.append(estado_nuevo)

    sql += " ORDER BY h.fecha_cambio DESC, h.id DESC"
    return [dict(fila) for fila in get_db().execute(sql, parametros).fetchall()]


def top_proveedores(fecha_corte=None, limite=10, proveedor_id=None, hoy=None):
    resumen = resumen_antiguedad(
        fecha_corte=fecha_corte, proveedor_id=proveedor_id, hoy=hoy
    )

    try:
        limite = int(limite)
    except (TypeError, ValueError):
        limite = 10
    limite = max(1, min(limite, 50))

    total_general = resumen["totales"]["total"]
    filas = []
    for posicion, fila in enumerate(resumen["filas"][:limite], start=1):
        item = dict(fila)
        item["posicion"] = posicion
        item["vencido"] = round(fila["total"] - fila["corriente"], 2)
        item["porcentaje"] = (
            round(fila["total"] / total_general * 100, 1) if total_general else 0.0
        )
        filas.append(item)

    return {"filas": filas, "totales": resumen["totales"]}


def conciliacion_mensual(desde, hasta, proveedor_id=None):
    facturas = obtener_facturas(proveedor_id=proveedor_id)
    pagos = obtener_pagos_exportar(proveedor_id=proveedor_id)
    proveedor = "Todos"

    if proveedor_id and (facturas or pagos):
        proveedor = (facturas or pagos)[0]["proveedor_nombre"]

    filas = []
    for mes in meses_entre(desde, hasta):
        clave = mes.strftime("%Y-%m")
        fin = fin_mes(mes).isoformat()
        emitido = round(
            sum(
                float(f["monto_total"])
                for f in facturas
                if str(f["fecha_emision"]).startswith(clave)
            ),
            2,
        )
        pagado = round(
            sum(
                float(p["monto_efectivo"])
                for p in pagos
                if str(p["fecha_pago"]).startswith(clave)
            ),
            2,
        )
        saldo_cierre = round(
            sum(
                float(f["monto_total"])
                for f in facturas
                if str(f["fecha_emision"]) <= fin
            )
            - sum(
                float(p["monto_efectivo"])
                for p in pagos
                if str(p["fecha_pago"]) <= fin
            ),
            2,
        )

        filas.append(
            {
                "mes": clave,
                "proveedor": proveedor,
                "emitido": emitido,
                "pagado": pagado,
                "variacion": round(emitido - pagado, 2),
                "saldo_cierre": saldo_cierre,
            }
        )

    totales = {
        "emitido": round(sum(f["emitido"] for f in filas), 2),
        "pagado": round(sum(f["pagado"] for f in filas), 2),
    }
    totales["variacion"] = round(totales["emitido"] - totales["pagado"], 2)
    totales["saldo_cierre"] = filas[-1]["saldo_cierre"] if filas else 0.0

    return {"filas": filas, "totales": totales}
