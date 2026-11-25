# Cuentas por pagar

Aplicación web local hecha con Flask, SQLite y plantillas Jinja2. Sin Node, sin ORM y sin dependencias adicionales.

## Ejecutar

Requiere Python 3.9 o superior.

```powershell
py -3 -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
python app.py
```

Luego abre http://127.0.0.1:5000

En Linux o macOS usa `python3` en lugar de `py -3`.

La base `cuentas_por_pagar.db` se crea automáticamente en el primer arranque. El primer usuario es `admin`. Si no defines `ADMIN_PASSWORD`, la contraseña se imprime en consola una sola vez.

## Configuración

Variables de entorno opcionales:

- `SECRET_KEY`: clave para firmar la sesión. En producción debe ser larga y aleatoria.
- `ADMIN_PASSWORD`: contraseña del primer usuario administrador.
- `BASE_DATOS`: ruta alternativa del archivo SQLite. Por defecto usa `cuentas_por_pagar.db` en esta carpeta.

Ejemplo en PowerShell:

```powershell
$env:SECRET_KEY = "valor-largo-y-aleatorio"
$env:ADMIN_PASSWORD = "MiContraseñaSegura"
python app.py
```

## Funciones

- Proveedores con alta, edición, búsqueda y paginación.
- Facturas por pagar con alta, edición, filtros, detalle y saldo calculado.
- Pagos en efectivo, transferencia, cheque u otro, con validación contra el saldo.
- Cheques emitidos con estados `Emitido / En cartera`, `Entregado`, `Cobrado / Compensado` y `Devuelto / Rechazado`.
- Historial de cambios de estado de cada cheque, con usuario y fecha.
- Panel con total por pagar, total vencido, pagado del mes y cheques pendientes.
- Exportación de facturas y pagos a CSV con separador `;`, BOM UTF-8 y escape de fórmulas.
- Usuarios con roles `administrador`, `contador` y `consultor`.
- Reportes de solo lectura con vista web y CSV.

## Reportes

Menú `Reportes`, accesible para cualquier usuario con sesión:

- Antigüedad de saldos: corriente, 1 a 30, 31 a 60, 61 a 90 y más de 90 días, por proveedor.
- Pagos por mes y método: efectivo, transferencia, cheque compensado y otro.
- Facturas por vencer y vencidas: con horizonte de 7 a 90 días, proveedor y estado.
- Reporte de cheques: por estado, banco y rango de fechas.
- Auditoría de cheques: cambios de estado con usuario y fecha.
- Conciliación mensual: emitido, pagado, variación y saldo al cierre.
- Top proveedores: ranking por saldo, con límite de 5, 10 o 20.

Los presets de fecha son mes actual, últimos 3 meses, trimestre actual, trimestre anterior, últimos 6 meses, últimos 12 meses y personalizado. En reportes de saldo, la fecha funciona como corte. Botón `Descargar CSV` conserva los filtros aplicados.

## Reglas de saldo

Un pago en efectivo, transferencia u otro descuenta la deuda al registrarse. Un pago con cheque solo descuenta cuando su estado es `Cobrado / Compensado`. Si un cheque compensado se marca como devuelto, la deuda se regenera.

Estados de factura: `Pendiente`, `Parcial`, `Pagada` y `Vencida`. La prioridad es `Pagada` > `Vencida` > `Parcial` > `Pendiente`.

## Permisos

- Administrador: crea, edita, borra y gestiona usuarios.
- Contador: crea y edita. No borra ni gestiona usuarios.
- Consultor: solo lee y exporta.

## Datos de ejemplo

El script agrega 3 proveedores, 6 facturas, 6 pagos y cheques en tres estados. Solo funciona si `ADMIN_PASSWORD` coincide con el administrador. Si la base ya tiene datos, agrega el ejemplo sin borrar nada usando `--permitir-datos`. Si los datos de ejemplo ya existen, se detiene para no duplicarlos.

```powershell
$env:ADMIN_PASSWORD = "TuContraseñaSegura"
.\.venv\Scripts\python.exe sembrar_demo.py --permitir-datos
```

Sin esa bandera, el script se detiene cuando la base no está vacía.

## Pruebas

```powershell
.\.venv\Scripts\python.exe -m unittest -v test_app.py
```

Actualmente hay 54 pruebas. Cubren login, CSRF, roles, altas y ediciones, borrados protegidos, reglas de saldo, cheques, historial, panel, paginación, JS externo, CSV y los 7 reportes con sus filtros.

## Estructura

- `app.py`: configuración y rutas.
- `db.py`: esquema SQLite, conexiones y vistas.
- `auth.py`: login, roles y CSRF.
- `servicios.py`: reglas de negocio, filtros, métricas, agregaciones de reportes, CSV y paginación.
- `reportes.py`: blueprint con las rutas de los 7 reportes y sus CSV.
- `sembrar_demo.py`: datos de ejemplo.
- `test_app.py`: pruebas automáticas.
- `templates/`: plantillas Jinja2 con Pico.css por CDN y macro de paginación compartida.
- `templates/reportes/`: base, filtros compartidos y una plantilla por reporte.
- `static/app.js`: único script, campos de cheque y presets de fecha.
- `NOTAS_IMPORTANTES.md`: arranque, credenciales y solución de problemas.

## Estado del proyecto

Plan completo de 13 pasos terminado. Los cambios de vista y los reportes están en la rama `prueba`. Pendiente de merge a `main` cuando lo autorices.
