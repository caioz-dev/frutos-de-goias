"""Testes da área do dono: login, pedidos, status, impressão e sabores."""

from datetime import date

import pytest
from werkzeug.security import check_password_hash

from app.db import get_db
from conftest import ADMIN_SENHA, ADMIN_USUARIO, enviar_pedido, id_sabor, login, token_csrf

ROTAS_PROTEGIDAS_GET = [
    "/admin/",
    "/admin/pedidos",
    "/admin/pedidos/1",
    "/admin/pedidos/1/imprimir",
    "/admin/pedidos/imprimir",
    "/admin/sabores",
    "/admin/sabores/1/editar",
]


@pytest.mark.parametrize("url", ROTAS_PROTEGIDAS_GET)
def test_admin_bloqueado_sem_login(client, app, url):
    enviar_pedido(app.test_client(), app)
    resp = client.get(url)
    assert resp.status_code == 302
    assert "/admin/login" in resp.headers["Location"]


def test_post_admin_bloqueado_sem_login(client, app):
    enviar_pedido(app.test_client(), app)
    token = token_csrf(client, "/admin/login")
    resp = client.post("/admin/pedidos/1/status", data={"status": "Em separação", "csrf_token": token})
    assert resp.status_code == 302 and "/admin/login" in resp.headers["Location"]
    with app.app_context():
        assert get_db().execute("SELECT status FROM pedidos WHERE id = 1").fetchone()[0] == "Novo"


def test_login_com_senha_errada(client):
    resp = login(client, senha="senha-errada")
    assert resp.status_code == 401
    assert "Usuário ou senha incorretos" in resp.get_data(as_text=True)
    assert client.get("/admin/pedidos").status_code == 302  # continua sem acesso


def test_login_com_usuario_inexistente_tem_mesma_mensagem(client):
    resp = login(client, usuario="ninguem")
    assert resp.status_code == 401
    assert "Usuário ou senha incorretos" in resp.get_data(as_text=True)


def test_login_correto_e_logout(client):
    resp = login(client)
    assert resp.status_code == 302 and resp.headers["Location"].endswith("/admin/pedidos")
    assert client.get("/admin/pedidos").status_code == 200

    token = token_csrf(client, "/admin/pedidos")
    client.post("/admin/logout", data={"csrf_token": token})
    assert client.get("/admin/pedidos").status_code == 302


def test_bloqueia_ip_apos_5_falhas(client):
    for _ in range(5):
        assert login(client, senha="errada").status_code == 401
    resp = login(client)  # senha certa, mas o IP está bloqueado
    assert resp.status_code == 429
    assert "Muitas tentativas" in resp.get_data(as_text=True)


def test_login_nao_redireciona_para_site_externo(client):
    token = token_csrf(client, "/admin/login")
    resp = client.post("/admin/login", data={
        "usuario": ADMIN_USUARIO, "senha": ADMIN_SENHA, "csrf_token": token,
        "next": "https://site-malicioso.example/",
    })
    assert resp.headers["Location"].endswith("/admin/pedidos")


def test_senha_guardada_como_hash(app):
    with app.app_context():
        guardado = get_db().execute("SELECT senha_hash FROM usuarios").fetchone()[0]
    assert ADMIN_SENHA not in guardado
    assert check_password_hash(guardado, ADMIN_SENHA)


def test_comando_criar_admin(app):
    runner = app.test_cli_runner()
    resultado = runner.invoke(args=["criar-admin", "--usuario", "maria", "--senha", "outra-senha-forte"])
    assert "criado" in resultado.output
    with app.app_context():
        row = get_db().execute("SELECT senha_hash FROM usuarios WHERE usuario = 'maria'").fetchone()
    assert check_password_hash(row["senha_hash"], "outra-senha-forte")

    curta = runner.invoke(args=["criar-admin", "--usuario", "joao", "--senha", "123"])
    assert curta.exit_code != 0


# ------------------------------------------------------------ pedidos

def status_do_pedido(app, pedido_id=1):
    with app.app_context():
        return get_db().execute("SELECT status FROM pedidos WHERE id = ?", (pedido_id,)).fetchone()[0]


def mudar_status(client, novo, pedido_id=1):
    token = token_csrf(client, f"/admin/pedidos/{pedido_id}")
    return client.post(f"/admin/pedidos/{pedido_id}/status", data={"status": novo, "csrf_token": token})


def test_mudanca_de_status_segue_o_fluxo(client, app):
    enviar_pedido(app.test_client(), app)
    login(client)
    for novo in ["Em separação", "Pronto", "Entregue"]:
        mudar_status(client, novo)
        assert status_do_pedido(app) == novo


def test_status_invalido_e_recusado(client, app):
    enviar_pedido(app.test_client(), app)
    login(client)
    mudar_status(client, "Entregue")  # pular etapas não é permitido
    assert status_do_pedido(app) == "Novo"
    mudar_status(client, "Qualquer coisa")
    assert status_do_pedido(app) == "Novo"


