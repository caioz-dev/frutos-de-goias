"""Testes da área pública: catálogo, pedido e consulta."""

from datetime import date, timedelta

import pytest

from app.db import get_db
from conftest import TELEFONE, enviar_pedido, id_sabor, token_csrf


def contar_pedidos(app) -> int:
    with app.app_context():
        return get_db().execute("SELECT COUNT(*) FROM pedidos").fetchone()[0]


def test_catalogo_mostra_sabores_e_indisponivel_esmaecido(client):
    html = client.get("/").get_data(as_text=True)
    assert "Pequi" in html and "Pistache" in html
    assert "sabor--indisponivel" in html
    assert "Indisponível" in html


def test_busca_ignora_acentos(client):
    html = client.get("/?q=acai").get_data(as_text=True)
    assert "Açaí" in html
    assert "Pequi" not in html


def test_formulario_nao_oferece_campo_para_sabor_indisponivel(client, app):
    html = client.get("/pedido").get_data(as_text=True)
    assert f'name="qtd_{id_sabor(app, "Pistache")}"' not in html
    assert f'name="qtd_{id_sabor(app, "Pequi")}"' in html


def test_criar_pedido_valido(client, app):
    amanha = (date.today() + timedelta(days=1)).isoformat()
    resp = enviar_pedido(client, app, data_desejada=amanha)
    assert resp.status_code == 302
    assert resp.headers["Location"].endswith("/pedido/confirmacao")

    with app.app_context():
        pedido = get_db().execute("SELECT * FROM pedidos").fetchone()
        itens = get_db().execute("SELECT nome_sabor, quantidade FROM itens_pedido ORDER BY nome_sabor").fetchall()
    assert pedido["status"] == "Novo"
    assert pedido["telefone"] == "62981234567"  # gravado só com dígitos
    assert pedido["data_desejada"] == amanha
    assert [(i["nome_sabor"], i["quantidade"]) for i in itens] == [("Açaí", 5), ("Pequi", 10)]

    html = client.get("/pedido/confirmacao").get_data(as_text=True)
    assert f"Pedido nº <strong>{pedido['id']}</strong>" in html
    assert "Total de itens" in html and "<strong>15</strong>" in html


def test_confirmacao_sem_pedido_volta_ao_catalogo(client):
    assert client.get("/pedido/confirmacao").status_code == 302


def test_rejeita_sabor_indisponivel(client, app):
    resp = enviar_pedido(client, app, **{f"qtd_{id_sabor(app, 'Pistache')}": "3"})
    assert resp.status_code == 400
    assert "Pistache está indisponível" in resp.get_data(as_text=True)
    assert contar_pedidos(app) == 0


def test_rejeita_sabor_inexistente(client, app):
    resp = enviar_pedido(client, app, qtd_9999="3")
    assert resp.status_code == 400
    assert contar_pedidos(app) == 0


@pytest.mark.parametrize("qtd", ["100", "-1", "abc", "1.5", "1e2", "999"])
def test_rejeita_quantidade_invalida(client, app, qtd):
    resp = enviar_pedido(client, app, **{f"qtd_{id_sabor(app, 'Pequi')}": qtd})
    assert resp.status_code == 400
    assert "Quantidade inválida" in resp.get_data(as_text=True)
    assert contar_pedidos(app) == 0


def test_aceita_limites_de_quantidade(client, app):
    resp = enviar_pedido(client, app, **{f"qtd_{id_sabor(app, 'Pequi')}": "99",
                                         f"qtd_{id_sabor(app, 'Açaí')}": "1"})
    assert resp.status_code == 302


def test_rejeita_pedido_sem_itens(client, app):
    resp = enviar_pedido(client, app, **{f"qtd_{id_sabor(app, 'Pequi')}": "", f"qtd_{id_sabor(app, 'Açaí')}": "0"})
    assert resp.status_code == 400
    assert "Escolha pelo menos um sabor" in resp.get_data(as_text=True)


@pytest.mark.parametrize("campo, valor, mensagem", [
    ("nome_responsavel", "", "Nome do responsável é obrigatório"),
    ("instituicao", "   ", "Instituição é obrigatório"),
    ("telefone", "", "Telefone/WhatsApp é obrigatório"),
    ("telefone", "1234", "Telefone/WhatsApp inválido"),
    ("nome_responsavel", "x" * 101, "no máximo 100"),
    ("observacoes", "x" * 301, "no máximo 300"),
    ("data_desejada", "2020-01-01", "não pode estar no passado"),
    ("data_desejada", "31/12/2030", "Data desejada inválida"),
])
def test_valida_campos_do_cliente(client, app, campo, valor, mensagem):
    resp = enviar_pedido(client, app, **{campo: valor})
    assert resp.status_code == 400
    assert mensagem in resp.get_data(as_text=True)
    assert contar_pedidos(app) == 0


def test_html_do_cliente_e_escapado(client, app):
    """Texto com <script> é exibido como texto, nunca executado (XSS)."""
    enviar_pedido(client, app, nome_responsavel="<script>alert(1)</script>")
    html = client.get("/pedido/confirmacao").get_data(as_text=True)
    assert "<script>alert(1)</script>" not in html
    assert "&lt;script&gt;" in html


# ------------------------------------------------------------ consulta pública

def consultar(client, numero, telefone):
    token = token_csrf(client, "/consultar")
    return client.post("/consultar", data={"numero": numero, "telefone": telefone, "csrf_token": token})


def test_consulta_com_numero_e_telefone_corretos(client, app):
    enviar_pedido(client, app)
    outro = app.test_client()  # outro navegador, sem a sessão do pedido
    resp = consultar(outro, "1", "+55 62 98123-4567")
    html = resp.get_data(as_text=True)
    assert resp.status_code == 200
    assert "Pedido nº 1" in html and "Novo" in html
    # Dados pessoais não aparecem na consulta pública.
    assert "Maria Souza" not in html
    assert "98123-4567" not in html


def test_consulta_com_telefone_errado_nao_revela_pedido(client, app):
    enviar_pedido(client, app)
    resp = consultar(app.test_client(), "1", "(62) 98888-7777")
    assert resp.status_code == 404
    assert "Pedido não encontrado" in resp.get_data(as_text=True)


def test_consulta_bloqueia_apos_muitas_tentativas(client, app):
    enviar_pedido(client, app)
    outro = app.test_client()
    for _ in range(10):
        consultar(outro, "1", "(62) 90000-0000")
    resp = consultar(outro, "1", TELEFONE)  # até o correto é recusado durante o bloqueio
    assert resp.status_code == 429
