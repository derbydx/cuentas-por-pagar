from datetime import date
from math import ceil

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