def test_cancelar_pedido(client, app):
    enviar_pedido(app.test_client(), app)
    login(client)
    mudar_status(client, "Cancelado")
    assert status_do_pedido(app) == "Cancelado"


def test_lista_mostra_dados_do_cliente_e_filtra(client, app):
    enviar_pedido(app.test_client(), app)
    enviar_pedido(app.test_client(), app, instituicao="Empresa Ipê Amarelo")
    login(client)
    mudar_status(client, "Em separação", pedido_id=2)

    html = client.get("/admin/pedidos").get_data(as_text=True)
    assert "Maria Souza" in html and "(62) 98123-4567" in html
    # mais recente primeiro
    assert html.index("Empresa Ipê Amarelo") < html.index("Escola Municipal Cerrado")

    html = client.get("/admin/pedidos?status=Novo").get_data(as_text=True)
    assert "Escola Municipal Cerrado" in html and "Empresa Ipê Amarelo" not in html

    html = client.get("/admin/pedidos?instituicao=ipê").get_data(as_text=True)
    assert "Empresa Ipê Amarelo" in html and "Escola Municipal Cerrado" not in html

    hoje = date.today().isoformat()
    assert "Escola Municipal Cerrado" in client.get(f"/admin/pedidos?data_pedido={hoje}").get_data(as_text=True)
    assert "nº 1" not in client.get("/admin/pedidos?data_pedido=2000-01-01").get_data(as_text=True)


def test_filtro_por_data_de_retirada(client, app):
    enviar_pedido(app.test_client(), app, data_desejada="2099-12-24")
    enviar_pedido(app.test_client(), app, instituicao="Outra Escola")
    login(client)
    html = client.get("/admin/pedidos?data_retirada=2099-12-24").get_data(as_text=True)
    assert "Escola Municipal Cerrado" in html and "Outra Escola" not in html


def test_impressao_de_um_pedido(client, app):
    enviar_pedido(app.test_client(), app)
    login(client)
    html = client.get("/admin/pedidos/1/imprimir").get_data(as_text=True)
    for trecho in ["Pedido nº 1", "Maria Souza", "Escola Municipal Cerrado", "(62) 98123-4567",
                   "Pequi", "Total de itens", "Entregar pela manhã", "Separado por:"]:
        assert trecho in html


def test_impressao_dos_filtrados(client, app):
    enviar_pedido(app.test_client(), app)
    enviar_pedido(app.test_client(), app, instituicao="Empresa Ipê Amarelo")
    login(client)
    mudar_status(client, "Cancelado", pedido_id=2)
    html = client.get("/admin/pedidos/imprimir?status=Novo").get_data(as_text=True)
    assert html.count('class="folha"') == 1
    assert "Escola Municipal Cerrado" in html and "Empresa Ipê Amarelo" not in html


# ------------------------------------------------------------ sabores

def test_alternar_disponibilidade_afeta_o_pedido(client, app):
    login(client)
    pequi = id_sabor(app, "Pequi")
    token = token_csrf(client, "/admin/sabores")
    client.post(f"/admin/sabores/{pequi}/disponibilidade", data={"csrf_token": token})

    resp = enviar_pedido(app.test_client(), app)
    assert resp.status_code == 400
    assert "Pequi está indisponível" in resp.get_data(as_text=True)


def test_adicionar_e_editar_sabor(client, app):
    login(client)
    token = token_csrf(client, "/admin/sabores")
    client.post("/admin/sabores", data={"nome": "Baru com Doce de Leite", "categoria": "Especiais", "csrf_token": token})
    assert "Baru com Doce de Leite" in client.get("/").get_data(as_text=True)

    # nome repetido é recusado
    resp = client.post("/admin/sabores", data={"nome": "pequi", "categoria": "X", "csrf_token": token})
    assert resp.status_code == 400

    novo = id_sabor(app, "Baru com Doce de Leite")
    client.post(f"/admin/sabores/{novo}/editar", data={"nome": "Baru Cremoso", "categoria": "Premium", "csrf_token": token})
    with app.app_context():
        row = get_db().execute("SELECT nome, categoria FROM sabores WHERE id = ?", (novo,)).fetchone()
    assert (row["nome"], row["categoria"]) == ("Baru Cremoso", "Premium")


def test_editar_sabor_nao_altera_pedidos_antigos(client, app):
    enviar_pedido(app.test_client(), app)
    login(client)
    token = token_csrf(client, "/admin/sabores")
    client.post(f"/admin/sabores/{id_sabor(app, 'Pequi')}/editar",
                data={"nome": "Pequi Novo", "categoria": "Tradicionais", "csrf_token": token},
                follow_redirects=True)
    html = client.get("/admin/pedidos/1").get_data(as_text=True)
    assert "Pequi" in html and "Pequi Novo" not in html
