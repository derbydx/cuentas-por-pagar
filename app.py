import csv
import io
import os
import sqlite3
from datetime import date

from flask import (
    Flask,
    Response,
    abort,
    flash,
    redirect,
    render_template,
    request,
    session,
    url_for,
)
from werkzeug.security import generate_password_hash

from auth import (
    auth_bp,
    crear_administrador_inicial,
    inyectar_contexto,
    login_required,
    role_required,
    validar_csrf,
)
from db import close_db, get_db, init_db
from servicios import (
    ESTADOS,
    ESTADOS_CHEQUE,
    METODOS_PAGO,
    ROLES,
    formato_moneda,
    metricas_dashboard,
    obtener_cheques,
    obtener_factura,
    obtener_facturas,
    obtener_historial_pago,
    obtener_pagos,
    obtener_pagos_exportar,
    obtener_proveedores,
    obtener_usuarios,
    paginar,
)

BASE_DIR = os.path.dirname(os.path.abspath(__file__))

app = Flask(__name__)

clave = os.environ.get("SECRET_KEY")
if not clave:
    print("ADVERTENCIA: SECRET_KEY no definida. Usando valor de desarrollo.")

app.config["SECRET_KEY"] = clave or "valor-de-desarrollo-cambiar-en-produccion"
app.config["SESSION_COOKIE_HTTPONLY"] = True
app.config["SESSION_COOKIE_SAMESITE"] = "Lax"
app.config["ADMIN_PASSWORD"] = os.environ.get("ADMIN_PASSWORD")
app.config["BASE_DATOS"] = os.environ.get(
    "BASE_DATOS", os.path.join(BASE_DIR, "cuentas_por_pagar.db")
)

app.teardown_appcontext(close_db)
app.register_blueprint(auth_bp)
app.context_processor(inyectar_contexto)
app.jinja_env.filters["moneda"] = formato_moneda

with app.app_context():
    init_db()
    crear_administrador_inicial()


def datos_proveedor_formulario():
    return {
        "nombre": request.form.get("nombre", "").strip(),
        "telefono": request.form.get("telefono", "").strip(),
        "email": request.form.get("email", "").strip(),
        "notas": request.form.get("notas", "").strip(),
    }


@app.route("/")
@login_required
def dashboard():
    facturas = obtener_facturas()
    por_atender = [factura for factura in facturas if factura["saldo"] > 0][:8]
    return render_template(
        "dashboard.html",
        metricas=metricas_dashboard(),
        por_atender=por_atender,
    )


@app.route("/proveedores")
@login_required
def proveedores():
    buscar = request.args.get("q", "").strip()
    datos = paginar(obtener_proveedores(buscar), pagina=request.args.get("pagina", 1))
    return render_template("proveedores.html", datos=datos, buscar=buscar)


@app.route("/proveedores/nuevo", methods=["GET", "POST"])
@role_required("administrador", "contador")
def proveedor_nuevo():
    if request.method == "POST":
        validar_csrf()
        proveedor = datos_proveedor_formulario()

        if not proveedor["nombre"]:
            flash("El nombre es obligatorio.", "danger")
            return render_template("proveedor_form.html", proveedor=proveedor)

        if proveedor["email"] and "@" not in proveedor["email"]:
            flash("El email no parece válido.", "danger")
            return render_template("proveedor_form.html", proveedor=proveedor)

        get_db().execute(
            "INSERT INTO proveedores (nombre, telefono, email, notas) VALUES (?, ?, ?, ?)",
            (
                proveedor["nombre"],
                proveedor["telefono"],
                proveedor["email"],
                proveedor["notas"],
            ),
        )
        get_db().commit()
        flash("Proveedor creado.", "success")
        return redirect(url_for("proveedores"))

    return render_template("proveedor_form.html", proveedor=None)


