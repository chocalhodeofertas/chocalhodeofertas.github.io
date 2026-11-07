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
    "MLB432988": "jogo",
    "MLB437648": "jogo",
}


def categoria_do_bot(cat_ml, pai):
    if cat_ml in MAPA:
        return MAPA[cat_ml]
    return "brinquedo" if pai == BRINQUEDOS else "outros"


def descobrir(ml, por_categoria=8, log=print):
    """Retorna {id: {"tipo", "categoria"}} com os mais vendidos de cada subcategoria."""
    alvos = [(BEBES, None)]
    for pai in (BEBES, BRINQUEDOS):
        try:
            alvos += [(c, pai) for c, _ in ml.subcategorias(pai) if c not in EXCLUIDAS]
        except ErroML as e:
            log(f"Aviso: não consegui listar subcategorias de {pai}: {e}")
    achados = {}
    for cat, pai in alvos:
        try:
            lista = ml.mais_vendidos(cat)
        except (ErroML, AcessoNegado) as e:
            log(f"Aviso: mais vendidos de {cat}: {e}")
            continue
        # Só produtos de catálogo: anúncios avulsos são bloqueados para o token do app
        lista = [(t, i) for t, i in lista if t == "catalogo"]
        for pos, (tipo, pid) in enumerate(lista[:por_categoria]):
            atual = achados.get(pid)
            if atual is None:
                achados[pid] = {"tipo": tipo, "categoria": categoria_do_bot(cat, pai), "pos": pos}
            else:
                atual["pos"] = min(atual.get("pos", pos), pos)
    log(f"Descoberta: {len(achados)} produtos em {len(alvos)} categorias.")
    return achados
