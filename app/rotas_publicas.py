"""Rotas da área pública: o que os clientes (empresas/escolas) acessam.

Fluxo cliente -> servidor:
  1. GET  /                 o navegador pede o catálogo; o servidor lê os
                            sabores no SQLite e devolve o HTML pronto.
  2. GET  /pedido           formulário com sabores + campo de quantidade.
  3. POST /pedido           o navegador envia o formulário (com token CSRF);
                            o servidor valida TUDO e grava o pedido.
  4. GET  /pedido/confirmacao  número e resumo do pedido recém-criado.
  5. POST /consultar        número + telefone -> status do pedido.
"""

import unicodedata

from flask import Blueprint, redirect, render_template, request, session, url_for

from .db import agora, get_db
from .seguranca import limitador_consulta, normalizar_telefone, texto, validar_pedido

bp = Blueprint("publico", __name__)


# ---------------------------------------------------------------- utilitários

def sem_acento(s: str) -> str:
    """'Açaí' -> 'acai' (para a busca não depender de acentos)."""
    s = unicodedata.normalize("NFD", s.casefold())
    return "".join(c for c in s if unicodedata.category(c) != "Mn")


def carregar_sabores():
    sabores = get_db().execute("SELECT id, nome, categoria, disponivel FROM sabores").fetchall()
    # Ordena em Python ignorando acentos ("Açaí" fica junto de "Acerola").
    return sorted(sabores, key=lambda s: sem_acento(s["nome"]))


def categoria_bate(termo: str, categoria: str) -> bool:
    """O termo é o começo de alguma palavra da categoria? ("kid" -> "Kids")."""
    return any(p.startswith(termo) for p in sem_acento(categoria).split())


def agrupar_por_categoria(sabores) -> list[tuple[str, list]]:
    """Agrupa mantendo as categorias na ordem em que foram cadastradas."""
    ordem = {
        row["categoria"]: row["primeiro"]
        for row in get_db().execute("SELECT categoria, MIN(id) AS primeiro FROM sabores GROUP BY categoria")
    }
    grupos: dict[str, list] = {}
    for s in sabores:
        grupos.setdefault(s["categoria"], []).append(s)
    return sorted(grupos.items(), key=lambda par: ordem.get(par[0], 0))


def buscar_itens(pedido_id: int):
    return get_db().execute(
        "SELECT nome_sabor, quantidade FROM itens_pedido WHERE pedido_id = ? ORDER BY id",
        (pedido_id,),
    ).fetchall()


# ---------------------------------------------------------------- rotas

@bp.get("/")
def catalogo():
    busca = texto(request.args.get("q"))[:60]
    sabores = carregar_sabores()
    if busca:
        termo = sem_acento(busca)
        sabores = [s for s in sabores if termo in sem_acento(s["nome"]) or categoria_bate(termo, s["categoria"])]
    return render_template("publico/catalogo.html", grupos=agrupar_por_categoria(sabores), busca=busca)


@bp.route("/pedido", methods=["GET", "POST"])
def fazer_pedido():
    sabores = carregar_sabores()
    grupos = agrupar_por_categoria(sabores)

    if request.method == "GET":
        return render_template("publico/pedido.html", grupos=grupos, form={}, erros=[])

    # A validação acontece SEMPRE no servidor: o navegador pode ser
    # manipulado (ex.: alterar o HTML para pedir um sabor indisponível).
    dados, erros = validar_pedido(request.form, {s["id"]: s for s in sabores})
    if erros:
        return render_template("publico/pedido.html", grupos=grupos, form=request.form, erros=erros), 400

    con = get_db()
    momento = agora()
    with con:  # transação: grava pedido e itens juntos, ou nada
        cur = con.execute(
            """INSERT INTO pedidos (nome_responsavel, instituicao, telefone, data_desejada,
                                    observacoes, status, criado_em, atualizado_em)
               VALUES (?, ?, ?, ?, ?, 'Novo', ?, ?)""",
            (dados["nome_responsavel"], dados["instituicao"], dados["telefone"],
             dados["data_desejada"], dados["observacoes"], momento, momento),
        )
        pedido_id = cur.lastrowid
        con.executemany(
            "INSERT INTO itens_pedido (pedido_id, sabor_id, nome_sabor, quantidade) VALUES (?, ?, ?, ?)",
            [(pedido_id, i["sabor_id"], i["nome_sabor"], i["quantidade"]) for i in dados["itens"]],
        )

    # O número do pedido vai na sessão (cookie assinado), não na URL: assim
    # ninguém vê o resumo de outro cliente trocando o número no endereço.
    session["ultimo_pedido"] = pedido_id
    return redirect(url_for("publico.confirmacao"))


@bp.get("/pedido/confirmacao")
def confirmacao():
    pedido_id = session.get("ultimo_pedido")
    pedido = None
    if pedido_id is not None:
        pedido = get_db().execute("SELECT * FROM pedidos WHERE id = ?", (pedido_id,)).fetchone()
    if pedido is None:
        return redirect(url_for("publico.catalogo"))
    itens = buscar_itens(pedido_id)
    total = sum(i["quantidade"] for i in itens)
    return render_template("publico/confirmacao.html", pedido=pedido, itens=itens, total=total)


@bp.route("/consultar", methods=["GET", "POST"])
def consultar():
    """Consulta pública: exige número do pedido E telefone usado no pedido.

    Usa POST para que o telefone não fique registrado na URL/histórico.
    Mostra só status e itens; nome e telefone do cliente nunca aparecem aqui.
    """
    if request.method == "GET":
        return render_template("publico/consultar.html", pedido=None, erro=None, numero="")

    ip = request.remote_addr or "?"
    numero = texto(request.form.get("numero")).lstrip("#")
    telefone = normalizar_telefone(request.form.get("telefone"))

    espera = limitador_consulta.segundos_restantes(ip)
    if espera:
        erro = f"Muitas tentativas. Aguarde {espera // 60 + 1} minuto(s) e tente de novo."
        return render_template("publico/consultar.html", pedido=None, erro=erro, numero=numero), 429

    pedido = None
    if numero.isdigit() and len(numero) <= 9 and telefone:
        pedido = get_db().execute(
            "SELECT id, status, criado_em, data_desejada, atualizado_em FROM pedidos WHERE id = ? AND telefone = ?",
            (int(numero), telefone),
        ).fetchone()

    if pedido is None:
        limitador_consulta.registrar_falha(ip)
        # Mensagem genérica: não revela se o número existe ou se o telefone errou.
        erro = "Pedido não encontrado. Confira o número e o telefone informados no pedido."
        return render_template("publico/consultar.html", pedido=None, erro=erro, numero=numero), 404

    limitador_consulta.registrar_sucesso(ip)
    itens = buscar_itens(pedido["id"])
    return render_template(
        "publico/consultar.html", pedido=pedido, itens=itens,
        total=sum(i["quantidade"] for i in itens), erro=None, numero=numero,
    )