@app.route("/proveedores/<int:proveedor_id>/editar", methods=["GET", "POST"])
@role_required("administrador", "contador")
def proveedor_editar(proveedor_id):
    fila = get_db().execute(
        "SELECT * FROM proveedores WHERE id = ?", (proveedor_id,)
    ).fetchone()
    if fila is None:
        abort(404)

    if request.method == "POST":
        validar_csrf()
        proveedor = datos_proveedor_formulario()

        if not proveedor["nombre"]:
            flash("El nombre es obligatorio.", "danger")
            return render_template("proveedor_form.html", proveedor=proveedor)

        if proveedor["email"] and "@" not in proveedor["email"]:
            flash("El email no parece válido.", "danger")
            return render_template("proveedor_form.html", proveedor=proveedor)

        get_db().execute(
            "UPDATE proveedores SET nombre = ?, telefono = ?, email = ?, notas = ? WHERE id = ?",
            (
                proveedor["nombre"],
                proveedor["telefono"],
                proveedor["email"],
                proveedor["notas"],
                proveedor_id,
            ),
        )
        get_db().commit()
        flash("Proveedor actualizado.", "success")
        return redirect(url_for("proveedores"))

    return render_template("proveedor_form.html", proveedor=dict(fila))


@app.route("/proveedores/<int:proveedor_id>/eliminar", methods=["POST"])
@role_required("administrador")
def proveedor_eliminar(proveedor_id):
    validar_csrf()
    db = get_db()

    try:
        cursor = db.execute("DELETE FROM proveedores WHERE id = ?", (proveedor_id,))
        if cursor.rowcount == 0:
            db.rollback()
            flash("Proveedor no encontrado.", "warning")
        else:
            db.commit()
            flash("Proveedor eliminado.", "success")
    except sqlite3.IntegrityError:
        db.rollback()
        flash("No se puede eliminar: el proveedor tiene facturas asociadas.", "danger")

    return redirect(url_for("proveedores"))


def datos_usuario_formulario():
    return {
        "username": request.form.get("username", "").strip(),
        "password": request.form.get("password", ""),
        "rol": request.form.get("rol", ""),
        "activo": 1 if request.form.get("activo") else 0,
    }


def ultimo_administrador(db, usuario_id=0):
    fila = db.execute(
        "SELECT COUNT(*) FROM usuarios "
        "WHERE rol = 'administrador' AND activo = 1 AND id != ?",
        (usuario_id,),
    ).fetchone()
    return fila[0] == 0


@app.route("/usuarios")
@role_required("administrador")
def usuarios():
    buscar = request.args.get("q", "").strip()
    datos = paginar(obtener_usuarios(buscar), pagina=request.args.get("pagina", 1))
    return render_template("usuarios.html", datos=datos, buscar=buscar)


@app.route("/usuarios/nuevo", methods=["GET", "POST"])
@role_required("administrador")
def usuario_nuevo():
    if request.method == "POST":
        validar_csrf()
        datos = datos_usuario_formulario()
        db = get_db()

        if not datos["username"]:
            flash("El usuario es obligatorio.", "danger")
        elif len(datos["password"]) < 8:
            flash("La contraseña debe tener al menos 8 caracteres.", "danger")
        elif datos["rol"] not in ROLES:
            flash("Selecciona un rol válido.", "danger")
        elif db.execute(
            "SELECT 1 FROM usuarios WHERE username = ?", (datos["username"],)
        ).fetchone():
            flash("Ese nombre de usuario ya existe.", "danger")
        else:
            db.execute(
                "INSERT INTO usuarios (username, password_hash, rol, activo) VALUES (?, ?, ?, ?)",
                (
                    datos["username"],
                    generate_password_hash(datos["password"]),
                    datos["rol"],
                    datos["activo"],
                ),
            )
            db.commit()
            flash("Usuario creado.", "success")
            return redirect(url_for("usuarios"))

        return render_template(
            "usuario_form.html", usuario=datos, es_nuevo=True, roles=ROLES
        )

    return render_template("usuario_form.html", usuario=None, es_nuevo=True, roles=ROLES)


