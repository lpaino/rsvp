from __future__ import annotations

import os
import sqlite3
from datetime import datetime
from functools import wraps
from pathlib import Path

from flask import (
    Flask,
    flash,
    g,
    jsonify,
    redirect,
    render_template,
    request,
    url_for,
)
from flask_login import (
    LoginManager,
    UserMixin,
    current_user,
    login_required,
    login_user,
    logout_user,
)
from werkzeug.security import check_password_hash, generate_password_hash

BASE_DIR = Path(__file__).resolve().parent
DATABASE = BASE_DIR / "party.db"

app = Flask(__name__)
app.config["SECRET_KEY"] = os.getenv("SECRET_KEY", "dev-secret-change-me")

login_manager = LoginManager()
login_manager.login_view = "login"
login_manager.init_app(app)


class User(UserMixin):
    def __init__(self, id_: int, username: str, password_hash: str, role: str):
        self.id = str(id_)
        self.username = username
        self.password_hash = password_hash
        self.role = role

    @staticmethod
    def from_row(row: sqlite3.Row) -> "User":
        return User(row["id"], row["username"], row["password_hash"], row["role"])


def get_db() -> sqlite3.Connection:
    if "db" not in g:
        g.db = sqlite3.connect(DATABASE)
        g.db.row_factory = sqlite3.Row
    return g.db


@app.teardown_appcontext
def close_db(exception=None):
    db = g.pop("db", None)
    if db is not None:
        db.close()


def init_db():
    db = sqlite3.connect(DATABASE)
    cursor = db.cursor()
    cursor.executescript(
        """
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT NOT NULL UNIQUE,
            password_hash TEXT NOT NULL,
            role TEXT NOT NULL CHECK (role IN ('admin', 'organizador', 'consulta'))
        );

        CREATE TABLE IF NOT EXISTS festa (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            nome TEXT NOT NULL,
            data_evento TEXT,
            local TEXT,
            descricao TEXT,
            created_at TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS fornecedores (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            nome TEXT NOT NULL,
            categoria TEXT,
            contato TEXT,
            observacoes TEXT
        );

        CREATE TABLE IF NOT EXISTS convidados (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            nome TEXT NOT NULL UNIQUE,
            telefone TEXT,
            grupo TEXT,
            confirmado INTEGER NOT NULL DEFAULT 0,
            confirmado_em TEXT
        );

        CREATE TABLE IF NOT EXISTS rsvp_submissions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            solicitante_id INTEGER NOT NULL,
            criado_em TEXT NOT NULL,
            FOREIGN KEY (solicitante_id) REFERENCES convidados(id)
        );

        CREATE TABLE IF NOT EXISTS rsvp_confirmados (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            submission_id INTEGER NOT NULL,
            convidado_id INTEGER NOT NULL,
            FOREIGN KEY (submission_id) REFERENCES rsvp_submissions(id),
            FOREIGN KEY (convidado_id) REFERENCES convidados(id)
        );
        """
    )

    existing_admin = cursor.execute("SELECT id FROM users WHERE username = ?", ("admin",)).fetchone()
    if not existing_admin:
        cursor.execute(
            "INSERT INTO users (username, password_hash, role) VALUES (?, ?, ?)",
            ("admin", generate_password_hash("admin123"), "admin"),
        )
    db.commit()
    db.close()


@login_manager.user_loader
def load_user(user_id: str):
    db = get_db()
    row = db.execute("SELECT * FROM users WHERE id = ?", (user_id,)).fetchone()
    return User.from_row(row) if row else None


def role_required(*roles):
    def decorator(view):
        @wraps(view)
        @login_required
        def wrapped(*args, **kwargs):
            if current_user.role not in roles:
                flash("Você não possui permissão para acessar esta área.", "danger")
                return redirect(url_for("dashboard"))
            return view(*args, **kwargs)

        return wrapped

    return decorator


def normalize_name(name: str) -> str:
    return " ".join(name.strip().split()).lower()


@app.route("/")
def index():
    return redirect(url_for("dashboard" if current_user.is_authenticated else "portal_rsvp"))


@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        username = request.form.get("username", "").strip()
        password = request.form.get("password", "")
        row = get_db().execute("SELECT * FROM users WHERE username = ?", (username,)).fetchone()
        if row and check_password_hash(row["password_hash"], password):
            login_user(User.from_row(row))
            return redirect(url_for("dashboard"))
        flash("Credenciais inválidas.", "danger")
    return render_template("login.html")


@app.route("/logout")
@login_required
def logout():
    logout_user()
    return redirect(url_for("login"))


@app.route("/dashboard")
@login_required
def dashboard():
    db = get_db()
    stats = {
        "total_convidados": db.execute("SELECT COUNT(*) FROM convidados").fetchone()[0],
        "confirmados": db.execute("SELECT COUNT(*) FROM convidados WHERE confirmado = 1").fetchone()[0],
        "fornecedores": db.execute("SELECT COUNT(*) FROM fornecedores").fetchone()[0],
    }
    festa = db.execute("SELECT * FROM festa ORDER BY id DESC LIMIT 1").fetchone()
    return render_template("dashboard.html", stats=stats, festa=festa)


@app.route("/usuarios", methods=["GET", "POST"])
@role_required("admin")
def usuarios():
    db = get_db()
    if request.method == "POST":
        db.execute(
            "INSERT INTO users (username, password_hash, role) VALUES (?, ?, ?)",
            (
                request.form["username"].strip(),
                generate_password_hash(request.form["password"]),
                request.form["role"],
            ),
        )
        db.commit()
        flash("Usuário criado com sucesso.", "success")
        return redirect(url_for("usuarios"))

    users = db.execute("SELECT id, username, role FROM users ORDER BY username").fetchall()
    return render_template("usuarios.html", users=users)


