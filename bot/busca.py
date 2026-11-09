"""Buscas sob demanda: `buscar <termo>`, `pegar 1 3`, `vigiar <termo>`."""
import html
from datetime import timedelta

from . import lote
from .filtros import fora_da_faixa, motivo_bloqueio
from .mensagens import brl
from .mercadolivre import AcessoNegado, ErroML

MAX_RESULTADOS = 8
VIGIAS_A_CADA = timedelta(hours=2)


def pesquisar(ml, termo, log=print):
    """Junta a busca do catálogo com os mais vendidos da categoria do termo. Retorna lista de dicts."""
    ids, ranking = [], {}
    try:
        cat, _ = ml.categoria_da_busca(termo)
        if cat:
            mv = [i for t, i in ml.mais_vendidos(cat) if t == "catalogo"]
            ranking = {pid: k for k, pid in enumerate(mv)}
    except (ErroML, AcessoNegado) as e:
        log(f"Aviso: categoria da busca: {e}")
        cat = None
    try:
        ids = [pid for pid, _ in ml.buscar_produtos(termo, 12)]
    except (ErroML, AcessoNegado) as e:
        log(f"Aviso: busca no catálogo: {e}")
    palavras = [w for w in termo.lower().split() if len(w) > 2]
    # mais vendidos da categoria que também batem com o termo entram na lista
    extras = list(ranking)[:15]
    vistos, res = set(), []
    for pid in ids + extras:
        if pid in vistos or len(res) >= 14:
            continue
        vistos.add(pid)
        try:
            info = ml.catalogo(pid)
        except (ErroML, AcessoNegado):
            continue
        if not info or not info.disponivel or not info.preco or not info.titulo:
            continue
        if pid not in ids and palavras and not any(w in info.titulo.lower() for w in palavras):
            continue
        if motivo_bloqueio(info.titulo):
            continue
        preco = float(info.preco)
        de = float(info.preco_original) if (info.preco_original or 0) > preco else None
        res.append({"id": pid, "titulo": info.titulo, "preco": preco, "de": de,
                    "desconto": (1 - preco / de) if de else 0.0, "rank": ranking.get(pid),
                    "item_id": info.item_id, "categoria": cat})
    res.sort(key=lambda r: (-(r["desconto"] or 0) * (1.5 if r["rank"] is not None and r["rank"] < 10 else 1)))
    return res[:MAX_RESULTADOS]


def buscar(termo, ml, estado, log=print):
    termo = termo.strip()
    if len(termo) < 3:
        return "Mande <b>buscar</b> + o que procura. Ex.: <b>buscar cadeirinha isofix</b>"
    res = pesquisar(ml, termo, log)
    if not res:
        return f"Não encontrei “{html.escape(termo)}” disponível agora."
    estado["busca"] = {"termo": termo, "itens": res}
    linhas = [f"🔎 <b>{html.escape(termo)}</b> — melhores resultados agora:", ""]
    for k, r in enumerate(res, 1):
        preco = f"de {brl(r['de'])} por <b>{brl(r['preco'])}</b> (-{round(r['desconto'] * 100)}%)" if r["de"] \
            else f"<b>{brl(r['preco'])}</b> (sem desconto)"
        fogo = f" 🔥 top {r['rank'] + 1} mais vendidos" if r["rank"] is not None and r["rank"] < 20 else ""
        linhas.append(f"{k}. {html.escape(r['titulo'][:70])}\n   {preco}{fogo}\n"
                      f"   https://www.mercadolivre.com.br/p/{r['id']}")
    linhas += ["", "Para usar: <b>pegar 1 3</b> (os números). Eu mando o lote para o Linkbuilder e, "
               "quando você devolver os links, eles entram no canal."]
    return "\n".join(linhas)


def pegar(texto, tg, estado, cfg, agora):
    busca = estado.get("busca") or {}
    itens = busca.get("itens") or []
    nums = [int(x) for x in texto.replace(",", " ").split() if x.isdigit()]
    escolhidos = [itens[n - 1] for n in nums if 1 <= n <= len(itens)]
    if not escolhidos:
        return "Mande <b>pegar</b> + os números da última busca. Ex.: <b>pegar 1 3</b>"
    for r in escolhidos:
        estado.setdefault("manuais", {})[r["id"]] = {"tipo": "catalogo", "categoria": "outros", "pedido": True}
    sem_link = [r for r in escolhidos if r["id"] not in estado.get("links", {}) and r.get("item_id")]
    if not sem_link:
        return "✅ Esses produtos já têm link; entram no canal quando estiverem em promoção."
    urls = [lote.url_linkbuilder(r["item_id"]) for r in sem_link]
    estado["lote_extra"] = {"dia": agora.date().isoformat(), "ids": [r["id"] for r in sem_link], "urls": urls}
    tg.enviar_texto(cfg.admin_chat, lote.texto_lote(urls).replace("Lote 1 de até 1 hoje", "Lote da sua busca"),
                    html=True)
    return None


def vigiar(termo, estado):
    termo = " ".join(termo.split()).lower()
    if len(termo) < 3:
        return "Mande <b>vigiar</b> + o produto. Ex.: <b>vigiar carrinho travel system</b>"
    estado.setdefault("vigias", {})[termo] = {"ids": []}
    estado["vigias_em"] = None  # busca na próxima rodada
    return (f"👀 Vigiando “{html.escape(termo)}”. Quando aparecer uma promoção boa, eu te aviso e ela entra "
            "no próximo lote do Linkbuilder. Ver todos: <b>vigias</b> · parar: <b>parar " + html.escape(termo) + "</b>")


def listar_vigias(estado):
    v = estado.get("vigias") or {}
    if not v:
        return "Nenhum produto sendo vigiado. Use <b>vigiar</b> + o produto."
    return "👀 <b>Vigiando:</b>\n" + "\n".join(f"• {html.escape(t)}" for t in v)


def parar(termo, estado):
    termo = " ".join(termo.split()).lower()
    if (estado.get("vigias") or {}).pop(termo, None) is None:
        return f"Não estava vigiando “{html.escape(termo)}”. Veja a lista com <b>vigias</b>."
    return f"✅ Parei de vigiar “{html.escape(termo)}”."


def atualizar_vigias(ml, estado, agora, log=print):
    """A cada 2h, procura os termos vigiados e põe os produtos na lista do bot (com prioridade)."""
    vigias = estado.get("vigias") or {}
    ultima = estado.get("vigias_em")
    if not vigias or (ultima and agora - _dt(ultima) < VIGIAS_A_CADA):
        return
    estado["vigias_em"] = agora.isoformat(timespec="minutes")
    for termo, d in vigias.items():
        try:
            ids = [pid for pid, _ in ml.buscar_produtos(termo, 8)]
        except (ErroML, AcessoNegado) as e:
            log(f"Aviso: vigia '{termo}': {e}")
            continue
        d["ids"] = ids
        for pid in ids:
            estado.setdefault("manuais", {}).setdefault(pid, {"tipo": "catalogo", "categoria": "outros"})
            estado["manuais"][pid]["vigia"] = termo


def _dt(s):
    from datetime import datetime

    return datetime.fromisoformat(s)
