"""Descobre produtos sozinho, pelas listas de mais vendidos do Mercado Livre."""
from .mercadolivre import AcessoNegado, ErroML

BEBES = "MLB1384"
BRINQUEDOS = "MLB1132"

# Subcategorias que ficam de fora
EXCLUIDAS = {
    "MLB39965",  # Alimentos para Bebês (fórmulas, leites: NBCAL)
    "MLB432873",  # Hobbies (modelismo, adultos)
    "MLB457877",  # Miniaturas (colecionáveis)
    "MLB432991",  # Anti-stress
    "MLB39492",  # Pegadinhas
    "MLB255050",  # Lançadores de brinquedo
    "MLB432988",  # Jogos (sinuca, mesas de jogos: fora do nicho)
    "MLB437648",  # Jogos de salão
}

# Categoria do ML → categoria do bot (define o emoji do post)
MAPA = {
    "MLB5360": "alimentacao",
    "MLB420334": "higiene",
    "MLB420375": "higiene",
    "MLB1392": "brinquedo",
    "MLB3655": "brinquedo",
    "MLB420295": "gestante",
    "MLB420409": "passeio",
    "MLB420361": "quarto",
    "MLB1396": "roupa",
}


def descobrir(ml, por_categoria=15, log=print, brinquedos=6):
    """Retorna {id: {"tipo", "categoria", "pos"}} com os mais vendidos.

    Bebês tem prioridade: entram as subcategorias e as sub-subcategorias (ex.: Higiene →
    Fraldas), com mais itens por lista. Brinquedos entra com menos itens por categoria,
    para não dominar o canal.
    """
    alvos = [(BEBES, None, por_categoria)]
    try:
        for c, _ in ml.subcategorias(BEBES):
            if c in EXCLUIDAS:
                continue
            alvos.append((c, BEBES, por_categoria))
            try:
                alvos += [(n, c, por_categoria) for n, _ in ml.subcategorias(c) if n not in EXCLUIDAS]
            except ErroML:
                pass
    except ErroML as e:
        log(f"Aviso: não consegui listar subcategorias de Bebês: {e}")
    try:
        alvos += [(c, BRINQUEDOS, brinquedos) for c, _ in ml.subcategorias(BRINQUEDOS) if c not in EXCLUIDAS]
    except ErroML as e:
        log(f"Aviso: não consegui listar subcategorias de Brinquedos: {e}")
    achados = {}
    for cat, pai, qtd in alvos:
        try:
            lista = ml.mais_vendidos(cat)
        except (ErroML, AcessoNegado) as e:
            log(f"Aviso: mais vendidos de {cat}: {e}")
            continue
        # Só produtos de catálogo: anúncios avulsos são bloqueados para o token do app
        lista = [(t, i) for t, i in lista if t == "catalogo"]
        categoria = MAPA.get(cat) or MAPA.get(pai) or ("brinquedo" if pai == BRINQUEDOS else "outros")
        for pos, (tipo, pid) in enumerate(lista[:qtd]):
            atual = achados.get(pid)
            if atual is None:
                achados[pid] = {"tipo": tipo, "categoria": categoria, "pos": pos}
            else:
                atual["pos"] = min(atual.get("pos", pos), pos)
    log(f"Descoberta: {len(achados)} produtos em {len(alvos)} categorias.")
    return achados


# ---------- Universo infantil além de Bebês e Brinquedos (até ~14 anos) ----------
# O Mercado Livre não separa roupas, livros, esportes etc. por idade (só "Roupas para Bebês").
# Por isso a lista é fixa, conferida na árvore de categorias, e onde a categoria mistura
# adulto e criança o título precisa indicar que é infantil ("infantil").
# (área, id da categoria no ML, nome, itens por lista, regra: None | "infantil" | "game")
AREAS = [
    ("roupa", "MLB5366", "Roupas para Bebês", 15, None),
    ("roupa", "MLB271219", "Kits de Conjuntos de Roupa", 20, "infantil"),
    ("roupa", "MLB31447", "Camisetas e Regatas", 20, "infantil"),
    ("roupa", "MLB23332", "Tênis", 20, "infantil"),
    ("roupa", "MLB273770", "Sandálias e Chinelos", 20, "infantil"),
    ("roupa", "MLB430391", "Moda Praia", 20, "infantil"),
    ("roupa", "MLB12554", "Uniformes Escolares", 10, "infantil"),
    ("roupa", "MLB50657", "Fantasias Completas", 20, "infantil"),
    ("game", "MLB11172", "Consoles", 10, "game"),
    ("game", "MLB186456", "Video Games", 20, "game"),
    ("game", "MLB373768", "Acessórios para Nintendo", 10, "game"),
    ("game", "MLB6899", "Cartas Colecionáveis (Pokémon...)", 15, "game"),
    ("brinquedo", "MLB6883", "Jogos de Tabuleiro e Cartas", 10, None),
    ("livro", "MLB437616", "Livros Físicos", 20, "infantil"),
    ("escola", "MLB455745", "Material Escolar", 15, None),
    ("escola", "MLB455455", "Kits de Mochilas Escolares", 10, None),
    ("escola", "MLB3127", "Mochilas", 20, "infantil"),
    ("escola", "MLB412348", "Lancheiras", 10, None),
    ("esporte", "MLB1278", "Natação", 20, "infantil"),
    ("esporte", "MLB1286", "Futebol", 20, "infantil"),
    ("esporte", "MLB1292", "Ciclismo", 20, "infantil"),
    ("esporte", "MLB410723", "Patinetes e Scooters", 15, "infantil"),
    ("esporte", "MLB1293", "Patins e Skate", 15, "infantil"),
    ("esporte", "MLB2521", "Piscinas e Acessórios", 15, "infantil"),
    ("casa", "MLB439424", "Berços e Moisés", 10, None),
    ("casa", "MLB271691", "Dosséis para Camas e Berços", 10, None),
    ("casa", "MLB194206", "Redes de Proteção", 10, None),
    ("casa", "MLB270093", "Carteiras Escolares", 10, None),
    ("casa", "MLB189188", "Luminárias", 20, "infantil"),
    ("casa", "MLB1609", "Roupa de Cama", 20, "infantil"),
    ("casa", "MLB9163", "Tapetes", 20, "infantil"),
    ("casa", "MLB436392", "Jogos e Sets de Móveis", 20, "infantil"),
    ("festa", "MLB256810", "Artigos para Festas", 20, "infantil"),
    ("festa", "MLB50656", "Decoração de Festa", 20, "infantil"),
    ("festa", "MLB40189", "Lembrancinhas", 15, "infantil"),
]


def explorar_areas(ml=None, log=print):
    """{area: [(cat_id, nome, regra, qtd)]}"""
    res = {}
    for area, cat, nome, qtd, regra in AREAS:
        res.setdefault(area, []).append((cat, nome, regra, qtd))
    return res


def descobrir_areas(ml, log=print):
    """Mais vendidos das áreas novas. Retorna {id: {"tipo", "categoria", "pos", "regra"}}."""
    achados = {}
    for area, cat, _, qtd, regra in AREAS:
        try:
            lista = [(t, i) for t, i in ml.mais_vendidos(cat) if t == "catalogo"]
        except (ErroML, AcessoNegado) as e:
            log(f"Aviso: mais vendidos de {cat}: {e}")
            continue
        for pos, (tipo, pid) in enumerate(lista[:qtd]):
            if pid not in achados:
                achados[pid] = {"tipo": tipo, "categoria": area, "pos": pos}
                if regra:
                    achados[pid]["regra"] = regra
    log(f"Áreas novas: {len(achados)} produtos.")
    return achados
