"""Mecanismos de segurança da aplicação.

Reúne em um só lugar:
  * cabeçalhos HTTP de segurança;
  * exigência de login nas rotas administrativas;
  * limite de tentativas (login e consulta pública de pedido);
  * validação dos dados enviados pelos formulários.

A criptografia da comunicação (HTTPS/TLS) é feita pelo servidor com o
certificado gerado por gerar_certificado.py (ver servidor.py).
"""

import re
import threading
import time
from datetime import date
from functools import wraps
from urllib.parse import urlsplit

from flask import flash, redirect, request, session, url_for

# --------------------------------------------------------------------------
# Cabeçalhos de segurança
# --------------------------------------------------------------------------

# Content-Security-Policy: o navegador só carrega CSS, JS e imagens do próprio
# servidor. Scripts embutidos no HTML (inline) ficam proibidos, o que reduz
# muito o risco de XSS. frame-ancestors 'none' impede que o site seja aberto
# dentro de um <iframe> de outro site (clickjacking).
CSP = (
    "default-src 'self'; "
    "script-src 'self'; "
    "style-src 'self'; "
    "img-src 'self' data:; "
    "form-action 'self'; "
    "frame-ancestors 'none'; "
    "base-uri 'self'; "
    "object-src 'none'"
)


def aplicar_cabecalhos(resposta):
    """Executado depois de toda requisição (after_request)."""
    resposta.headers["Content-Security-Policy"] = CSP
    # Impede que o navegador "adivinhe" o tipo de um arquivo (MIME sniffing).
    resposta.headers["X-Content-Type-Options"] = "nosniff"
    # Proteção contra clickjacking para navegadores antigos (complementa o CSP).
    resposta.headers["X-Frame-Options"] = "DENY"
    # Não vaza o endereço completo das páginas para outros sites.
    resposta.headers["Referrer-Policy"] = "same-origin"
    # Páginas da área do dono contêm dados de clientes: não guardar em cache.
    if request.path.startswith("/admin"):
        resposta.headers["Cache-Control"] = "no-store"
    return resposta


# --------------------------------------------------------------------------
# Autenticação
# --------------------------------------------------------------------------


def login_obrigatorio(view):
    """Decorador: redireciona para o login se o usuário não estiver logado."""

    @wraps(view)
    def envolvida(*args, **kwargs):
        if session.get("usuario_id") is None:
            flash("Faça login para acessar a área do dono.", "aviso")
            return redirect(url_for("admin.login", next=request.full_path))
        return view(*args, **kwargs)

    return envolvida


def destino_seguro(proximo: str | None) -> str | None:
    """Aceita só caminhos internos da área admin no parâmetro ?next=.

    Evita "open redirect": um link malicioso como
    /admin/login?next=https://site-falso.com não leva o usuário para fora.
    """
    if not proximo:
        return None
    partes = urlsplit(proximo)
    if partes.scheme or partes.netloc or not partes.path.startswith("/admin/"):
        return None
    if "\\" in proximo:
        return None
    return proximo


# --------------------------------------------------------------------------
# Limite de tentativas (em memória)
# --------------------------------------------------------------------------


class LimitadorTentativas:
    """Bloqueia um IP depois de N falhas dentro de uma janela de tempo.

    Fica em memória: reiniciar o servidor zera os contadores. Para um
    servidor único e local isso é suficiente e evita complexidade.
    """

    def __init__(self, max_falhas: int = 5, bloqueio_segundos: int = 300):
        self.max_falhas = max_falhas
        self.bloqueio_segundos = bloqueio_segundos
        self._falhas: dict[str, list[float]] = {}
        self._bloqueado_ate: dict[str, float] = {}
        self._trava = threading.Lock()  # o servidor atende requisições em threads

    def segundos_restantes(self, ip: str) -> int:
        """Quanto tempo falta para desbloquear (0 = liberado)."""
        with self._trava:
            fim = self._bloqueado_ate.get(ip, 0)
            restante = fim - time.monotonic()
            if restante <= 0:
                self._bloqueado_ate.pop(ip, None)
                return 0
            return int(restante) + 1

    def registrar_falha(self, ip: str) -> None:
        agora = time.monotonic()
        with self._trava:
            # Só contam as falhas dentro da janela de tempo.
            recentes = [t for t in self._falhas.get(ip, []) if agora - t < self.bloqueio_segundos]
            recentes.append(agora)
            if len(recentes) >= self.max_falhas:
                self._bloqueado_ate[ip] = agora + self.bloqueio_segundos
                recentes = []
            self._falhas[ip] = recentes

    def registrar_sucesso(self, ip: str) -> None:
        with self._trava:
            self._falhas.pop(ip, None)

    def limpar(self) -> None:
        with self._trava:
            self._falhas.clear()
            self._bloqueado_ate.clear()


