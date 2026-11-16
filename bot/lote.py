"""Links oficiais (meli.la) pelo Linkbuilder do painel de afiliados, em lote.

1. Uma vez por dia, o bot manda no privado um bloco com as URLs das melhores
   ofertas que ainda não têm link oficial.
2. Você cola o bloco no Linkbuilder, clica em Gerar e manda os links de volta.
3. O bot associa os links na mesma ordem e guarda para sempre.
"""
import html
import re

LINKBUILDER = "https://www.mercadolivre.com.br/afiliados/linkbuilder"
RE_MELI = re.compile(r"https?://meli\.la/[A-Za-z0-9]+")


def url_linkbuilder(item_id):
    """Endereço de anúncio, que é o formato que o Linkbuilder aceita."""
    return f"https://produto.mercadolivre.com.br/MLB-{item_id[3:]}-produto-_JM"


def prioridade(oferta, posicao=None, agora=None):
    from .ofertas import pontuacao

    return pontuacao(oferta, posicao, agora)


def _chave_do_lote(estado, agora):
    """Ordem em que os produtos sem link entram no lote (a mesma que a página da fila mostra)."""
    from . import espelho
    from . import estado as est

    pos = {pid: d.get("pos") for pid, d in estado.get("descobertos", {}).items()}

    def chave(x):
        o = x[0]
        peso = prioridade(o, pos.get(o.id), agora)
        if espelho.eh_do_espelho(estado, o.id):
            peso *= 1.5   # candidato de canal vale só 48 h: precisa do link logo
        if est.repetido(estado, o.titulo, agora, 7, o.preco):
            peso *= 0.4   # parecido com algo postado na semana: não sairia agora de qualquer jeito
        return peso

    return chave


def resumo_fila(estado, sem_link, agora, n=25):
    """Retrato dos produtos aprovados que esperam o link oficial, na ordem do lote, para a página da fila."""
    from . import espelho

    no_lote = set((estado.get("lote") or {}).get("ids") or [])
    itens, vistos = [], set()
    for o, item in sorted(sem_link, key=_chave_do_lote(estado, agora), reverse=True):
        if o.id in vistos or o.id in estado["links"] or not item:
            continue
        vistos.add(o.id)
        if len(itens) < n:
            itens.append({"id": o.id, "titulo": (o.titulo or "")[:80], "preco": o.preco,
                          "desconto": round(getattr(o, "desconto", 0) or 0, 3),
                          "espelho": bool(espelho.eh_do_espelho(estado, o.id)), "no_lote": o.id in no_lote})
    return {"em": agora.isoformat(timespec="minutes"), "total": len(vistos), "itens": itens}


def montar_lote(estado, sem_link, tamanho, agora):
    """sem_link: lista de (oferta, item_id). Grava o lote pendente e devolve as URLs."""
    escolhidas, vistos = [], set()
    from .ofertas import tipo_produto

    chave = _chave_do_lote(estado, agora)
    por_tipo = {}
    for o, item in sorted(sem_link, key=chave, reverse=True):
        if o.id in vistos or o.id in estado["links"] or not item:
            continue
        tp = tipo_produto(o.titulo)
        if por_tipo.get(tp, 0) >= 2:  # no máximo 2 do mesmo tipo por lote: mais variedade
            continue
        por_tipo[tp] = por_tipo.get(tp, 0) + 1
        vistos.add(o.id)
        escolhidas.append((o.id, url_linkbuilder(item)))
        if len(escolhidas) >= tamanho:
            break
    if not escolhidas:
        return []
    estado["lote"] = {
        "dia": agora.date().isoformat(),
        "ids": [pid for pid, _ in escolhidas],
        "urls": [u for _, u in escolhidas],
    }
    return [u for _, u in escolhidas]


def conferir_anuncio(estado, pid, info, log=print, procurar=None):
    """O link oficial de um produto de catálogo abre UM anúncio (o que venceu quando o lote foi montado).
    Se esse anúncio não está mais ativo no catálogo (pausado, sem estoque, saiu), o link é descartado:
    o produto volta para a fila do lote com o anúncio que vende agora. Se está ativo, o preço do post
    passa a ser o DESSE anúncio (é ele que a pessoa vai ver ao tocar no link).
    Retorna False quando o link foi descartado.
    procurar(pid, item, total): consulta as páginas seguintes do catálogo quando ele tem mais de 20 anúncios."""
    item = (estado.get("links_item") or {}).get(pid)
    if not item or not info or not getattr(info, "ativos", None) or pid not in estado.get("links", {}):
        return True  # link antigo (sem anúncio anotado) ou catálogo não consultado: segue como antes
    if item not in info.ativos and getattr(info, "total", 0) > len(info.ativos):
        if procurar is None:
            return True  # não dá para saber: não descarta
        try:
            achado = procurar(pid, item, info.total)
        except Exception:  # noqa: BLE001 — sem conferir, mantém o link
            return True
        if achado:
            info.ativos[item] = achado
    if item not in info.ativos:
        del estado["links"][pid]
        del estado["links_item"][pid]
        log(f"{pid}: o anúncio do link oficial ({item}) não está mais ativo; link descartado, volta para o lote.")
        return False
    preco, de = info.ativos[item]
    info.preco, info.preco_original, info.item_id = preco, de, item
    return True


def texto_lote(urls, numero=1, total=1):
    return (
        f"🔗 <b>Lote {numero} de até {total} hoje: {len(urls)} ofertas sem link oficial</b>\n\n"
        f"1. Toque no bloco abaixo para copiar\n"
        f'2. Abra o <a href="{LINKBUILDER}">Linkbuilder</a>, cole e toque em <b>Gerar</b>\n'
        f"3. Copie todos os links gerados e mande aqui, numa mensagem só\n\n"
        f"<pre>{html.escape(chr(10).join(urls))}</pre>"
    )


def aplicar_resposta(estado, texto):
    """Associa os meli.la do texto ao lote pendente. Retorna (ok, mensagem)."""
    links = RE_MELI.findall(texto or "")
    lote = estado.get("lote")
    extra = estado.get("lote_extra")
    if not links:
        return False, None
    if extra and len(links) == len(extra["ids"]) and not (lote and len(links) == len(lote["ids"])):
        for pid, link in zip(extra["ids"], links):
            estado["links"][pid] = link
        estado["lote_extra"] = None
        return True, f"✅ {len(links)} links da sua busca salvos! Entram no canal nas próximas rodadas."
    if not lote:
        return False, "Recebi links, mas não há nenhum lote pendente."
    if len(links) != len(lote["ids"]):
        return False, (
            f"⚠️ Recebi {len(links)} links, mas o lote tem {len(lote['ids'])} produtos. "
            "Para não trocar um produto pelo outro, não salvei nada. "
            "Gere de novo com o bloco inteiro e mande todos os links juntos."
        )
    anuncios = estado.setdefault("links_item", {})
    for pid, link, url in zip(lote["ids"], links, lote.get("urls") or [None] * len(links)):
        estado["links"][pid] = link
        m = re.search(r"MLB-(\d+)", url or "")
        if m:
            anuncios[pid] = "MLB" + m.group(1)  # o link oficial abre este anúncio (não o catálogo inteiro)
    estado["lote"] = None
    return True, (f"✅ {len(links)} links oficiais salvos ({len(estado['links'])} no total)! "
                  "Começo a postar nas próximas rodadas. Se ainda houver lote hoje, ele chega em até 20 min.")