@app.route("/usuarios/<int:usuario_id>/editar", methods=["GET", "POST"])
@role_required("administrador")
def usuario_editar(usuario_id):
    db = get_db()
    fila = db.execute(
        "SELECT id, username, rol, activo FROM usuarios WHERE id = ?", (usuario_id,)
    ).fetchone()
    if fila is None:
        abort(404)

    if request.method == "POST":
        validar_csrf()
        datos = datos_usuario_formulario()
        actual = dict(fila)

        if not datos["username"]:
            flash("El usuario es obligatorio.", "danger")
        elif datos["rol"] not in ROLES:
            flash("Selecciona un rol válido.", "danger")
        elif db.execute(
            "SELECT 1 FROM usuarios WHERE username = ? AND id != ?",
            (datos["username"], usuario_id),
        ).fetchone():
            flash("Ese nombre de usuario ya existe.", "danger")
        elif datos["password"] and len(datos["password"]) < 8:
            flash("La contraseña debe tener al menos 8 caracteres.", "danger")
        elif (
            actual["rol"] == "administrador"
            and actual["activo"] == 1
            and (datos["rol"] != "administrador" or datos["activo"] == 0)
            and ultimo_administrador(db, usuario_id)
        ):
            flash("No se puede quitar el rol al último administrador activo.", "danger")
        else:
            if datos["password"]:
                db.execute(
                    "UPDATE usuarios SET username = ?, password_hash = ?, rol = ?, activo = ? WHERE id = ?",
                    (
                        datos["username"],
                        generate_password_hash(datos["password"]),
                        datos["rol"],
                        datos["activo"],
                        usuario_id,
                    ),
                )
            else:
                db.execute(
                    "UPDATE usuarios SET username = ?, rol = ?, activo = ? WHERE id = ?",
                    (datos["username"], datos["rol"], datos["activo"], usuario_id),
                )
            db.commit()
            flash("Usuario actualizado.", "success")
            return redirect(url_for("usuarios"))

        return render_template(
            "usuario_form.html", usuario=datos, es_nuevo=False, roles=ROLES
        )

    return render_template(
        "usuario_form.html", usuario=dict(fila), es_nuevo=False, roles=ROLES
    )


@app.route("/usuarios/<int:usuario_id>/eliminar", methods=["POST"])
@role_required("administrador")
def usuario_eliminar(usuario_id):
    validar_csrf()
    db = get_db()
    fila = db.execute(
        "SELECT rol, activo FROM usuarios WHERE id = ?", (usuario_id,)
    ).fetchone()

    if fila is None:
        flash("Usuario no encontrado.", "warning")
    elif (
        fila["rol"] == "administrador"
        and fila["activo"] == 1
        and ultimo_administrador(db, usuario_id)
    ):
        flash("No se puede eliminar al último administrador activo.", "danger")
    else:
        db.execute("DELETE FROM usuarios WHERE id = ?", (usuario_id,))
        db.commit()
        flash("Usuario eliminado.", "success")

    return redirect(url_for("usuarios"))


def datos_factura_formulario():
    try:
        proveedor_id = int(request.form.get("proveedor_id", 0))
    except (TypeError, ValueError):
        proveedor_id = 0

    return {
        "proveedor_id": proveedor_id,
        "numero_factura": request.form.get("numero_factura", "").strip(),
        "concepto": request.form.get("concepto", "").strip(),
        "monto_total": request.form.get("monto_total", "").strip(),
        "fecha_emision": request.form.get("fecha_emision", "").strip(),
        "fecha_vencimiento": request.form.get("fecha_vencimiento", "").strip(),
    }


def validar_factura(datos, db, factura_id=0):
    if not datos["numero_factura"]:
        return "El número de factura es obligatorio."

    if not datos["concepto"]:
        return "El concepto es obligatorio."

    if not datos["proveedor_id"]:
        return "Selecciona un proveedor."

    if not db.execute(
        "SELECT 1 FROM proveedores WHERE id = ?", (datos["proveedor_id"],)
    ).fetchone():
        return "El proveedor seleccionado no existe."

    try:
        monto = float(datos["monto_total"])
    except (TypeError, ValueError):
        return "El monto debe ser un número."

    if monto <= 0:
        return "El monto debe ser mayor que cero."

    try:
        emision = date.fromisoformat(datos["fecha_emision"])
        vencimiento = date.fromisoformat(datos["fecha_vencimiento"])
    except (TypeError, ValueError):
        return "Las fechas no son válidas."

    if vencimiento < emision:
        return "La fecha de vencimiento no puede ser anterior a la emisión."

    if db.execute(
        "SELECT 1 FROM facturas WHERE numero_factura = ? AND id != ?",
        (datos["numero_factura"], factura_id),
    ).fetchone():
        return "Ese número de factura ya existe."

    return None


@app.route("/facturas")
@login_required
def facturas():
    estado = request.args.get("estado", "").strip()
    proveedor_id = request.args.get("proveedor_id", "").strip()
    buscar = request.args.get("q", "").strip()

    datos = paginar(
        obtener_facturas(estado=estado, proveedor_id=proveedor_id, buscar=buscar),
        pagina=request.args.get("pagina", 1),
    )

    return render_template(
        "facturas.html",
        datos=datos,
        estados=ESTADOS,
        proveedores=obtener_proveedores(),
        estado=estado,
        proveedor_id=proveedor_id,
        buscar=buscar,
    )


