import os
import re
import tempfile
import unittest
from datetime import date, timedelta

DIRECTORIO_TEMP = tempfile.mkdtemp(prefix="cuentas_por_pagar_test_")
os.environ["BASE_DATOS"] = os.path.join(DIRECTORIO_TEMP, "test.db")
os.environ["ADMIN_PASSWORD"] = "ClavePrueba123"

from werkzeug.security import generate_password_hash

from app import app
from db import get_db

HOY = date.today().isoformat()
MANANA = (date.today() + timedelta(days=10)).isoformat()
AYER = (date.today() - timedelta(days=10)).isoformat()


class PruebasBase(unittest.TestCase):
    def setUp(self):
        self.cliente = app.test_client()

        with app.app_context():
            db = get_db()
            db.execute("DELETE FROM pago_estado_historial")
            db.execute("DELETE FROM pagos")
            db.execute("DELETE FROM facturas")
            db.execute("DELETE FROM proveedores")
            db.execute("DELETE FROM usuarios WHERE username != 'admin'")
            db.commit()

        self.entrar()

    def token(self, respuesta):
        encontrado = re.search(rb'name="csrf_token" value="([^"]+)"', respuesta.data)
        self.assertIsNotNone(encontrado, "No se encontró token CSRF")
        return encontrado.group(1).decode()

    def entrar(self, usuario="admin", password="ClavePrueba123"):
        token = self.token(self.cliente.get("/login"))
        return self.cliente.post(
            "/login",
            data={"csrf_token": token, "username": usuario, "password": password},
        )

    def salir(self):
        token = self.token(self.cliente.get("/"))
        self.cliente.post("/logout", data={"csrf_token": token})

    def crear_usuario(self, username, rol, password="ClaveUsuario"):
        with app.app_context():
            db = get_db()
            db.execute(
                "INSERT INTO usuarios (username, password_hash, rol) VALUES (?, ?, ?)",
                (username, generate_password_hash(password), rol),
            )
            db.commit()

    def crear_proveedor(self, nombre="Proveedor Prueba"):
        with app.app_context():
            db = get_db()
            db.execute("INSERT INTO proveedores (nombre) VALUES (?)", (nombre,))
            db.commit()
            return db.execute("SELECT id FROM proveedores WHERE nombre = ?", (nombre,)).fetchone()[0]

    def crear_factura(
        self, numero="F-001", monto=1000, proveedor_id=None, vencimiento=MANANA
    ):
        if proveedor_id is None:
            proveedor_id = self.crear_proveedor()

        with app.app_context():
            db = get_db()
            db.execute(
                "INSERT INTO facturas "
                "(proveedor_id, numero_factura, concepto, monto_total, fecha_emision, fecha_vencimiento) "
                "VALUES (?, ?, ?, ?, ?, ?)",
                (proveedor_id, numero, "Concepto de prueba", monto, HOY, vencimiento),
            )
            db.commit()
            return db.execute("SELECT id FROM facturas WHERE numero_factura = ?", (numero,)).fetchone()[0]

    def saldo(self, factura_id):
        with app.app_context():
            fila = get_db().execute(
                "SELECT saldo FROM v_facturas_saldo WHERE id = ?", (factura_id,)
            ).fetchone()
            return round(float(fila["saldo"]), 2)

    def estado(self, factura_id):
        with app.app_context():
            fila = get_db().execute(
                "SELECT * FROM v_facturas_saldo WHERE id = ?", (factura_id,)
            ).fetchone()
            from servicios import estado_factura

            return estado_factura(fila)

    def pagar(
        self,
        factura_id,
        monto,
        metodo="Efectivo",
        estado_cheque=None,
        numero_cheque="CH-1",
        banco="Banco Prueba",
    ):
        datos = {
            "csrf_token": self.token(
                self.cliente.get(f"/facturas/{factura_id}/pagos/nuevo")
            ),
            "monto": str(monto),
            "fecha_pago": HOY,
            "metodo": metodo,
            "notas": "Pago de prueba",
        }

        if metodo == "Cheque":
            datos.update(
                {
                    "numero_cheque": numero_cheque,
                    "banco_emisor": banco,
                    "fecha_cheque": HOY,
                    "estado_cheque": estado_cheque,
                }
            )

        return self.cliente.post(
            f"/facturas/{factura_id}/pagos/nuevo", data=datos
        )

    def historial(self, pago_id):
        with app.app_context():
            return [
                tuple(fila)
                for fila in get_db().execute(
                    "SELECT estado_anterior, estado_nuevo FROM pago_estado_historial "
                    "WHERE pago_id = ? ORDER BY id",
                    (pago_id,),
                )
            ]


