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
# Cada área: categoria do bot, nome da categoria raiz no ML, nomes de subcategorias que entram
# (None = todas), itens por lista, e se o título precisa indicar que é infantil.
AREAS = [
    ("roupa", r"calcados.*roupas", r"infant|crianc|menin|bebe|juvenil|kids|fantasia|escolar", 8, False),
    ("game", r"^games", None, 6, False),
    ("game", r"brinquedos", r"carta|colecion|trading|figurinha|album", 6, False),  # Pokémon, figurinhas
    ("livro", r"livros", r"infant|juvenil|crianc|colorir|didatic|escolar", 8, False),
    ("escola", r"papelaria", r"escolar|papelaria|desenho|pintura|lapis|caderno|mochila|estojo|cartolina|massinha", 6, False),
    ("esporte", r"esportes", r"natacao|futebol|patin|skate|ciclismo|bicicleta|piscina", 6, True),
    ("casa", r"casa.*moveis", r"infant|crianc|bebe|kids", 8, False),
    ("festa", r"festas", None, 6, True),
]
MAX_CATS_AREA = 12


def _norm(t):
    from .filtros import normalizar

    return normalizar(t)


def explorar_areas(ml, log=print):
    """Acha, pelo nome, as categorias do ML de cada área. Retorna {area: [(cat_id, nome, exige_infantil, qtd)]}."""
    import re

    try:
        raizes = ml.categorias_raiz()
    except ErroML as e:
        log(f"Aviso: não consegui listar as categorias do ML: {e}")
        return {}
    res = {}
    for area, raiz_re, sub_re, qtd, exige in AREAS:
        raiz = next(((c, n) for c, n in raizes if re.search(raiz_re, _norm(n))), None)
        if not raiz:
            log(f"Aviso: área {area}: categoria raiz não encontrada.")
            continue
        cats = []
        try:
            filhos = ml.subcategorias(raiz[0])
        except ErroML:
            filhos = []
        for c, n in filhos:
            if len(cats) >= MAX_CATS_AREA:
                break
            if sub_re is None or re.search(sub_re, _norm(n)):
                cats.append((c, n, exige, qtd))
                continue
            # olha um nível abaixo (ex.: Roupas → Roupas Infantis)
            try:
                netos = ml.subcategorias(c)
            except ErroML:
                netos = []
            for c2, n2 in netos:
                if len(cats) < MAX_CATS_AREA and re.search(sub_re, _norm(n2)):
                    cats.append((c2, f"{n} › {n2}", exige, qtd))
        res.setdefault(area, []).extend(c for c in cats if c[0] not in {x[0] for x in res.get(area, [])})
    return res


def descobrir_areas(ml, log=print):
    """Mais vendidos das áreas novas. Retorna {id: {"tipo", "categoria", "pos", "exige_infantil"}}."""
    achados = {}
    for area, cats in explorar_areas(ml, log).items():
        for cat, _, exige, qtd in cats:
            try:
                lista = [(t, i) for t, i in ml.mais_vendidos(cat) if t == "catalogo"]
            except (ErroML, AcessoNegado) as e:
                log(f"Aviso: mais vendidos de {cat}: {e}")
                continue
            for pos, (tipo, pid) in enumerate(lista[:qtd]):
                if pid not in achados:
                    achados[pid] = {"tipo": tipo, "categoria": area, "pos": pos}
                    if exige:
                        achados[pid]["exige_infantil"] = True
    log(f"Áreas novas: {len(achados)} produtos.")
    return achados
