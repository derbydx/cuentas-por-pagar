# Notas importantes

## Activar el entorno y correr el servidor

Desde esta carpeta, en PowerShell:

```powershell
.\.venv\Scripts\Activate.ps1
python app.py
```

Si el entorno virtual todavía no existe, créalo una sola vez:

```powershell
py -3 -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
```

Luego abre http://127.0.0.1:5000

## Problemas comunes

- `ModuleNotFoundError: No module named 'flask'`: el entorno virtual no está activado o Flask no se instaló. Ejecuta los comandos de arriba.
- La página no carga: revisa que haya un proceso `python app.py` corriendo. Puedes comprobar el puerto con:

```powershell
Get-NetTCPConnection -LocalPort 5000 -State Listen
```

- El diseño no se ve: Pico.css se carga por CDN, así que necesitas internet.
- Para detener el servidor, presiona Ctrl+C en la terminal donde está corriendo.

## Base de datos

El archivo `cuentas_por_pagar.db` se crea automáticamente al iniciar `app.py`. No lo edites a mano. Está ignorado por Git.

## Dominio del proyecto

Este proyecto es de cuentas por pagar: proveedores, facturas por pagar, pagos realizados y cheques emitidos. No es de cuentas por cobrar.

## Primer ingreso

El usuario inicial es `admin`. Si definiste `ADMIN_PASSWORD`, usa esa contraseña. Si no la definiste, la contraseña generada se imprime una sola vez en la consola al primer arranque. No guardes contraseñas en este archivo porque se sube a Git.

```text
usuario: admin
password: (la que definiste en ADMIN_PASSWORD o la que imprimió la consola)
```

Roles disponibles: `administrador`, `contador` y `consultor`.

## Datos de ejemplo

El script `sembrar_demo.py` agrega proveedores, facturas, pagos y cheques de prueba. Solo funciona si definiste `ADMIN_PASSWORD` con la contraseña real del administrador. Si la base ya tiene tus propios datos, usa `--permitir-datos` para agregar el ejemplo sin borrar nada. Si el ejemplo ya está sembrado, el script se detiene para no duplicarlo.

```powershell
$env:ADMIN_PASSWORD = "TuContraseñaSegura"
.\.venv\Scripts\python.exe sembrar_demo.py --permitir-datos
```

## Exportación

En la pantalla `Exportar` puedes descargar `facturas.csv` y `pagos.csv`. Los archivos usan separador `;`, BOM UTF-8 y comas decimales para Excel.

## Pruebas

```powershell
.\.venv\Scripts\python.exe -m unittest -v test_app.py
```