class PruebasAutenticacion(PruebasBase):
    def test_raiz_pide_login(self):
        cliente = app.test_client()
        respuesta = cliente.get("/")
        self.assertEqual(respuesta.status_code, 302)
        self.assertIn("/login", respuesta.headers["Location"])

    def test_csrf_en_login(self):
        cliente = app.test_client()
        respuesta = cliente.post(
            "/login", data={"username": "admin", "password": "ClavePrueba123"}
        )
        self.assertEqual(respuesta.status_code, 400)

    def test_login_incorrecto(self):
        cliente = app.test_client()
        token = self.token(cliente.get("/login"))
        respuesta = cliente.post(
            "/login",
            data={"csrf_token": token, "username": "admin", "password": "mala"},
        )
        self.assertIn(b"incorrectos", respuesta.data)

    def test_login_y_logout(self):
        self.assertEqual(self.cliente.get("/").status_code, 200)
        self.salir()
        self.assertEqual(self.cliente.get("/").status_code, 302)


class PruebasRoles(PruebasBase):
    def setUp(self):
        super().setUp()
        self.crear_usuario("contador1", "contador", "ClaveContador")
        self.crear_usuario("lector1", "consultor", "ClaveLector")

    def test_administrador_ve_usuarios(self):
        self.assertEqual(self.cliente.get("/usuarios").status_code, 200)

    def test_contador_no_ve_usuarios(self):
        self.salir()
        self.entrar("contador1", "ClaveContador")
        self.assertEqual(self.cliente.get("/usuarios").status_code, 403)

    def test_consultor_no_crea(self):
        self.salir()
        self.entrar("lector1", "ClaveLector")
        self.assertEqual(self.cliente.get("/facturas/nuevo").status_code, 403)
        self.assertEqual(self.cliente.get("/proveedores/nuevo").status_code, 403)

    def test_consultor_no_cambia_cheque(self):
        self.salir()
        self.entrar("lector1", "ClaveLector")
        self.assertEqual(
            self.cliente.post("/pagos/1/estado", data={"csrf_token": "x"}).status_code,
            403,
        )

    def test_botones_por_rol(self):
        self.crear_proveedor()
        self.salir()
        self.entrar("lector1", "ClaveLector")
        respuesta = self.cliente.get("/proveedores").data
        self.assertNotIn(b"Editar", respuesta)
        self.assertNotIn(b"Eliminar", respuesta)


