"""Rotas da área do dono (todas exigem login, exceto a própria tela de login)."""

from datetime import date

from flask import Blueprint, abort, flash, redirect, render_template, request, session, url_for
from werkzeug.security import check_password_hash, generate_password_hash

from . import STATUS
from .db import agora, get_db
from .rotas_publicas import agrupar_por_categoria, carregar_sabores
from .seguranca import (
    LIMITES, destino_seguro, limitador_login, login_obrigatorio, texto,
)

bp = Blueprint("admin", __name__, url_prefix="/admin")

# Mudanças de status permitidas. O fluxo normal é
# Novo -> Em separação -> Pronto -> Entregue; também dá para cancelar ou
# voltar um passo (para corrigir um clique errado).
TRANSICOES = {
    "Novo": ["Em separação", "Cancelado"],
    "Em separação": ["Pronto", "Novo", "Cancelado"],
    "Pronto": ["Entregue", "Em separação", "Cancelado"],
    "Entregue": ["Pronto"],
    "Cancelado": ["Novo"],
}

FLUXO = ["Novo", "Em separação", "Pronto", "Entregue"]


def acoes_de_status(atual: str) -> list[dict]:
    """Botões mostrados no detalhe do pedido: (status destino, rótulo, estilo)."""
    acoes = []
    for novo in TRANSICOES[atual]:
        if novo == "Cancelado":
            acoes.append({"status": novo, "rotulo": "Cancelar pedido", "estilo": "botao--perigo"})
        elif atual == "Cancelado":
            acoes.append({"status": novo, "rotulo": "Reabrir pedido", "estilo": "botao--secundario"})
        elif FLUXO.index(novo) > FLUXO.index(atual):
            acoes.append({"status": novo, "rotulo": f"Marcar como \"{novo}\"", "estilo": ""})
        else:
            acoes.append({"status": novo, "rotulo": f"Voltar para \"{novo}\"", "estilo": "botao--secundario"})
    return acoes


# Hash "falso" usado quando o usuário não existe: assim o tempo de resposta é
# parecido nos dois casos e não dá para descobrir quais usuários existem.
_HASH_FICTICIO = generate_password_hash("senha-ficticia-para-tempo-constante")


# ============================================================ login / logout

@bp.route("/login", methods=["GET", "POST"])
def login():
    if session.get("usuario_id"):
        return redirect(url_for("admin.pedidos"))

    proximo = destino_seguro(request.args.get("next"))
    if request.method == "GET":
        return render_template("admin/login.html", proximo=proximo)

    ip = request.remote_addr or "?"
    espera = limitador_login.segundos_restantes(ip)
    if espera:
        flash(f"Muitas tentativas de login. Aguarde {espera // 60 + 1} minuto(s).", "erro")
        return render_template("admin/login.html", proximo=proximo), 429

    usuario = texto(request.form.get("usuario"))[:40]
    senha = request.form.get("senha", "")[:200]
    row = get_db().execute("SELECT id, usuario, senha_hash FROM usuarios WHERE usuario = ?", (usuario,)).fetchone()

    # check_password_hash recalcula o hash da senha digitada com o mesmo salt
    # e compara em tempo constante.
    senha_ok = check_password_hash(row["senha_hash"] if row else _HASH_FICTICIO, senha)
    if not (row and senha_ok):
        limitador_login.registrar_falha(ip)
        flash("Usuário ou senha incorretos.", "erro")
        return render_template("admin/login.html", proximo=proximo), 401

    limitador_login.registrar_sucesso(ip)
    # Limpa a sessão anterior antes de autenticar (evita fixação de sessão).
    session.clear()
    session["usuario_id"] = row["id"]
    session["usuario"] = row["usuario"]
    session.permanent = True  # expira em 8 horas (PERMANENT_SESSION_LIFETIME)
    return redirect(destino_seguro(request.form.get("next")) or url_for("admin.pedidos"))


@bp.post("/logout")
@login_obrigatorio
def logout():
    # POST (com CSRF) para que um link externo não consiga deslogar o dono.
    session.clear()
    flash("Você saiu da área do dono.", "ok")
    return redirect(url_for("admin.login"))


@bp.get("/")
@login_obrigatorio
def inicio():
    return redirect(url_for("admin.pedidos"))


# ============================================================ pedidos

