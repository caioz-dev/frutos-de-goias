-- Esquema do banco SQLite da sorveteria.
-- "IF NOT EXISTS" permite executar este script toda vez que o app inicia.

PRAGMA foreign_keys = ON;

-- Usuários da área administrativa (os donos). A senha NUNCA é guardada,
-- apenas o hash gerado por werkzeug.security (scrypt com salt aleatório).
CREATE TABLE IF NOT EXISTS usuarios (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    usuario     TEXT    NOT NULL UNIQUE,
    senha_hash  TEXT    NOT NULL,
    criado_em   TEXT    NOT NULL
);

-- Catálogo de sabores.
CREATE TABLE IF NOT EXISTS sabores (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    nome        TEXT    NOT NULL UNIQUE COLLATE NOCASE,
    categoria   TEXT    NOT NULL,
    disponivel  INTEGER NOT NULL DEFAULT 1 CHECK (disponivel IN (0, 1))
);

-- Pedidos feitos pelos clientes (empresas/escolas).
CREATE TABLE IF NOT EXISTS pedidos (
    id                INTEGER PRIMARY KEY AUTOINCREMENT,
    nome_responsavel  TEXT    NOT NULL,
    instituicao       TEXT    NOT NULL,
    telefone          TEXT    NOT NULL,   -- só dígitos, ex.: 62999998888
    data_desejada     TEXT,               -- AAAA-MM-DD (opcional)
    observacoes       TEXT    NOT NULL DEFAULT '',
    status            TEXT    NOT NULL DEFAULT 'Novo'
                      CHECK (status IN ('Novo', 'Em separação', 'Pronto', 'Entregue', 'Cancelado')),
    criado_em         TEXT    NOT NULL,   -- AAAA-MM-DD HH:MM:SS (horário local)
    atualizado_em     TEXT    NOT NULL
);

-- Itens de cada pedido. O nome do sabor é copiado no momento do pedido para
-- que uma edição posterior no catálogo não altere pedidos antigos.
CREATE TABLE IF NOT EXISTS itens_pedido (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    pedido_id   INTEGER NOT NULL REFERENCES pedidos (id) ON DELETE CASCADE,
    sabor_id    INTEGER REFERENCES sabores (id),
    nome_sabor  TEXT    NOT NULL,
    quantidade  INTEGER NOT NULL CHECK (quantidade BETWEEN 1 AND 99)
);

CREATE INDEX IF NOT EXISTS idx_pedidos_criado ON pedidos (criado_em);
CREATE INDEX IF NOT EXISTS idx_itens_pedido ON itens_pedido (pedido_id);
