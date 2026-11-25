"""Popula o banco com os sabores iniciais da sorveteria.

Uso:  python seed.py

Pode ser executado mais de uma vez: sabores que já existem (mesmo nome)
são ignorados, então nada é duplicado e as alterações feitas pelo dono
na área administrativa são preservadas.
"""

SABORES = {
    "Tradicionais": [
        "Abacate", "Abacaxi", "Abacaxi ao Leite", "Açaí", "Amendoim", "Amora", "Araticum",
        "Banana", "Buriti", "Cagaita", "Cajamanga", "Cajuzinho", "Castanha de Caju",
        "Castanha do Pará", "Chocolate", "Ciriguela", "Coalhada", "Coco Branco",
        "Coco Queimado", "Cupuaçu", "Flocos", "Goiaba", "Graviola", "Groselha",
        "Jabuticaba", "Jaca", "Kiwi", "Leite Condensado", "Lichia", "Limão Fruta",
        "Limão Suíço", "Mamão", "Manga", "Mangaba", "Maracujá", "Maracujá ao Leite",
        "Melancia", "Milho Verde", "Morango Fruta", "Morango ao Leite", "Murici",
        "Olho de Sogra", "Pequi", "Romeu e Julieta", "Tamarindo", "Taperebá", "Tapioca",
        "Umbu", "Uva",
    ],
    "Premium": [
        "Açaí com Cupuaçu", "Açaí com Ninho", "Açaí com Tapioca", "Alfajor",
        "Avelã com Chocolate", "Bacuri", "Baru", "Brigadeiro", "Chocolate Branco",
        "Chocomenta", "Coco Verde", "Doce de Leite", "Frutas do Bosque", "Maltine", "Ninho",
        "Ninho com Abacaxi", "Ninho com Coco", "Ninho com Morango", "Ninho Trufado",
        "Passas ao Rum", "Pé de Moleque", "Skimó", "Tentação", "Torta de Limão",
        "Torta de Maracujá",
    ],
    "Especiais": [
        "Chocolate Belga", "Cookies Cream", "Morango em Pedaços", "Pistache",
        "Pistache Zero", "Ninho com Pistache",
    ],
    "Kids": [
        "Kids Chiclete", "Kids Chocolate", "Kids Groselha", "Kids Mar Azul", "Kids Morango",
        "Kids Uva",
    ],
    "Paletas": [
        "Paleta Açaí", "Paleta Chocolate", "Paleta Coco", "Paleta Maracujá", "Paleta Morango",
        "Paleta Ninho",
    ],
    "Zero Açúcar": [
        "Abacaxi Zero", "Açaí Zero", "Cajamanga Zero", "Chocolate Zero", "Coco Zero",
        "Morango Zero", "Ninho com Morango Zero", "Ninho Zero", "Uva Zero",
    ],
}


def popular(con) -> int:
    """Insere os sabores que ainda não existem. Retorna quantos foram inseridos."""
    inseridos = 0
    for categoria, nomes in SABORES.items():
        for nome in nomes:
            cur = con.execute(
                "INSERT OR IGNORE INTO sabores (nome, categoria, disponivel) VALUES (?, ?, 1)",
                (nome, categoria),
            )
            inseridos += cur.rowcount
    con.commit()
    return inseridos


if __name__ == "__main__":
    from app import create_app
    from app.db import get_db

    app = create_app()
    with app.app_context():
        n = popular(get_db())
        total = get_db().execute("SELECT COUNT(*) FROM sabores").fetchone()[0]
    print(f"{n} sabores inseridos. Total no catálogo: {total}.")