@app.route("/facturas/nuevo", methods=["GET", "POST"])
@role_required("administrador", "contador")
def factura_nuevo():
    db = get_db()

    if request.method == "POST":
        validar_csrf()
        datos = datos_factura_formulario()
        error = validar_factura(datos, db)

        if error:
            flash(error, "danger")
        else:
            db.execute(
                "INSERT INTO facturas "
                "(proveedor_id, numero_factura, concepto, monto_total, fecha_emision, fecha_vencimiento) "
                "VALUES (?, ?, ?, ?, ?, ?)",
                (
                    datos["proveedor_id"],
                    datos["numero_factura"],
                    datos["concepto"],
                    float(datos["monto_total"]),
                    datos["fecha_emision"],
                    datos["fecha_vencimiento"],
                ),
            )
            db.commit()
            flash("Factura creada.", "success")
            return redirect(url_for("facturas"))

        return render_template(
            "factura_form.html", factura=datos, proveedores=obtener_proveedores()
        )

    return render_template(
        "factura_form.html", factura=None, proveedores=obtener_proveedores()
    )


@app.route("/facturas/<int:factura_id>")
@login_required
def factura_detalle(factura_id):
    factura = obtener_factura(factura_id)
    if factura is None:
        abort(404)

    pagos = obtener_pagos(factura_id)
    monto = float(factura["monto_total"])
    pagado = float(factura["total_pagado"])
    porcentaje = min(100, round(pagado / monto * 100)) if monto else 0

    return render_template(
        "factura_detalle.html", factura=factura, pagos=pagos, porcentaje=porcentaje
    )


@app.route("/facturas/<int:factura_id>/editar", methods=["GET", "POST"])
@role_required("administrador", "contador")
def factura_editar(factura_id):
    db = get_db()
    fila = db.execute("SELECT * FROM facturas WHERE id = ?", (factura_id,)).fetchone()
    if fila is None:
        abort(404)

    if request.method == "POST":
        validar_csrf()
        datos = datos_factura_formulario()
        error = validar_factura(datos, db, factura_id)

        if error:
            flash(error, "danger")
        else:
            db.execute(
                "UPDATE facturas SET proveedor_id = ?, numero_factura = ?, concepto = ?, "
                "monto_total = ?, fecha_emision = ?, fecha_vencimiento = ? WHERE id = ?",
                (
                    datos["proveedor_id"],
                    datos["numero_factura"],
                    datos["concepto"],
                    float(datos["monto_total"]),
                    datos["fecha_emision"],
                    datos["fecha_vencimiento"],
                    factura_id,
                ),
            )
            db.commit()
            flash("Factura actualizada.", "success")
            return redirect(url_for("factura_detalle", factura_id=factura_id))

        return render_template(
            "factura_form.html", factura=datos, proveedores=obtener_proveedores()
        )

    return render_template(
        "factura_form.html", factura=dict(fila), proveedores=obtener_proveedores()
    )


@app.route("/facturas/<int:factura_id>/eliminar", methods=["POST"])
@role_required("administrador")
def factura_eliminar(factura_id):
    validar_csrf()
    db = get_db()
    cursor = db.execute("DELETE FROM facturas WHERE id = ?", (factura_id,))

    if cursor.rowcount == 0:
        db.rollback()
        flash("Factura no encontrada.", "warning")
    else:
        db.commit()
        flash("Factura eliminada.", "success")

    return redirect(url_for("facturas"))


def datos_pago_formulario():
    return {
        "monto": request.form.get("monto", "").strip(),
        "fecha_pago": request.form.get("fecha_pago", "").strip(),
        "metodo": request.form.get("metodo", ""),
        "numero_cheque": request.form.get("numero_cheque", "").strip(),
        "banco_emisor": request.form.get("banco_emisor", "").strip(),
        "fecha_cheque": request.form.get("fecha_cheque", "").strip(),
        "estado_cheque": request.form.get("estado_cheque", ""),
        "notas": request.form.get("notas", "").strip(),
    }


