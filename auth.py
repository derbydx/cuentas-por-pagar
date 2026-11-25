import secrets
from functools import wraps

from flask import (
    Blueprint,
    abort,
    current_app,
    flash,
    redirect,
    render_template,
    request,
    session,
    url_for,
)
from werkzeug.security import check_password_hash, generate_password_hash

from db import get_db

auth_bp = Blueprint("auth", __name__)


def generar_csrf_token():
    if "csrf_token" not in session:
        session["csrf_token"] = secrets.token_urlsafe(32)
    return session["csrf_token"]


def validar_csrf():
    enviado = request.form.get("csrf_token", "")
    esperado = session.get("csrf_token", "")
    if not esperado or not secrets.compare_digest(enviado, esperado):
        abort(400, description="Token CSRF inválido.")


def usuario_actual():
    usuario_id = session.get("usuario_id")
    if not usuario_id:
        return None
    return get_db().execute(
        "SELECT id, username, rol FROM usuarios WHERE id = ? AND activo = 1",
        (usuario_id,),
    ).fetchone()


def inyectar_contexto():
    return {"usuario": usuario_actual(), "csrf_token": generar_csrf_token}


def crear_administrador_inicial():
    db = get_db()
    existe = db.execute(
        "SELECT 1 FROM usuarios WHERE rol = 'administrador' LIMIT 1"
    ).fetchone()
    if existe:
        return

    password_configurada = current_app.config.get("ADMIN_PASSWORD")
    password = password_configurada or secrets.token_urlsafe(12)
    db.execute(
        "INSERT INTO usuarios (username, password_hash, rol) VALUES (?, ?, 'administrador')",
        ("admin", generate_password_hash(password)),
    )
    db.commit()

    if password_configurada:
        print("Administrador creado: admin (password desde ADMIN_PASSWORD)")
    else:
        print(f"Administrador creado: admin / {password}")


def login_required(funcion):
    @wraps(funcion)
    def envoltorio(*args, **kwargs):
        if "usuario_id" not in session:
            flash("Inicia sesión para continuar.", "warning")
            destino = request.full_path.rstrip("?")
            return redirect(url_for("auth.login", next=destino))
        return funcion(*args, **kwargs)

    return envoltorio


def role_required(*roles):
    def decorador(funcion):
        @wraps(funcion)
        @login_required
        def envoltorio(*args, **kwargs):
            if session.get("rol") not in roles:
                abort(403)
            return funcion(*args, **kwargs)

        return envoltorio

    return decorador


@auth_bp.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        validar_csrf()
        nombre = request.form.get("username", "").strip()
        password = request.form.get("password", "")

        usuario = get_db().execute(
            "SELECT * FROM usuarios WHERE username = ? AND activo = 1", (nombre,)
        ).fetchone()

        if not usuario or not check_password_hash(usuario["password_hash"], password):
            flash("Usuario o contraseña incorrectos.", "danger")
            return render_template("login.html")

        destino = request.args.get("next", url_for("dashboard"))
        if not destino.startswith("/") or destino.startswith("//"):
            destino = url_for("dashboard")

        session.clear()
        session["usuario_id"] = usuario["id"]
        session["username"] = usuario["username"]
        session["rol"] = usuario["rol"]
        session["csrf_token"] = secrets.token_urlsafe(32)
        flash(f"Bienvenido, {usuario['username']}.", "success")
        return redirect(destino)

    return render_template("login.html")


@auth_bp.route("/logout", methods=["POST"])
def logout():
    validar_csrf()
    session.clear()
    flash("Sesión cerrada.", "info")
    return redirect(url_for("auth.login"))