class PruebasProveedoresYUsuarios(PruebasBase):
    def test_alta_edicion_y_csrf(self):
        self.assertEqual(
            self.cliente.post("/proveedores/nuevo", data={"nombre": "X"}).status_code,
            400,
        )

        token = self.token(self.cliente.get("/proveedores/nuevo"))
        respuesta = self.cliente.post(
            "/proveedores/nuevo",
            data={"csrf_token": token, "nombre": "Proveedor Uno", "email": "uno@example.com"},
        )
        self.assertEqual(respuesta.status_code, 302)
        self.assertIn(b"Proveedor Uno", self.cliente.get("/proveedores").data)

        with app.app_context():
            proveedor_id = get_db().execute(
                "SELECT id FROM proveedores WHERE nombre = 'Proveedor Uno'"
            ).fetchone()[0]

        token = self.token(self.cliente.get(f"/proveedores/{proveedor_id}/editar"))
        self.cliente.post(
            f"/proveedores/{proveedor_id}/editar",
            data={"csrf_token": token, "nombre": "Proveedor Editado", "email": ""},
        )
        self.assertIn(b"Proveedor Editado", self.cliente.get("/proveedores").data)

    def test_email_invalido(self):
        token = self.token(self.cliente.get("/proveedores/nuevo"))
        respuesta = self.cliente.post(
            "/proveedores/nuevo",
            data={"csrf_token": token, "nombre": "Sin Email", "email": "no-valido"},
        )
        self.assertIn(b"no parece", respuesta.data)

    def test_borrado_protegido(self):
        proveedor_id = self.crear_proveedor("Proveedor Sin Facturas")
        token = self.token(self.cliente.get("/proveedores"))
        respuesta = self.cliente.post(
            f"/proveedores/{proveedor_id}/eliminar",
            data={"csrf_token": token},
            follow_redirects=True,
        )
        self.assertIn(b"Proveedor eliminado", respuesta.data)

        con_factura = self.crear_proveedor("Proveedor Con Factura")
        self.crear_factura("F-BORRAR", 100, con_factura)
        token = self.token(self.cliente.get("/proveedores"))
        respuesta = self.cliente.post(
            f"/proveedores/{con_factura}/eliminar",
            data={"csrf_token": token},
            follow_redirects=True,
        )
        self.assertIn(b"tiene facturas asociadas", respuesta.data)

    def test_usuario_duplicado_y_password_corta(self):
        token = self.token(self.cliente.get("/usuarios/nuevo"))
        datos = {
            "csrf_token": token,
            "username": "admin",
            "password": "Clave12345",
            "rol": "contador",
            "activo": "1",
        }
        self.assertIn(b"ya existe", self.cliente.post("/usuarios/nuevo", data=datos).data)

        datos["username"] = "nuevo"
        datos["password"] = "123"
        self.assertIn(b"al menos 8", self.cliente.post("/usuarios/nuevo", data=datos).data)

    def test_ultimo_administrador_protegido(self):
        with app.app_context():
            admin_id = get_db().execute(
                "SELECT id FROM usuarios WHERE username = 'admin'"
            ).fetchone()[0]

        token = self.token(self.cliente.get(f"/usuarios/{admin_id}/editar"))
        respuesta = self.cliente.post(
            f"/usuarios/{admin_id}/editar",
            data={
                "csrf_token": token,
                "username": "admin",
                "password": "",
                "rol": "contador",
                "activo": "1",
            },
        )
        self.assertIn("último administrador", respuesta.data.decode("utf-8"))

    def test_paginacion_compartida(self):
        for numero in range(21):
            self.crear_proveedor(f"Proveedor Paginación {numero}")

        respuesta = self.cliente.get("/proveedores").data
        self.assertIn("Página 1 de 2".encode("utf-8"), respuesta)
        self.assertIn(b"pagina=2", respuesta)
        self.assertIn(b"(21 proveedores)", respuesta)


