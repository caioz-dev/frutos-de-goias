"""Testes dos mecanismos de segurança transversais."""

import sqlite3

from app import create_app
from conftest import dados_pedido, login, token_csrf


def test_csrf_ativo_rejeita_post_sem_token(client, app):
    resp = client.post("/pedido", data=dados_pedido(app))
    assert resp.status_code == 400
    assert "Formulário expirado" in resp.get_data(as_text=True)


def test_csrf_rejeita_token_falso(client, app):
    client.get("/pedido")
    dados = dados_pedido(app)
    dados["csrf_token"] = "token-inventado"
    assert client.post("/pedido", data=dados).status_code == 400


def test_csrf_protege_login_e_admin(client):
    assert client.post("/admin/login", data={"usuario": "dono", "senha": "x"}).status_code == 400
    login(client)
    assert client.post("/admin/pedidos/1/status", data={"status": "Pronto"}).status_code == 400
    assert client.post("/admin/logout").status_code == 400


def test_token_de_uma_sessao_nao_vale_em_outra(client, app):
    token = token_csrf(client, "/pedido")
    outro = app.test_client()
    outro.get("/pedido")
    dados = dados_pedido(app)
    dados["csrf_token"] = token
    assert outro.post("/pedido", data=dados).status_code == 400


def test_cabecalhos_de_seguranca(client):
    resp = client.get("/")
    assert resp.headers["X-Content-Type-Options"] == "nosniff"
    assert resp.headers["X-Frame-Options"] == "DENY"
    csp = resp.headers["Content-Security-Policy"]
    assert "default-src 'self'" in csp and "frame-ancestors 'none'" in csp
    assert "unsafe-inline" not in csp


def test_admin_nao_fica_em_cache(client):
    login(client)
    assert client.get("/admin/pedidos").headers["Cache-Control"] == "no-store"


def test_cookie_de_sessao_secure_httponly_samesite(tmp_path):
    """Com a configuração padrão (produção) o cookie sai com as três proteções."""
    app = create_app({"SECRET_KEY": "x" * 32, "DATABASE": str(tmp_path / "c.db")})
    resp = app.test_client().get("/pedido")  # gera token CSRF -> grava a sessão
    cookie = resp.headers["Set-Cookie"]
    assert "Secure" in cookie
    assert "HttpOnly" in cookie
    assert "SameSite=Lax" in cookie


def test_app_recusa_iniciar_sem_secret_key(tmp_path, monkeypatch):
    monkeypatch.setenv("SECRET_KEY", "")
    try:
        create_app({"DATABASE": str(tmp_path / "s.db")})
    except RuntimeError as e:
        assert "SECRET_KEY" in str(e)
    else:
        raise AssertionError("deveria exigir SECRET_KEY")


def test_injecao_sql_no_filtro_e_inofensiva(client, app):
    login(client)
    resp = client.get("/admin/pedidos?instituicao=' OR 1=1; DROP TABLE pedidos; --")
    assert resp.status_code == 200
    con = sqlite3.connect(app.config["DATABASE"])
    assert con.execute("SELECT COUNT(*) FROM pedidos").fetchone()[0] == 0  # tabela intacta
    con.close()


def test_seed_insere_sabores_sem_duplicar(app):
    import seed
    from app.db import get_db
    with app.app_context():
        primeira = seed.popular(get_db())
        segunda = seed.popular(get_db())
        total = get_db().execute("SELECT COUNT(*) FROM sabores").fetchone()[0]
    esperado = sum(len(v) for v in seed.SABORES.values())
    assert segunda == 0
    assert total >= esperado and primeira > 0
    assert len(seed.SABORES["Premium"]) == 25 and "Alfajor" in seed.SABORES["Premium"]
    assert len(seed.SABORES["Especiais"]) == 6 and "Chocolate Belga" in seed.SABORES["Especiais"]
    # Ordem das categorias na página: Tradicionais, Premium, Especiais, Kids...
    assert list(seed.SABORES)[:3] == ["Tradicionais", "Premium", "Especiais"]
