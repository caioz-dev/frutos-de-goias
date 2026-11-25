"""Acesso ao banco de dados SQLite (módulo sqlite3 da biblioteca padrão).

Regra de ouro deste projeto: TODA consulta usa parâmetros (?) e nunca
concatena texto vindo do usuário no SQL. Isso impede injeção de SQL.
"""

import sqlite3
from datetime import datetime
from pathlib import Path

from flask import current_app, g


def agora() -> str:
    """Data/hora local no formato gravado no banco."""
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def get_db() -> sqlite3.Connection:
    """Abre (uma vez por requisição) a conexão com o banco."""
    if "db" not in g:
        g.db = sqlite3.connect(current_app.config["DATABASE"])
        g.db.row_factory = sqlite3.Row  # permite acessar colunas pelo nome
        g.db.execute("PRAGMA foreign_keys = ON")
    return g.db


def close_db(_erro=None) -> None:
    """Fecha a conexão ao final da requisição."""
    db = g.pop("db", None)
    if db is not None:
        db.close()


def criar_tabelas(caminho_banco: str) -> None:
    """Cria as tabelas caso ainda não existam."""
    Path(caminho_banco).parent.mkdir(parents=True, exist_ok=True)
    esquema = (Path(__file__).parent / "schema.sql").read_text(encoding="utf-8")
    con = sqlite3.connect(caminho_banco)
    try:
        con.executescript(esquema)
    finally:
        con.close()


def init_app(app) -> None:
    criar_tabelas(app.config["DATABASE"])
    app.teardown_appcontext(close_db)
