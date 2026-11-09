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
