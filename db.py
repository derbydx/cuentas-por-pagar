import sqlite3

from flask import current_app, g, has_app_context

NOMBRE_BASE_DATOS = "cuentas_por_pagar.db"

ESQUEMA = """
CREATE TABLE IF NOT EXISTS usuarios (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    username TEXT NOT NULL UNIQUE,
    password_hash TEXT NOT NULL,
    rol TEXT NOT NULL CHECK (rol IN ('administrador', 'contador', 'consultor')),
    activo INTEGER NOT NULL DEFAULT 1 CHECK (activo IN (0, 1)),
    creado_en TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS proveedores (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    nombre TEXT NOT NULL,
    telefono TEXT,
    email TEXT,
    notas TEXT,
    creado_en TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS facturas (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    proveedor_id INTEGER NOT NULL REFERENCES proveedores(id) ON DELETE RESTRICT,
    numero_factura TEXT NOT NULL UNIQUE,
    concepto TEXT NOT NULL,
    monto_total REAL NOT NULL CHECK (monto_total > 0),
    fecha_emision TEXT NOT NULL,
    fecha_vencimiento TEXT NOT NULL,
    creado_en TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS pagos (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    factura_id INTEGER NOT NULL REFERENCES facturas(id) ON DELETE CASCADE,
    monto REAL NOT NULL CHECK (monto > 0),
    fecha_pago TEXT NOT NULL,
    metodo TEXT NOT NULL CHECK (metodo IN ('Efectivo', 'Transferencia', 'Cheque', 'Otro')),
    numero_cheque TEXT,
    banco_emisor TEXT,
    fecha_cheque TEXT,
    estado_cheque TEXT CHECK (
        estado_cheque IS NULL
        OR estado_cheque IN (
            'Emitido / En cartera',
            'Entregado',
            'Cobrado / Compensado',
            'Devuelto / Rechazado'
        )
    ),
    notas TEXT,
    creado_en TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CHECK (
        metodo != 'Cheque' OR (
            numero_cheque IS NOT NULL AND numero_cheque != ''
            AND banco_emisor IS NOT NULL AND banco_emisor != ''
            AND fecha_cheque IS NOT NULL AND fecha_cheque != ''
            AND estado_cheque IS NOT NULL
        )
    )
);

CREATE TABLE IF NOT EXISTS pago_estado_historial (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    pago_id INTEGER NOT NULL REFERENCES pagos(id) ON DELETE CASCADE,
    estado_anterior TEXT,
    estado_nuevo TEXT NOT NULL,
    fecha_cambio TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    usuario_id INTEGER REFERENCES usuarios(id) ON DELETE SET NULL
);

CREATE INDEX IF NOT EXISTS idx_facturas_proveedor ON facturas(proveedor_id);
CREATE INDEX IF NOT EXISTS idx_facturas_vencimiento ON facturas(fecha_vencimiento);
CREATE INDEX IF NOT EXISTS idx_pagos_factura ON pagos(factura_id);
CREATE INDEX IF NOT EXISTS idx_pagos_estado_cheque ON pagos(estado_cheque);
CREATE INDEX IF NOT EXISTS idx_historial_pago ON pago_estado_historial(pago_id);

CREATE VIEW IF NOT EXISTS v_pagos_efectivos AS
SELECT
    p.id,
    p.factura_id,
    p.monto,
    p.fecha_pago,
    p.metodo,
    p.numero_cheque,
    p.banco_emisor,
    p.fecha_cheque,
    p.estado_cheque,
    p.notas,
    p.creado_en,
    CASE
        WHEN p.metodo = 'Cheque' THEN
            CASE
                WHEN p.estado_cheque = 'Cobrado / Compensado' THEN p.monto
                ELSE 0
            END
        ELSE p.monto
    END AS monto_efectivo
FROM pagos p;

CREATE VIEW IF NOT EXISTS v_facturas_saldo AS
SELECT
    f.id,
    f.proveedor_id,
    f.numero_factura,
    f.concepto,
    f.monto_total,
    f.fecha_emision,
    f.fecha_vencimiento,
    f.creado_en,
    pr.nombre AS proveedor_nombre,
    COALESCE(SUM(pg.monto_efectivo), 0) AS total_pagado,
    f.monto_total - COALESCE(SUM(pg.monto_efectivo), 0) AS saldo
FROM facturas f
JOIN proveedores pr ON pr.id = f.proveedor_id
LEFT JOIN v_pagos_efectivos pg ON pg.factura_id = f.id
GROUP BY f.id;
"""


def ruta_base_datos():
    if has_app_context():
        return current_app.config.get("BASE_DATOS", NOMBRE_BASE_DATOS)
    return NOMBRE_BASE_DATOS


def get_db():
    if "db" not in g:
        db = sqlite3.connect(ruta_base_datos())
        db.row_factory = sqlite3.Row
        db.execute("PRAGMA foreign_keys = ON")
        g.db = db
    return g.db


def close_db(error=None):
    db = g.pop("db", None)
    if db is not None:
        db.close()


def init_db():
    db = sqlite3.connect(ruta_base_datos())
    db.execute("PRAGMA foreign_keys = ON")
    db.executescript(ESQUEMA)
    db.close()
