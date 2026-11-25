"""Fábrica da aplicação Flask da sorveteria Frutos de Goiás.

Aqui são ligadas as peças: configuração (.env), banco, proteção CSRF,
cookies de sessão seguros, cabeçalhos de segurança e as rotas.
"""

import os
from datetime import timedelta
from pathlib import Path

import click
from dotenv import load_dotenv
from flask import Flask, render_template
from flask_wtf.csrf import CSRFError, CSRFProtect
from werkzeug.security import generate_password_hash

from . import db
from .seguranca import aplicar_cabecalhos

PASTA_PROJETO = Path(__file__).resolve().parent.parent

csrf = CSRFProtect()

STATUS = ["Novo", "Em separação", "Pronto", "Entregue", "Cancelado"]


def create_app(config_extra: dict | None = None) -> Flask:
    # Lê o arquivo .env (SECRET_KEY etc.). Segredos ficam fora do código.
    load_dotenv(PASTA_PROJETO / ".env")

    app = Flask(__name__)

    chave = os.environ.get("SECRET_KEY", "")
    app.config.update(
        SECRET_KEY=chave,
        DATABASE=str(PASTA_PROJETO / os.environ.get("DATABASE", "instance/sorveteria.db")),
        # ---- Cookie de sessão ----
        # Secure: o navegador só envia o cookie por HTTPS.
        # HttpOnly: JavaScript da página não consegue ler o cookie (protege contra XSS).
        # SameSite=Lax: o cookie não acompanha POSTs vindos de outros sites (ajuda contra CSRF).
        SESSION_COOKIE_SECURE=True,
        SESSION_COOKIE_HTTPONLY=True,
        SESSION_COOKIE_SAMESITE="Lax",
        SESSION_COOKIE_NAME="sessao_sorveteria",
        PERMANENT_SESSION_LIFETIME=timedelta(hours=8),
        # ---- CSRF (Flask-WTF) ----
        WTF_CSRF_TIME_LIMIT=None,  # o token vale enquanto durar a sessão
        # Limita o tamanho do corpo das requisições (nenhum formulário passa disso).
        MAX_CONTENT_LENGTH=64 * 1024,
    )
    if config_extra:
        app.config.update(config_extra)

    if not app.config["SECRET_KEY"] or app.config["SECRET_KEY"] == "troque-esta-chave":
        raise RuntimeError(
            "SECRET_KEY não configurada. Copie .env.example para .env e gere uma chave com:\n"
            '  python -c "import secrets; print(secrets.token_hex(32))"'
        )

    db.init_app(app)

    # Proteção CSRF em TODOS os formulários POST: cada formulário leva um token
    # secreto ligado à sessão; requisições sem o token correto são recusadas.
    csrf.init_app(app)

    app.after_request(aplicar_cabecalhos)

    from .rotas_admin import bp as bp_admin
    from .rotas_publicas import bp as bp_publico

    app.register_blueprint(bp_publico)
    app.register_blueprint(bp_admin)

    registrar_erros(app)
    registrar_filtros(app)
    registrar_comandos(app)
    return app


def registrar_erros(app: Flask) -> None:
    @app.errorhandler(CSRFError)
    def erro_csrf(e):
        return render_template(
            "erro.html",
            titulo="Formulário expirado",
            mensagem="Por segurança, recarregue a página e envie o formulário novamente.",
        ), 400

    @app.errorhandler(404)
    def nao_encontrado(e):
        return render_template("erro.html", titulo="Página não encontrada", mensagem="O endereço acessado não existe."), 404

    @app.errorhandler(413)
    def grande_demais(e):
        return render_template("erro.html", titulo="Envio muito grande", mensagem="Os dados enviados excedem o limite."), 413


def registrar_filtros(app: Flask) -> None:
    @app.template_filter("data_br")
    def data_br(valor: str | None) -> str:
        """'2026-11-25' -> '25/11/2026'; '2026-11-25 14:30:00' -> '25/11/2026 14:30'."""
        if not valor:
            return ""
        data, _, hora = valor.partition(" ")
        a, m, d = data.split("-")
        return f"{d}/{m}/{a}" + (f" {hora[:5]}" if hora else "")

    @app.template_filter("telefone_br")
    def telefone_br(digitos: str) -> str:
        if len(digitos) == 11:
            return f"({digitos[:2]}) {digitos[2:7]}-{digitos[7:]}"
        if len(digitos) == 10:
            return f"({digitos[:2]}) {digitos[2:6]}-{digitos[6:]}"
        return digitos

    @app.template_filter("classe_status")
    def classe_status(status: str) -> str:
        return {"Novo": "novo", "Em separação": "separacao", "Pronto": "pronto",
                "Entregue": "entregue", "Cancelado": "cancelado"}.get(status, "")


def registrar_comandos(app: Flask) -> None:
    @app.cli.command("criar-admin")
    @click.option("--usuario", prompt="Usuário", help="Nome de usuário do dono.")
    @click.password_option("--senha", prompt="Senha", confirmation_prompt="Repita a senha")
    def criar_admin(usuario: str, senha: str):
        """Cria (ou redefine a senha de) um usuário da área do dono."""
        usuario = usuario.strip()
        if not usuario or len(usuario) > 40:
            raise click.ClickException("Usuário deve ter entre 1 e 40 caracteres.")
        if len(senha) < 8:
            raise click.ClickException("A senha deve ter pelo menos 8 caracteres.")
        con = db.get_db()
        # Guarda apenas o HASH da senha (scrypt + salt), nunca a senha em si.
        senha_hash = generate_password_hash(senha)
        existente = con.execute("SELECT id FROM usuarios WHERE usuario = ?", (usuario,)).fetchone()
        if existente:
            con.execute("UPDATE usuarios SET senha_hash = ? WHERE id = ?", (senha_hash, existente["id"]))
            msg = f"Senha do usuário '{usuario}' redefinida."
        else:
            con.execute(
                "INSERT INTO usuarios (usuario, senha_hash, criado_em) VALUES (?, ?, ?)",
                (usuario, senha_hash, db.agora()),
            )
            msg = f"Usuário '{usuario}' criado."
        con.commit()
        click.echo(msg)
