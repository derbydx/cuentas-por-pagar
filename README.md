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

Actualmente hay 30 pruebas. Cubren login, CSRF, roles, altas y ediciones, borrados protegidos, reglas de saldo, cheques, historial, panel y CSV.

## Estructura

- `app.py`: configuración y rutas.
- `db.py`: esquema SQLite, conexiones y vistas.
- `auth.py`: login, roles y CSRF.
- `servicios.py`: reglas de negocio, filtros, métricas y paginación.
- `sembrar_demo.py`: datos de ejemplo.
- `test_app.py`: pruebas automáticas.
- `templates/`: plantillas Jinja2 con Pico.css por CDN.
- `NOTAS_IMPORTANTES.md`: arranque, credenciales y solución de problemas.

## Estado del proyecto

Plan completo de 13 pasos terminado. Sin commit ni push.