def validar_pago(datos, saldo):
    try:
        monto = float(datos["monto"])
    except (TypeError, ValueError):
        return "El monto debe ser un número."

    if monto <= 0:
        return "El monto debe ser mayor que cero."

    if monto > round(float(saldo), 2) + 0.01:
        return "El pago no puede superar el saldo pendiente."

    try:
        date.fromisoformat(datos["fecha_pago"])
    except (TypeError, ValueError):
        return "La fecha de pago no es válida."

    if datos["metodo"] not in METODOS_PAGO:
        return "Selecciona un método de pago válido."

    if datos["metodo"] == "Cheque":
        if not all(
            (
                datos["numero_cheque"],
                datos["banco_emisor"],
                datos["fecha_cheque"],
                datos["estado_cheque"],
            )
        ):
            return "Los datos del cheque son obligatorios."

        try:
            date.fromisoformat(datos["fecha_cheque"])
        except (TypeError, ValueError):
            return "La fecha del cheque no es válida."

        if datos["estado_cheque"] not in ESTADOS_CHEQUE:
            return "El estado del cheque no es válido."

    return None


def render_pago_form(factura, datos):
    return render_template(
        "pago_form.html",
        factura=factura,
        datos=datos,
        metodos=METODOS_PAGO,
        estados_cheque=ESTADOS_CHEQUE,
        hoy=date.today().isoformat(),
    )


@app.route("/facturas/<int:factura_id>/pagos/nuevo", methods=["GET", "POST"])
@role_required("administrador", "contador")
def pago_nuevo(factura_id):
    factura = obtener_factura(factura_id)
    if factura is None:
        abort(404)

    if request.method == "POST":
        validar_csrf()
        datos = datos_pago_formulario()
        error = validar_pago(datos, factura["saldo"])

        if error:
            flash(error, "danger")
            return render_pago_form(factura, datos)

        db = get_db()
        db.execute("BEGIN IMMEDIATE")
        try:
            fila = db.execute(
                "SELECT saldo FROM v_facturas_saldo WHERE id = ?", (factura_id,)
            ).fetchone()
            saldo_actual = float(fila["saldo"]) if fila else 0.0

            if float(datos["monto"]) > round(saldo_actual, 2) + 0.01:
                db.rollback()
                flash("El pago no puede superar el saldo pendiente.", "danger")
                return render_pago_form(factura, datos)

            if datos["metodo"] == "Cheque":
                numero_cheque = datos["numero_cheque"]
                banco_emisor = datos["banco_emisor"]
                fecha_cheque = datos["fecha_cheque"]
                estado_cheque = datos["estado_cheque"]
            else:
                numero_cheque = None
                banco_emisor = None
                fecha_cheque = None
                estado_cheque = None

            db.execute(
                "INSERT INTO pagos "
                "(factura_id, monto, fecha_pago, metodo, numero_cheque, banco_emisor, fecha_cheque, estado_cheque, notas) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    factura_id,
                    float(datos["monto"]),
                    datos["fecha_pago"],
                    datos["metodo"],
                    numero_cheque,
                    banco_emisor,
                    fecha_cheque,
                    estado_cheque,
                    datos["notas"],
                ),
            )
            pago_id = db.execute("SELECT last_insert_rowid()").fetchone()[0]

            if datos["metodo"] == "Cheque":
                db.execute(
                    "INSERT INTO pago_estado_historial "
                    "(pago_id, estado_anterior, estado_nuevo, usuario_id) "
                    "VALUES (?, ?, ?, ?)",
                    (pago_id, None, estado_cheque, session.get("usuario_id")),
                )

            db.commit()
        except Exception:
            db.rollback()
            raise

        flash("Pago registrado.", "success")
        return redirect(url_for("factura_detalle", factura_id=factura_id))

    datos = {
        "metodo": "Efectivo",
        "fecha_pago": date.today().isoformat(),
        "estado_cheque": ESTADOS_CHEQUE[0],
    }
    return render_pago_form(factura, datos)


@app.route("/cheques")
@login_required
def cheques():
    estado = request.args.get("estado", "").strip()
    buscar = request.args.get("q", "").strip()

    datos = paginar(
        obtener_cheques(estado=estado, buscar=buscar),
        pagina=request.args.get("pagina", 1),
    )

    return render_template(
        "cheques.html",
        datos=datos,
        estados=ESTADOS_CHEQUE,
        estado=estado,
        buscar=buscar,
    )


