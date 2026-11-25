"""Configuração compartilhada dos testes.

Cada teste recebe um banco SQLite novo (em pasta temporária) com alguns
sabores e um usuário admin. A proteção CSRF fica LIGADA, como em produção:
os testes buscam o token na página antes de enviar formulários.
"""

import re
import sys
from pathlib import Path

import pytest
from werkzeug.security import generate_password_hash

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app import create_app  # noqa: E402
from app.db import agora, get_db  # noqa: E402
from app.seguranca import limitador_consulta, limitador_login  # noqa: E402

ADMIN_USUARIO = "dono"
ADMIN_SENHA = "senha-de-teste-123"
TELEFONE = "(62) 98123-4567"


@pytest.fixture
def app(tmp_path):
    app = create_app({
        "TESTING": True,
        "SECRET_KEY": "chave-so-para-testes",
        "DATABASE": str(tmp_path / "teste.db"),
        # O cliente de testes usa http://; em produção o cookie é Secure (há
        # um teste específico verificando isso).
        "SESSION_COOKIE_SECURE": False,
    })
    with app.app_context():
        con = get_db()
        con.executemany(
            "INSERT INTO sabores (nome, categoria, disponivel) VALUES (?, ?, ?)",
            [("Pequi", "Tradicionais", 1), ("Açaí", "Tradicionais", 1), ("Pistache", "Especiais", 0)],
        )
        con.execute(
            "INSERT INTO usuarios (usuario, senha_hash, criado_em) VALUES (?, ?, ?)",
            (ADMIN_USUARIO, generate_password_hash(ADMIN_SENHA), agora()),
        )
        con.commit()
    limitador_login.limpar()
    limitador_consulta.limpar()
    yield app
    limitador_login.limpar()
    limitador_consulta.limpar()


@pytest.fixture
def client(app):
    return app.test_client()


def token_csrf(client, url: str) -> str:
    """Abre a página e extrai o token CSRF do formulário."""
    html = client.get(url).get_data(as_text=True)
    achado = re.search(r'name="csrf_token" value="([^"]+)"', html)
    assert achado, f"token CSRF não encontrado em {url}"
    return achado.group(1)


def id_sabor(app, nome: str) -> int:
    with app.app_context():
        return get_db().execute("SELECT id FROM sabores WHERE nome = ?", (nome,)).fetchone()["id"]


def dados_pedido(app, **extra) -> dict:
    dados = {
        "nome_responsavel": "Maria Souza",
        "instituicao": "Escola Municipal Cerrado",
        "telefone": TELEFONE,
        "data_desejada": "",
        "observacoes": "Entregar pela manhã",
        f"qtd_{id_sabor(app, 'Pequi')}": "10",
        f"qtd_{id_sabor(app, 'Açaí')}": "5",
    }
    dados.update(extra)
    return dados


def enviar_pedido(client, app, **extra):
    dados = dados_pedido(app, **extra)
    dados["csrf_token"] = token_csrf(client, "/pedido")
    return client.post("/pedido", data=dados)


def login(client, usuario=ADMIN_USUARIO, senha=ADMIN_SENHA):
    token = token_csrf(client, "/admin/login")
    return client.post("/admin/login", data={"usuario": usuario, "senha": senha, "csrf_token": token})
