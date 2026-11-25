# Frutos de Goiás: sistema de pedidos

Projeto Integrador III-A, Análise e Desenvolvimento de Sistemas, PUC Goiás.

Aplicação **cliente-servidor** de consulta de informações e registro de pedidos para a sorveteria
**Frutos de Goiás** (Galvão e França Comércio de Alimentos LTDA). A comunicação entre navegador e
servidor é **criptografada com HTTPS/TLS**.

- **Clientes** (empresas e escolas) consultam o catálogo de sabores, fazem um pedido informando
  sabor e quantidade e depois acompanham o status do pedido.
- **Donos** entram com usuário e senha, veem os pedidos, mudam o status
  (Novo → Em separação → Pronto → Entregue, ou Cancelado), imprimem as listas de separação e
  gerenciam os sabores.

Não há pagamento online.

A arquitetura, as rotas, o fluxo do pedido e os mecanismos de segurança estão em
[docs/arquitetura.md](docs/arquitetura.md).

---

## Tecnologias

| Camada | Tecnologia |
|---|---|
| Servidor | Python 3.11+ com Flask (templates Jinja2) |
| Banco de dados | SQLite pelo módulo `sqlite3` da biblioteca padrão (sem ORM) |
| Interface | HTML + CSS responsivo (mobile first), JavaScript mínimo |
| Segurança | TLS (`ssl` + certificado gerado com `cryptography`), Flask-WTF (CSRF), `werkzeug.security` (hash de senha) |
| Configuração | `python-dotenv` (arquivo `.env`) |
| Testes | pytest |

## Estrutura

```
frutos-de-goias/
├── app/
│   ├── __init__.py         # fábrica da aplicação, configuração, comando criar-admin
│   ├── db.py               # conexão SQLite
│   ├── schema.sql          # tabelas
│   ├── seguranca.py        # cabeçalhos, login obrigatório, limite de tentativas, validação
│   ├── rotas_publicas.py   # catálogo, pedido, consulta
│   ├── rotas_admin.py      # login, pedidos, status, impressão, sabores
│   ├── templates/          # páginas HTML (Jinja2)
│   └── static/             # CSS, JS e ícone
├── tests/                  # testes automatizados (pytest)
├── docs/arquitetura.md     # documentação técnica
├── gerar_certificado.py    # gera o certificado TLS autoassinado
├── seed.py                 # cadastra os sabores iniciais
├── servidor.py             # inicia o servidor HTTPS
├── requirements.txt
└── .env.example            # modelo de configuração
```

---

## Passo a passo no Windows

Os comandos abaixo são para o **PowerShell**, executados dentro da pasta do projeto.

### 1. Requisitos