def ler_filtros() -> dict:
    """Lê e valida os filtros da URL; valores inválidos são ignorados."""
    filtros = {"status": "", "data_pedido": "", "data_retirada": "", "instituicao": ""}
    status = request.args.get("status", "")
    if status in STATUS:
        filtros["status"] = status
    for campo in ("data_pedido", "data_retirada"):
        valor = request.args.get(campo, "")
        try:
            filtros[campo] = date.fromisoformat(valor).isoformat()
        except ValueError:
            pass
    filtros["instituicao"] = texto(request.args.get("instituicao"))[: LIMITES["instituicao"]]
    return filtros


def buscar_pedidos(filtros: dict):
    """Monta a consulta com os filtros. Os VALORES vão sempre como parâmetros."""
    condicoes, params = [], []
    if filtros["status"]:
        condicoes.append("p.status = ?")
        params.append(filtros["status"])
    if filtros["data_pedido"]:
        condicoes.append("date(p.criado_em) = ?")
        params.append(filtros["data_pedido"])
    if filtros["data_retirada"]:
        condicoes.append("p.data_desejada = ?")
        params.append(filtros["data_retirada"])
    if filtros["instituicao"]:
        # Escapa % e _ para que sejam tratados como texto comum no LIKE.
        termo = filtros["instituicao"].replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
        condicoes.append("p.instituicao LIKE ? ESCAPE '\\'")
        params.append(f"%{termo}%")
    where = ("WHERE " + " AND ".join(condicoes)) if condicoes else ""
    return get_db().execute(
        f"""SELECT p.*, COALESCE(SUM(i.quantidade), 0) AS total_itens
            FROM pedidos p LEFT JOIN itens_pedido i ON i.pedido_id = p.id
            {where}
            GROUP BY p.id
            ORDER BY p.criado_em DESC, p.id DESC""",
        params,
    ).fetchall()


def buscar_pedido(pedido_id: int):
    pedido = get_db().execute("SELECT * FROM pedidos WHERE id = ?", (pedido_id,)).fetchone()
    if pedido is None:
        abort(404)
    itens = get_db().execute(
        "SELECT nome_sabor, quantidade FROM itens_pedido WHERE pedido_id = ? ORDER BY nome_sabor COLLATE NOCASE",
        (pedido_id,),
    ).fetchall()
    return pedido, itens


@bp.get("/pedidos")
@login_obrigatorio
def pedidos():
    filtros = ler_filtros()
    lista = buscar_pedidos(filtros)
    contagem = {
        row["status"]: row["n"]
        for row in get_db().execute("SELECT status, COUNT(*) AS n FROM pedidos GROUP BY status")
    }
    return render_template(
        "admin/pedidos.html", pedidos=lista, filtros=filtros, status_lista=STATUS,
        filtros_ativos={k: v for k, v in filtros.items() if v},
        contagem=contagem, hoje=date.today().isoformat(),
    )


@bp.get("/pedidos/<int:pedido_id>")
@login_obrigatorio
def pedido_detalhe(pedido_id: int):
    pedido, itens = buscar_pedido(pedido_id)
    return render_template(
        "admin/pedido_detalhe.html", pedido=pedido, itens=itens,
        total=sum(i["quantidade"] for i in itens), acoes=acoes_de_status(pedido["status"]),
    )


@bp.post("/pedidos/<int:pedido_id>/status")
@login_obrigatorio
def mudar_status(pedido_id: int):
    pedido, _ = buscar_pedido(pedido_id)
    novo = request.form.get("status", "")
    if novo not in TRANSICOES[pedido["status"]]:
        flash(f"Não é possível mudar de \"{pedido['status']}\" para \"{novo}\".", "erro")
        return redirect(url_for("admin.pedido_detalhe", pedido_id=pedido_id))
    con = get_db()
    with con:
        con.execute("UPDATE pedidos SET status = ?, atualizado_em = ? WHERE id = ?", (novo, agora(), pedido_id))
    flash(f"Pedido nº {pedido_id} agora está \"{novo}\".", "ok")
    voltar = destino_seguro(request.form.get("voltar"))
    return redirect(voltar or url_for("admin.pedido_detalhe", pedido_id=pedido_id))


@bp.get("/pedidos/<int:pedido_id>/imprimir")
@login_obrigatorio
def imprimir_pedido(pedido_id: int):
    pedido, itens = buscar_pedido(pedido_id)
    return render_template("admin/imprimir.html", lista=[(pedido, itens)], filtros=None)