@app.route("/festa", methods=["GET", "POST"])
@role_required("admin", "organizador")
def cadastro_festa():
    db = get_db()
    if request.method == "POST":
        db.execute(
            "INSERT INTO festa (nome, data_evento, local, descricao, created_at) VALUES (?, ?, ?, ?, ?)",
            (
                request.form["nome"],
                request.form.get("data_evento"),
                request.form.get("local"),
                request.form.get("descricao"),
                datetime.now().isoformat(),
            ),
        )
        db.commit()
        flash("Festa cadastrada com sucesso.", "success")
        return redirect(url_for("cadastro_festa"))

    festas = db.execute("SELECT * FROM festa ORDER BY id DESC").fetchall()
    return render_template("festa.html", festas=festas)


@app.route("/fornecedores", methods=["GET", "POST"])
@role_required("admin", "organizador")
def fornecedores():
    db = get_db()
    if request.method == "POST":
        db.execute(
            "INSERT INTO fornecedores (nome, categoria, contato, observacoes) VALUES (?, ?, ?, ?)",
            (
                request.form["nome"],
                request.form.get("categoria"),
                request.form.get("contato"),
                request.form.get("observacoes"),
            ),
        )
        db.commit()
        flash("Fornecedor cadastrado com sucesso.", "success")
        return redirect(url_for("fornecedores"))

    lista = db.execute("SELECT * FROM fornecedores ORDER BY nome").fetchall()
    return render_template("fornecedores.html", fornecedores=lista)


@app.route("/convidados", methods=["GET", "POST"])
@role_required("admin", "organizador")
def convidados():
    db = get_db()
    if request.method == "POST":
        nome = " ".join(request.form["nome"].strip().split())
        exists = db.execute(
            "SELECT id FROM convidados WHERE lower(nome) = ?",
            (normalize_name(nome),),
        ).fetchone()
        if exists:
            flash("Este nome já existe na lista de convidados.", "danger")
            return redirect(url_for("convidados"))

        db.execute(
            "INSERT INTO convidados (nome, telefone, grupo) VALUES (?, ?, ?)",
            (nome, request.form.get("telefone"), request.form.get("grupo")),
        )
        db.commit()
        flash("Convidado cadastrado com sucesso.", "success")
        return redirect(url_for("convidados"))

    lista = db.execute("SELECT * FROM convidados ORDER BY nome").fetchall()
    return render_template("convidados.html", convidados=lista)


@app.route("/portal-rsvp", methods=["GET", "POST"])
def portal_rsvp():
    db = get_db()
    if request.method == "POST":
        principal_nome = " ".join(request.form.get("principal", "").strip().split())
        tem_acompanhante = request.form.get("tem_acompanhante", "nao")
        acompanhants = [
            " ".join(n.strip().split())
            for n in request.form.getlist("acompanhantes")
            if n.strip()
        ]

        if tem_acompanhante != "sim":
            acompanhants = []

        nomes_para_validar = [principal_nome] + acompanhants

        if not principal_nome:
            flash("Informe o nome do convidado principal.", "danger")
            return redirect(url_for("portal_rsvp"))

        normalized_map = {}
        for nome in nomes_para_validar:
            key = normalize_name(nome)
            if key in normalized_map:
                flash("Existem nomes duplicados na confirmação. Revise os acompanhantes.", "danger")
                return redirect(url_for("portal_rsvp"))
            normalized_map[key] = nome

        placeholders = " OR ".join(["lower(nome) = ?" for _ in normalized_map])
        rows = db.execute(
            f"SELECT id, nome FROM convidados WHERE {placeholders}",
            tuple(normalized_map.keys()),
        ).fetchall()
        encontrados = {normalize_name(r["nome"]): {"id": r["id"], "nome": r["nome"]} for r in rows}
        faltantes = [nome_original for key, nome_original in normalized_map.items() if key not in encontrados]

        if faltantes:
            flash(
                "Os seguintes nomes não estão na lista de convidados: " + ", ".join(faltantes),
                "danger",
            )
            return redirect(url_for("portal_rsvp"))

        submission = db.execute(
            "INSERT INTO rsvp_submissions (solicitante_id, criado_em) VALUES (?, ?)",
            (encontrados[normalize_name(principal_nome)]["id"], datetime.now().isoformat()),
        )
        submission_id = submission.lastrowid

        for nome in nomes_para_validar:
            convidado_id = encontrados[normalize_name(nome)]["id"]
            db.execute(
                "INSERT INTO rsvp_confirmados (submission_id, convidado_id) VALUES (?, ?)",
                (submission_id, convidado_id),
            )
            db.execute(
                "UPDATE convidados SET confirmado = 1, confirmado_em = ? WHERE id = ?",
                (datetime.now().isoformat(), convidado_id),
            )

        db.commit()
        flash("Presença confirmada com sucesso!", "success")
        return redirect(url_for("portal_rsvp"))

    total_confirmados = db.execute("SELECT COUNT(*) FROM convidados WHERE confirmado = 1").fetchone()[0]
    return render_template("portal_rsvp.html", total_confirmados=total_confirmados)


@app.route("/api/convidados/existe")
def api_convidado_existe():
    nome = request.args.get("nome", "")
    nome_normalizado = normalize_name(nome)
    if not nome_normalizado:
        return jsonify({"exists": False, "nome": None})

    row = get_db().execute(
        "SELECT nome FROM convidados WHERE lower(nome) = ?",
        (nome_normalizado,),
    ).fetchone()
    return jsonify({"exists": bool(row), "nome": row["nome"] if row else None})


if __name__ == "__main__":
    init_db()
    app.run(host="0.0.0.0", port=5000, debug=True)