@app.route("/pagos/<int:pago_id>/historial")
@login_required
def pago_historial(pago_id):
    fila = get_db().execute(
        "SELECT p.*, f.numero_factura, pr.nombre AS proveedor_nombre "
        "FROM pagos p "
        "JOIN facturas f ON f.id = p.factura_id "
        "JOIN proveedores pr ON pr.id = f.proveedor_id "
        "WHERE p.id = ? AND p.metodo = 'Cheque'",
        (pago_id,),
    ).fetchone()
    if fila is None:
        abort(404)

    return render_template(
        "cheque_historial.html",
        pago=dict(fila),
        historial=obtener_historial_pago(pago_id),
        estados=ESTADOS_CHEQUE,
    )


@app.route("/pagos/<int:pago_id>/estado", methods=["POST"])
@role_required("administrador", "contador")
def pago_cambiar_estado(pago_id):
    validar_csrf()
    estado = request.form.get("estado_cheque", "")

    if estado not in ESTADOS_CHEQUE:
        flash("El estado del cheque no es válido.", "danger")
        return redirect(url_for("cheques"))

    db = get_db()
    db.execute("BEGIN IMMEDIATE")
    try:
        pago = db.execute(
            "SELECT estado_cheque FROM pagos WHERE id = ? AND metodo = 'Cheque'",
            (pago_id,),
        ).fetchone()

        if pago is None:
            db.rollback()
            abort(404)

        anterior = pago["estado_cheque"]

        if anterior == estado:
            db.rollback()
            flash("El cheque ya está en ese estado.", "warning")
        else:
            db.execute(
                "UPDATE pagos SET estado_cheque = ? WHERE id = ?", (estado, pago_id)
            )
            db.execute(
                "INSERT INTO pago_estado_historial "
                "(pago_id, estado_anterior, estado_nuevo, usuario_id) "
                "VALUES (?, ?, ?, ?)",
                (pago_id, anterior, estado, session.get("usuario_id")),
            )
            db.commit()
            flash("Estado del cheque actualizado.", "success")
    except Exception:
        db.rollback()
        raise

    if request.form.get("origen") == "historial":
        return redirect(url_for("pago_historial", pago_id=pago_id))
    return redirect(url_for("cheques"))


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


@app.route("/exportar")
@login_required
def exportar():
    return render_template(
        "exportar.html", estados=ESTADOS, proveedores=obtener_proveedores()
    )


@app.route("/exportar/facturas.csv")
@login_required
def exportar_facturas():
    estado = request.args.get("estado", "").strip()
    proveedor_id = request.args.get("proveedor_id", "").strip()
    buscar = request.args.get("q", "").strip()

    facturas = obtener_facturas(
        estado=estado, proveedor_id=proveedor_id, buscar=buscar
    )

    filas = [
        [
            factura["numero_factura"],
            factura["proveedor_nombre"],
            factura["concepto"],
            numero_csv(factura["monto_total"]),
            numero_csv(factura["total_pagado"]),
            numero_csv(factura["saldo"]),
            factura["estado"],
            factura["fecha_emision"],
            factura["fecha_vencimiento"],
        ]
        for factura in facturas
    ]

    encabezados = [
        "Numero factura",
        "Proveedor",
        "Concepto",
        "Monto total",
        "Pagado",
        "Saldo",
        "Estado",
        "Fecha emision",
        "Fecha vencimiento",
    ]

    return responder_csv("facturas.csv", encabezados, filas)


@app.route("/exportar/pagos.csv")
@login_required
def exportar_pagos():
    proveedor_id = request.args.get("proveedor_id", "").strip()
    buscar = request.args.get("q", "").strip()
    pagos = obtener_pagos_exportar(proveedor_id=proveedor_id, buscar=buscar)

    filas = [
        [
            pago["fecha_pago"],
            pago["numero_factura"],
            pago["proveedor_nombre"],
            pago["metodo"],
            numero_csv(pago["monto"]),
            numero_csv(pago["monto_efectivo"]),
            pago["numero_cheque"] or "",
            pago["banco_emisor"] or "",
            pago["fecha_cheque"] or "",
            pago["estado_cheque"] or "",
            pago["notas"] or "",
        ]
        for pago in pagos
    ]

    encabezados = [
        "Fecha pago",
        "Numero factura",
        "Proveedor",
        "Metodo",
        "Monto",
        "Afecta saldo",
        "Numero cheque",
        "Banco emisor",
        "Fecha cheque",
        "Estado cheque",
        "Notas",
    ]

    return responder_csv("pagos.csv", encabezados, filas)


if __name__ == "__main__":
    app.run(host="127.0.0.1", port=5000, debug=True)