@bp.get("/pedidos/imprimir")
@login_obrigatorio
def imprimir_filtrados():
    filtros = ler_filtros()
    lista = [buscar_pedido(p["id"]) for p in buscar_pedidos(filtros)]
    return render_template("admin/imprimir.html", lista=lista, filtros=filtros)


# ============================================================ sabores

def validar_sabor(form, ignorar_id: int | None = None) -> tuple[dict, list[str]]:
    dados = {"nome": texto(form.get("nome")), "categoria": texto(form.get("categoria"))}
    erros = []
    if not dados["nome"]:
        erros.append("Informe o nome do sabor.")
    elif len(dados["nome"]) > LIMITES["nome_sabor"]:
        erros.append(f"O nome deve ter no máximo {LIMITES['nome_sabor']} caracteres.")
    if not dados["categoria"]:
        erros.append("Informe a categoria.")
    elif len(dados["categoria"]) > LIMITES["categoria"]:
        erros.append(f"A categoria deve ter no máximo {LIMITES['categoria']} caracteres.")
    if dados["nome"]:
        repetido = get_db().execute(
            "SELECT id FROM sabores WHERE nome = ? COLLATE NOCASE AND id IS NOT ?", (dados["nome"], ignorar_id)
        ).fetchone()
        if repetido:
            erros.append(f"Já existe um sabor chamado \"{dados['nome']}\".")
    return dados, erros


def categorias_existentes() -> list[str]:
    return [r["categoria"] for r in get_db().execute(
        "SELECT categoria FROM sabores GROUP BY categoria ORDER BY MIN(id)"
    )]


def tela_sabores(form, erros):
    lista = carregar_sabores()
    return render_template(
        "admin/sabores.html", grupos=agrupar_por_categoria(lista),
        categorias=categorias_existentes(), form=form, erros=erros,
    )


@bp.get("/sabores")
@login_obrigatorio
def sabores():
    return tela_sabores({}, [])


@bp.post("/sabores")
@login_obrigatorio
def novo_sabor():
    dados, erros = validar_sabor(request.form)
    if erros:
        return tela_sabores(request.form, erros), 400
    con = get_db()
    with con:
        con.execute("INSERT INTO sabores (nome, categoria, disponivel) VALUES (?, ?, 1)",
                    (dados["nome"], dados["categoria"]))
    flash(f"Sabor \"{dados['nome']}\" adicionado.", "ok")
    return redirect(url_for("admin.sabores"))


@bp.route("/sabores/<int:sabor_id>/editar", methods=["GET", "POST"])
@login_obrigatorio
def editar_sabor(sabor_id: int):
    sabor = get_db().execute("SELECT * FROM sabores WHERE id = ?", (sabor_id,)).fetchone()
    if sabor is None:
        abort(404)
    if request.method == "GET":
        return render_template("admin/sabor_editar.html", sabor=sabor, form=dict(sabor),
                               categorias=categorias_existentes(), erros=[])
    dados, erros = validar_sabor(request.form, ignorar_id=sabor_id)
    if erros:
        return render_template("admin/sabor_editar.html", sabor=sabor, form=request.form,
                               categorias=categorias_existentes(), erros=erros), 400
    con = get_db()
    with con:
        con.execute("UPDATE sabores SET nome = ?, categoria = ? WHERE id = ?",
                    (dados["nome"], dados["categoria"], sabor_id))
    flash(f"Sabor \"{dados['nome']}\" atualizado.", "ok")
    return redirect(url_for("admin.sabores") + f"#sabor-{sabor_id}")


@bp.post("/sabores/<int:sabor_id>/disponibilidade")
@login_obrigatorio
def alternar_disponibilidade(sabor_id: int):
    sabor = get_db().execute("SELECT * FROM sabores WHERE id = ?", (sabor_id,)).fetchone()
    if sabor is None:
        abort(404)
    novo = 0 if sabor["disponivel"] else 1
    con = get_db()
    with con:
        con.execute("UPDATE sabores SET disponivel = ? WHERE id = ?", (novo, sabor_id))
    flash(f"\"{sabor['nome']}\" agora está {'disponível' if novo else 'indisponível'}.", "ok")
    return redirect(url_for("admin.sabores") + f"#sabor-{sabor_id}")