class PruebasFacturas(PruebasBase):
    def validaciones(self):
        with app.app_context():
            proveedor_id = get_db().execute("SELECT id FROM proveedores LIMIT 1").fetchone()[0]
        token = self.token(self.cliente.get("/facturas/nuevo"))
        base = {
            "csrf_token": token,
            "proveedor_id": proveedor_id,
            "numero_factura": "F-NUEVA",
            "concepto": "Concepto",
            "monto_total": "500",
            "fecha_emision": HOY,
            "fecha_vencimiento": MANANA,
        }
        return base

    def test_alta_y_validaciones(self):
        proveedor_id = self.crear_proveedor()
        base = self.validaciones()
        respuesta = self.cliente.post("/facturas/nuevo", data=base)
        self.assertEqual(respuesta.status_code, 302)
        self.assertIn(b"F-NUEVA", self.cliente.get("/facturas").data)

        base = self.validaciones()
        base["monto_total"] = "0"
        self.assertIn(b"mayor que cero", self.cliente.post("/facturas/nuevo", data=base).data)

        base = self.validaciones()
        base["fecha_emision"] = MANANA
        base["fecha_vencimiento"] = HOY
        self.assertIn(b"anterior a la", self.cliente.post("/facturas/nuevo", data=base).data)

        base = self.validaciones()
        self.assertIn(b"ya existe", self.cliente.post("/facturas/nuevo", data=base).data)

    def test_filtros_y_detalle(self):
        proveedor_id = self.crear_proveedor("Proveedor Filtros")
        factura_id = self.crear_factura("F-FILTRO", 750, proveedor_id)

        self.assertIn(b"F-FILTRO", self.cliente.get("/facturas?q=F-FILTRO").data)
        self.assertIn(
            b"F-FILTRO",
            self.cliente.get(f"/facturas?proveedor_id={proveedor_id}").data,
        )
        self.assertIn(b"F-FILTRO", self.cliente.get("/facturas?estado=Pendiente").data)

        detalle = self.cliente.get(f"/facturas/{factura_id}").data
        self.assertIn(b"RD$ 750.00", detalle)
        self.assertIn(b"/pagos/nuevo", detalle)

    def test_js_externo_en_pago(self):
        factura_id = self.crear_factura("F-JS", 100)
        respuesta = self.cliente.get(f"/facturas/{factura_id}/pagos/nuevo").data
        self.assertIn(b"/static/app.js", respuesta)
        self.assertNotIn(b"<script>", respuesta)

        archivo_js = self.cliente.get("/static/app.js")
        self.assertEqual(archivo_js.status_code, 200)
        archivo_js.close()

    def test_estados_de_factura(self):
        pendiente = self.crear_factura("F-PENDIENTE", 1000)
        vencida = self.crear_factura("F-VENCIDA", 1000, vencimiento=AYER)
        self.pagar(pendiente, 200)
        self.pagar(vencida, 200)

        self.assertEqual(self.estado(pendiente), "Parcial")
        self.assertEqual(self.estado(vencida), "Vencida")

        self.pagar(pendiente, 800)
        self.assertEqual(self.estado(pendiente), "Pagada")

    def test_borrado_admin_y_contador(self):
        factura_id = self.crear_factura("F-BORRAR", 100)

        token = self.token(self.cliente.get("/facturas"))
        respuesta = self.cliente.post(
            f"/facturas/{factura_id}/eliminar", data={"csrf_token": token}
        )
        self.assertEqual(respuesta.status_code, 302)
        self.assertNotIn(b"F-BORRAR", self.cliente.get("/facturas").data)

        factura_id = self.crear_factura("F-BORRAR2", 100)
        self.salir()
        self.crear_usuario("contador2", "contador", "ClaveContador")
        self.entrar("contador2", "ClaveContador")
        token = self.token(self.cliente.get("/facturas"))
        respuesta = self.cliente.post(
            f"/facturas/{factura_id}/eliminar", data={"csrf_token": token}
        )
        self.assertEqual(respuesta.status_code, 403)