- Python 3.11 ou mais novo ([python.org](https://www.python.org/downloads/)).
  Na instalação, marque **"Add Python to PATH"**.
- Confira no PowerShell:

  ```powershell
  python --version
  ```

### 2. Criar e ativar o ambiente virtual

```powershell
python -m venv venv
.\venv\Scripts\Activate.ps1
```

Se aparecer o erro *"a execução de scripts foi desabilitada neste sistema"*, rode uma vez:

```powershell
Set-ExecutionPolicy -Scope CurrentUser RemoteSigned
```

Depois ative de novo. Com o ambiente ativo, a linha do terminal começa com `(venv)`.

### 3. Instalar as dependências

```powershell
pip install -r requirements.txt
```

### 4. Criar o arquivo `.env`

```powershell
Copy-Item .env.example .env
python -c "import secrets; print(secrets.token_hex(32))"
```

Abra o `.env` no Bloco de Notas (`notepad .env`) e troque `troque-esta-chave` pela chave que o
comando acima imprimiu. A aplicação **não inicia** sem uma `SECRET_KEY` própria.

### 5. Gerar o certificado HTTPS

Descubra o IP do PC na rede Wi-Fi:

```powershell
ipconfig
```

Procure a linha **"Endereço IPv4"** do adaptador Wi-Fi (ex.: `192.168.0.15`) e gere o certificado
incluindo esse IP:

```powershell
python gerar_certificado.py --ip 192.168.0.15
```

Isso cria `certs/cert.pem` e `certs/key.pem`. Sem o `--ip`, o certificado vale só para
`localhost` e `127.0.0.1`. **Se o IP do PC mudar, gere o certificado de novo.**

### 6. Cadastrar os sabores iniciais

```powershell
python seed.py
```

Pode rodar mais de uma vez: sabores já existentes não são duplicados.

### 7. Criar o usuário do dono

```powershell
flask criar-admin
```

O comando pede usuário e senha (mínimo de 8 caracteres; a senha não aparece enquanto você digita).
Rodar de novo com o mesmo usuário **redefine a senha**.

### 8. Iniciar o servidor

```powershell
python servidor.py
```

O terminal mostra os endereços de acesso. Para parar, use `Ctrl+C`.

Na primeira vez, o Windows pode perguntar se o Python pode usar a rede. Marque **Redes privadas**
e clique em **Permitir acesso**. Sem isso, o celular não consegue conectar.

---

## Como acessar

### Pelo PC

- Site dos clientes: <https://localhost:5000>
- Área do dono: <https://localhost:5000/admin/login>

### Pelo celular (mesma rede Wi-Fi)

1. O celular precisa estar **no mesmo Wi-Fi** que o PC.
2. No navegador do celular, acesse `https://IP-DO-PC:5000` (ex.: `https://192.168.0.15:5000`).
   Use `https://`; `http://` não funciona.
3. Se não abrir, confira se a rede do Windows está como **Rede privada** e se o firewall permitiu
   o Python (passo 8).

### Aviso de certificado autoassinado (esperado)

Na primeira vez, o navegador mostra um aviso como **"Sua conexão não é particular"**
(`NET::ERR_CERT_AUTHORITY_INVALID`). Isso acontece porque o certificado foi gerado por nós e não
por uma autoridade certificadora reconhecida (como Let's Encrypt). **A conexão continua
criptografada.** O navegador só não consegue confirmar a identidade do servidor.

Para continuar:

- **Chrome / Edge (PC e Android):** *Avançado* → *Continuar para … (não seguro)*.
- **Firefox:** *Avançado* → *Aceitar o risco e continuar*.
- **Safari (iPhone):** *Mostrar detalhes* → *visitar este site* → confirmar.

Em produção, com um domínio próprio, o certificado autoassinado seria trocado por um certificado
gratuito do Let's Encrypt e o aviso desapareceria. O resto do código continua igual.

---

## Rodando os testes

Com o ambiente virtual ativo:

```powershell
python -m pytest
```

Para ver o nome de cada teste:

```powershell
python -m pytest -v
```

Os testes usam um banco temporário próprio e não mexem no banco real. Eles cobrem, entre outros:
criação de pedido válido; recusa de sabor indisponível, sabor inexistente e quantidade inválida;
validação dos campos; área do dono bloqueada sem login; senha errada; bloqueio após 5 falhas;
CSRF ativo; mudança de status; impressão; filtros; cabeçalhos de segurança; cookies seguros;
tentativa de injeção de SQL.

---

## Uso no dia a dia

**Cliente:** abre o site → *Fazer pedido* → informa as quantidades e os dados → *Enviar pedido* →
anota o número. Para acompanhar, usa *Meu pedido* com o número e o telefone.

**Dono:** *Área do dono* (link no rodapé) → *Pedidos*:

- Atalho **"Novos de hoje"**, ou filtros por status, data do pedido, data de retirada e instituição.
- **Imprimir N pedido(s) da lista** imprime todos os pedidos filtrados, um por folha.
- Ao abrir um pedido: *Imprimir pedido*, *Marcar como "Em separação"* etc., ou *Cancelar pedido*.
  Também dá para voltar um passo, caso tenha clicado errado.
- *Sabores*: liga e desliga a disponibilidade com um toque, adiciona sabores e edita nome e
  categoria.

## Configurações (`.env`)

| Variável | Para quê | Padrão |
|---|---|---|
| `SECRET_KEY` | assina o cookie de sessão e os tokens CSRF | **obrigatória** |
| `DATABASE` | caminho do banco SQLite | `instance/sorveteria.db` |
| `PORTA` | porta do servidor HTTPS | `5000` |
| `CERT_ARQUIVO` / `CHAVE_ARQUIVO` | certificado e chave TLS | `certs/cert.pem` / `certs/key.pem` |
