import os
import sys
from datetime import date, timedelta

from werkzeug.security import check_password_hash

from app import app
from db import get_db

PROVEEDORES = (
    ("Distribuidora Norte", "809-555-0101", "ventas@norte.example.com", "Proveedor de mercadería"),
    ("Servicios del Este", "809-555-0102", "contacto@este.example.com", "Servicios generales"),
    ("Papelería Central", "809-555-0103", "", "Material de oficina"),
)

FACTURAS = (
    ("F-2026-001", "Compra de mercadería", 15000.00, 20, 12),
    ("F-2026-002", "Servicio de limpieza", 8500.00, 10, 5),
    ("F-2026-003", "Material de oficina", 3200.00, 15, -3),
    ("F-2026-004", "Mantenimiento de equipos", 4750.50, 5, 25),
    ("F-2026-005", "Combustible", 6000.00, 8, -10),
    ("F-2026-006", "Impresión de formularios", 2100.00, 12, 30),
)

PAGOS = (
    (1, 3750.00, "Efectivo", None, None, None, 0, "Anticipo en efectivo"),
    (2, 8500.00, "Cheque", "CH-1001", "Banco Popular", "Emitido / En cartera", 10, "Cheque pendiente"),
    (3, 1500.00, "Transferencia", None, None, None, 0, "Abono parcial"),
    (4, 3200.00, "Cheque", "CH-1002", "Banco Reservas", "Devuelto / Rechazado", -2, "Cheque devuelto"),
    (5, 6000.00, "Transferencia", None, None, None, 0, "Factura saldada"),
    (6, 2100.00, "Cheque", "CH-1003", "Banco Popular", "Cobrado / Compensado", 3, "Cheque compensado"),
)


def main():
    permitir_datos = "--permitir-datos" in sys.argv[1:]
    password = os.environ.get("ADMIN_PASSWORD")
    if not password:
        print("Define ADMIN_PASSWORD con la contraseña del administrador antes de sembrar datos de ejemplo.")
        return 1

    with app.app_context():
        db = get_db()
        admin = db.execute(
            "SELECT id, password_hash FROM usuarios WHERE username = 'admin' AND rol = 'administrador'"
        ).fetchone()

        if not admin or not check_password_hash(admin["password_hash"], password):
            print("ADMIN_PASSWORD no coincide con el usuario administrador. No se sembraron datos.")
            return 1

        hay_datos = db.execute("SELECT 1 FROM proveedores LIMIT 1").fetchone() or db.execute(
            "SELECT 1 FROM facturas LIMIT 1"
        ).fetchone()
        if hay_datos and not permitir_datos:
            print(
                "La base ya tiene proveedores o facturas. "
                "Usa --permitir-datos para agregar el ejemplo sin borrar nada."
            )
            return 1

        nombres_demo = [nombre for nombre, _, _, _ in PROVEEDORES]
        marcadores = ",".join("?" for _ in nombres_demo)
        if db.execute(
            f"SELECT 1 FROM proveedores WHERE nombre IN ({marcadores}) LIMIT 1",
            nombres_demo,
        ).fetchone():
            print("Los datos de ejemplo ya están sembrados. No se agregaron duplicados.")
            return 1

        numeros_demo = [numero for numero, _, _, _, _ in FACTURAS]
        marcadores = ",".join("?" for _ in numeros_demo)
        if db.execute(
            f"SELECT 1 FROM facturas WHERE numero_factura IN ({marcadores}) LIMIT 1",
            numeros_demo,
        ).fetchone():
            print("Ya existe una factura de ejemplo. No se agregaron duplicados.")
            return 1

        hoy = date.today()
        proveedor_ids = []

        for nombre, telefono, email, notas in PROVEEDORES:
            cursor = db.execute(
                "INSERT INTO proveedores (nombre, telefono, email, notas) VALUES (?, ?, ?, ?)",
                (nombre, telefono, email, notas),
            )
            proveedor_ids.append(cursor.lastrowid)

        factura_ids = []

        for indice, (numero, concepto, monto, dias_emision, dias_vencimiento) in enumerate(FACTURAS):
            proveedor_id = proveedor_ids[indice % len(proveedor_ids)]
            cursor = db.execute(
                "INSERT INTO facturas "
                "(proveedor_id, numero_factura, concepto, monto_total, fecha_emision, fecha_vencimiento) "
                "VALUES (?, ?, ?, ?, ?, ?)",
                (
                    proveedor_id,
                    numero,
                    concepto,
                    monto,
                    (hoy - timedelta(days=dias_emision)).isoformat(),
                    (hoy + timedelta(days=dias_vencimiento)).isoformat(),
                ),
            )
            factura_ids.append(cursor.lastrowid)

        for factura_id, monto, metodo, numero_cheque, banco, estado, dias, notas in PAGOS:
            fecha_pago = (hoy + timedelta(days=dias)).isoformat()
            cursor = db.execute(
                "INSERT INTO pagos "
                "(factura_id, monto, fecha_pago, metodo, numero_cheque, banco_emisor, fecha_cheque, estado_cheque, notas) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    factura_ids[factura_id - 1],
                    monto,
                    fecha_pago,
                    metodo,
                    numero_cheque,
                    banco,
                    fecha_pago if numero_cheque else None,
                    estado,
                    notas,
                ),
            )

            if metodo == "Cheque":
                db.execute(
                    "INSERT INTO pago_estado_historial "
                    "(pago_id, estado_anterior, estado_nuevo, usuario_id) VALUES (?, ?, ?, ?)",
                    (cursor.lastrowid, None, estado, admin["id"]),
                )

        db.commit()

        print("Datos de ejemplo sembrados:")
        print(f"  {len(PROVEEDORES)} proveedores")
        print(f"  {len(FACTURAS)} facturas")
        print(f"  {len(PAGOS)} pagos, incluidos 3 cheques en estados distintos")
        print("Estados de factura resultantes: Pagada, Parcial, Vencida y Pendiente")

    return 0


if __name__ == "__main__":
    sys.exit(main())