class PruebasPagosYCheques(PruebasBase):
    def test_pago_efectivo_descuenta(self):
        factura_id = self.crear_factura("F-EFECTIVO", 1000)
        respuesta = self.pagar(factura_id, 250)
        self.assertEqual(respuesta.status_code, 302)
        self.assertEqual(self.saldo(factura_id), 750.0)

    def test_pago_no_supera_saldo(self):
        factura_id = self.crear_factura("F-EXCESO", 100)
        respuesta = self.pagar(factura_id, 200)
        self.assertIn(b"superar el saldo", respuesta.data)
        self.assertEqual(self.saldo(factura_id), 100.0)

    def test_cheque_sin_datos(self):
        factura_id = self.crear_factura("F-CHEQUE-DATOS", 100)
        token = self.token(self.cliente.get(f"/facturas/{factura_id}/pagos/nuevo"))
        respuesta = self.cliente.post(
            f"/facturas/{factura_id}/pagos/nuevo",
            data={"csrf_token": token, "monto": "50", "fecha_pago": HOY, "metodo": "Cheque"},
        )
        self.assertIn(b"datos del cheque", respuesta.data)

    def test_cheque_solo_descuenta_al_compensarse(self):
        factura_id = self.crear_factura("F-CHEQUE", 1000)

        self.pagar(
            factura_id,
            400,
            metodo="Cheque",
            estado_cheque="Emitido / En cartera",
            numero_cheque="CH-400",
        )
        self.assertEqual(self.saldo(factura_id), 1000.0)

        self.pagar(
            factura_id,
            300,
            metodo="Cheque",
            estado_cheque="Entregado",
            numero_cheque="CH-401",
        )
        self.assertEqual(self.saldo(factura_id), 1000.0)

        with app.app_context():
            db = get_db()
            pago_id = db.execute(
                "SELECT id FROM pagos WHERE numero_cheque = 'CH-400'"
            ).fetchone()[0]
            db.execute(
                "UPDATE pagos SET estado_cheque = 'Cobrado / Compensado' WHERE id = ?",
                (pago_id,),
            )
            db.commit()

        self.assertEqual(self.saldo(factura_id), 600.0)

        token = self.token(self.cliente.get("/cheques"))
        self.cliente.post(
            f"/pagos/{pago_id}/estado",
            data={"csrf_token": token, "estado_cheque": "Devuelto / Rechazado"},
        )
        self.assertEqual(self.saldo(factura_id), 1000.0)

    def test_historial_de_cheque(self):
        factura_id = self.crear_factura("F-HISTORIAL", 1000)
        self.pagar(
            factura_id,
            500,
            metodo="Cheque",
            estado_cheque="Emitido / En cartera",
            numero_cheque="CH-500",
        )

        with app.app_context():
            pago_id = get_db().execute(
                "SELECT id FROM pagos WHERE numero_cheque = 'CH-500'"
            ).fetchone()[0]

        self.assertEqual(self.historial(pago_id), [(None, "Emitido / En cartera")])

        token = self.token(self.cliente.get(f"/pagos/{pago_id}/historial"))
        respuesta = self.cliente.post(
            f"/pagos/{pago_id}/estado",
            data={
                "csrf_token": token,
                "estado_cheque": "Cobrado / Compensado",
                "origen": "historial",
            },
        )
        self.assertEqual(respuesta.status_code, 302)
        self.assertEqual(
            self.historial(pago_id),
            [(None, "Emitido / En cartera"), ("Emitido / En cartera", "Cobrado / Compensado")],
        )

        self.assertIn(b"Cobrado / Compensado", self.cliente.get("/cheques").data)

    def test_cambio_estado_con_boton(self):
        factura_id = self.crear_factura("F-BOTON", 100)
        self.pagar(
            factura_id,
            50,
            metodo="Cheque",
            estado_cheque="Emitido / En cartera",
            numero_cheque="CH-BOTON",
        )

        respuesta = self.cliente.get("/cheques").data
        self.assertNotIn(b"onchange=", respuesta)
        self.assertIn(b">Cambiar</button>", respuesta)

    def test_cambio_estado_invalido(self):
        factura_id = self.crear_factura("F-ESTADO", 1000)
        self.pagar(
            factura_id,
            100,
            metodo="Cheque",
            estado_cheque="Emitido / En cartera",
            numero_cheque="CH-600",
        )

        with app.app_context():
            pago_id = get_db().execute(
                "SELECT id FROM pagos WHERE numero_cheque = 'CH-600'"
            ).fetchone()[0]

        token = self.token(self.cliente.get("/cheques"))
        respuesta = self.cliente.post(
            f"/pagos/{pago_id}/estado",
            data={"csrf_token": token, "estado_cheque": "Inventado"},
            follow_redirects=True,
        )
        self.assertIn(b"no es v", respuesta.data)
        self.assertEqual(len(self.historial(pago_id)), 1)

    def test_csrf_en_cambio_de_estado(self):
        respuesta = self.cliente.post(
            "/pagos/1/estado", data={"estado_cheque": "Entregado"}
        )
        self.assertEqual(respuesta.status_code, 400)

    def test_no_cheque_no_tiene_historial(self):
        factura_id = self.crear_factura("F-NO-CHEQUE", 100)
        self.pagar(factura_id, 10)

        with app.app_context():
            pago_id = get_db().execute("SELECT id FROM pagos LIMIT 1").fetchone()[0]

        self.assertEqual(self.cliente.get(f"/pagos/{pago_id}/historial").status_code, 404)