# 5 senhas erradas -> IP bloqueado por 5 minutos.
limitador_login = LimitadorTentativas(max_falhas=5, bloqueio_segundos=300)
# A consulta pública também é limitada para dificultar "chutar" telefones.
limitador_consulta = LimitadorTentativas(max_falhas=10, bloqueio_segundos=300)


# --------------------------------------------------------------------------
# Validação de entradas (sempre no servidor; o HTML pode ser burlado)
# --------------------------------------------------------------------------

LIMITES = {
    "nome_responsavel": 100,
    "instituicao": 120,
    "observacoes": 300,
    "nome_sabor": 60,
    "categoria": 40,
}

QTD_MIN, QTD_MAX = 1, 99


def texto(valor: str | None) -> str:
    """Remove espaços extras e caracteres de controle de um texto."""
    if valor is None:
        return ""
    valor = re.sub(r"[\x00-\x08\x0b-\x1f\x7f]", "", valor)
    return valor.strip()


def normalizar_telefone(valor: str | None) -> str:
    """Mantém só os dígitos: '(62) 99999-8888' -> '62999998888'."""
    return re.sub(r"\D", "", valor or "")


def telefone_valido(digitos: str) -> bool:
    # DDD + número (10 ou 11 dígitos); aceita também +55 na frente.
    return 10 <= len(digitos) <= 13


def validar_data_desejada(valor: str) -> tuple[str | None, str | None]:
    """Retorna (data_iso, erro). Data vazia é permitida."""
    if not valor:
        return None, None
    try:
        d = date.fromisoformat(valor)
    except ValueError:
        return None, "Data desejada inválida."
    if d < date.today():
        return None, "A data desejada não pode estar no passado."
    return d.isoformat(), None


def validar_quantidade(valor: str) -> int | None:
    """Converte a quantidade. Retorna None se inválida.

    Aceita apenas inteiros de 1 a 99 escritos só com dígitos
    (rejeita '1.5', '-3', '1e2', 'abc', ' 100').
    """
    if not re.fullmatch(r"\d{1,2}", valor):
        return None
    qtd = int(valor)
    return qtd if QTD_MIN <= qtd <= QTD_MAX else None


def validar_pedido(form, sabores_por_id: dict) -> tuple[dict, list[str]]:
    """Valida o formulário de pedido.

    `sabores_por_id` vem do banco: {id: Row(nome, disponivel, ...)}.
    Retorna (dados_limpos, lista_de_erros).
    """
    erros: list[str] = []
    dados = {
        "nome_responsavel": texto(form.get("nome_responsavel")),
        "instituicao": texto(form.get("instituicao")),
        "telefone": normalizar_telefone(form.get("telefone")),
        "observacoes": texto(form.get("observacoes")),
    }

    for campo, rotulo in (("nome_responsavel", "Nome do responsável"), ("instituicao", "Instituição")):
        if not dados[campo]:
            erros.append(f"{rotulo} é obrigatório.")
        elif len(dados[campo]) > LIMITES[campo]:
            erros.append(f"{rotulo} deve ter no máximo {LIMITES[campo]} caracteres.")

    if not dados["telefone"]:
        erros.append("Telefone/WhatsApp é obrigatório.")
    elif not telefone_valido(dados["telefone"]):
        erros.append("Telefone/WhatsApp inválido. Informe com DDD, ex.: (62) 99999-8888.")

    if len(dados["observacoes"]) > LIMITES["observacoes"]:
        erros.append(f"Observações devem ter no máximo {LIMITES['observacoes']} caracteres.")

    dados["data_desejada"], erro_data = validar_data_desejada(texto(form.get("data_desejada")))
    if erro_data:
        erros.append(erro_data)

    # Itens: campos chamados qtd_<id_do_sabor>. Vazio ou "0" = não escolhido.
    itens = []
    for chave, valor in form.items():
        if not chave.startswith("qtd_"):
            continue
        valor = texto(valor)
        if valor in ("", "0"):
            continue
        id_texto = chave[4:]
        sabor = sabores_por_id.get(int(id_texto)) if id_texto.isdigit() else None
        if sabor is None:
            erros.append("Um dos sabores escolhidos não existe.")
            continue
        if not sabor["disponivel"]:
            erros.append(f"O sabor {sabor['nome']} está indisponível no momento.")
            continue
        qtd = validar_quantidade(valor)
        if qtd is None:
            erros.append(f"Quantidade inválida para {sabor['nome']}: use um número inteiro de {QTD_MIN} a {QTD_MAX}.")
            continue
        itens.append({"sabor_id": sabor["id"], "nome_sabor": sabor["nome"], "quantidade": qtd})

    if not itens and not erros:
        erros.append("Escolha pelo menos um sabor e informe a quantidade.")

    dados["itens"] = itens
    return dados, erros