class PruebasExportacion(PruebasBase):
    def test_csv_facturas(self):
        factura_id = self.crear_factura("F-CSV", 1234.50)
        with app.app_context():
            proveedor_id = get_db().execute("SELECT id FROM proveedores LIMIT 1").fetchone()[0]

        token = self.token(self.cliente.get(f"/facturas/{factura_id}/editar"))
        respuesta = self.cliente.post(
            f"/facturas/{factura_id}/editar",
            data={
                "csrf_token": token,
                "proveedor_id": proveedor_id,
                "numero_factura": "F-CSV",
                "concepto": "=SUM(A1)",
                "monto_total": "1234.50",
                "fecha_emision": HOY,
                "fecha_vencimiento": MANANA,
            },
        )
        self.assertEqual(respuesta.status_code, 302)

        respuesta = self.cliente.get("/exportar/facturas.csv")
        contenido = respuesta.data.decode("utf-8-sig")
        self.assertTrue(respuesta.data.startswith(b"\xef\xbb\xbf"))
        self.assertIn("text/csv", respuesta.headers["Content-Type"])
        self.assertIn("'=SUM(A1)", contenido)
        self.assertIn("1234,50", contenido)
        self.assertIn("F-CSV", contenido)

    def test_csv_filtros_y_pagos(self):
        proveedor_id = self.crear_proveedor("Proveedor CSV Pagos")
        factura_id = self.crear_factura("F-CSV-2", 500, proveedor_id)
        self.pagar(
            factura_id,
            100,
            metodo="Cheque",
            estado_cheque="Cobrado / Compensado",
            numero_cheque="CH-CSV",
        )

        contenido = self.cliente.get(
            f"/exportar/facturas.csv?proveedor_id={proveedor_id}"
        ).data.decode("utf-8-sig")
        self.assertIn("F-CSV-2", contenido)

        vacio = self.cliente.get("/exportar/facturas.csv?estado=Vencida").data.decode("utf-8-sig")
        self.assertNotIn("F-CSV-2", vacio)

        pagos = self.cliente.get("/exportar/pagos.csv").data.decode("utf-8-sig")
        self.assertIn("CH-CSV", pagos)
        self.assertIn("100,00", pagos)

    def test_csv_requiere_login(self):
        self.salir()
        self.assertEqual(
            self.cliente.get("/exportar/facturas.csv").status_code, 302
        )


class PruebasPanel(PruebasBase):
    def test_menu_sin_enlaces_vacios(self):
        respuesta = self.cliente.get("/")
        self.assertNotIn(b'href="#"', respuesta.data)
        self.assertNotIn(b">Panel</a>", respuesta.data)
        self.assertIn(b"Cuentas por pagar</a>", respuesta.data)
        self.assertIn(b'aria-current="page"', respuesta.data)

    def test_tarjetas_y_tablas(self):
        self.crear_factura("F-PANEL", 500, vencimiento=AYER)
        respuesta = self.cliente.get("/")
        self.assertIn(b"Total por pagar", respuesta.data)
        self.assertIn(b"Total vencido", respuesta.data)
        self.assertIn(b"Pagado del mes", respuesta.data)
        self.assertIn(b"Cheques pendientes", respuesta.data)
        self.assertIn(b"F-PANEL", respuesta.data)
        self.assertIn(b"RD$ 500.00", respuesta.data)


if __name__ == "__main__":
    unittest.main(verbosity=2)
