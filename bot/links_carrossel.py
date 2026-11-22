"""Links de afiliado de cada carrossel, entregues ao admin no Telegram (pedido do Leonardo, 21/11).

Toda vez que um carrossel é gerado, o admin recebe UMA mensagem com o link de cada produto, na ordem
dos slides, para guardar e responder os pedidos de link nos comentários (Instagram/TikTok).

Duas entradas:
- `do_carrossel(titulo, ofertas)`: carrosséis do próprio bot (pacote do dia, "carrossel <tema>");
  as ofertas já vêm com o link oficial.
- `processar(...)`: carrosséis montados fora do bot (pelo Claude). O pedido fica em
  `pedidos/carrosseis.json` (lista de {"id", "titulo", "itens": [{"id", "nome"}]}; id = MLB... do
  catálogo ou itemId da Shopee). A cada rodada: link da Shopee pela API (etiqueta "tiktok"),
  link oficial do ML que já existe em `estado.links`; o que faltar no ML vai num lote do Linkbuilder
  (`estado.lote_extra`). Quando os links voltam, sai a mensagem completa. Pedido feito fica em
  `estado.carrosseis_links` (não repete). Nada aqui abre link de afiliado.
"""
import json
from datetime import datetime
from pathlib import Path

from . import lote

PEDIDOS = Path(__file__).resolve().parent.parent / "pedidos" / "carrosseis.json"
ETIQUETA = "tiktok"
VALIDADE_DIAS = 7  # pedido sem todos os links depois disso: para de esperar
LOTE_DIAS = 3  # lote do Linkbuilder sem resposta depois disso: libera para outro


def mensagem(titulo, itens, completo=True):
    """itens: lista de (nome, link ou None[, id]). Texto simples, fácil de copiar."""
    faltam = sum(1 for it in itens if not it[1])
    topo = "🔗 Links do carrossel" if completo or not faltam else "🔗 Links do carrossel (parcial)"
    linhas = [f"{topo}: {titulo}", "Guarde esta mensagem para responder os comentários.", ""]
    for k, it in enumerate(itens, 1):
        nome, link = it[0], it[1]
        shopee = len(it) > 2 and _e_shopee(it[2])
        linhas.append(f"{k}. {nome}")
        linhas.append(link or ("⚠️ não consegui gerar o link da Shopee agora" if shopee
                               else "⏳ falta o link oficial (lote do Linkbuilder logo abaixo)"))
        linhas.append("")
    linhas.append("#publi")
    return "\n".join(linhas)


def _curto(titulo, limite=60):
    t = " ".join((titulo or "").split())
    return t if len(t) <= limite else t[:limite].rsplit(" ", 1)[0] + "…"


def do_carrossel(tg, chat, titulo, ofertas, log=print):
    """Mensagem dos links de um carrossel do próprio bot."""
    itens = [(_curto(o.titulo), getattr(o, "link", None)) for o in ofertas]
    try:
        tg.enviar_texto(chat, mensagem(titulo, itens))
    except Exception as e:  # noqa: BLE001 — a mensagem de links nunca derruba o pacote
        log(f"Aviso: não consegui mandar os links do carrossel: {e}")


def ler_pedidos(caminho=PEDIDOS):
    try:
        dados = json.loads(Path(caminho).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return []
    return [p for p in dados if isinstance(p, dict) and p.get("id") and p.get("itens")]


def _e_shopee(pid):
    pid = str(pid)
    return pid.isdigit() or pid.upper().startswith("SHP")


def link_shopee(shp, pid, log=print):
    """Link curto oficial da Shopee com a etiqueta do TikTok (pela API de afiliados)."""
    if not shp:
        return None
    try:
        p = shp.item(int(str(pid).upper().replace("SHP", "")))
        if not p:
            return None
        return shp.link_curto(p.link_produto or p.link, [ETIQUETA]) or p.link
    except Exception as e:  # noqa: BLE001
        log(f"Links do carrossel: Shopee {pid} falhou ({type(e).__name__}: {e}).")
        return None


def _anuncio_ml(ml, pid, log=print):
    try:
        info = ml.catalogo(pid)
        return info.item_id if info and info.disponivel else None
    except Exception as e:  # noqa: BLE001
        log(f"Links do carrossel: ML {pid} falhou ({type(e).__name__}: {e}).")
        return None


def _mandar_lote(tg, chat, estado, ml, titulo, pids, hoje, log):
    anuncios = [(pid, _anuncio_ml(ml, pid, log)) for pid in pids]
    anuncios = [(pid, a) for pid, a in anuncios if a]
    if not anuncios:
        return
    urls = [lote.url_linkbuilder(a) for _, a in anuncios]
    estado["lote_extra"] = {"dia": hoje.isoformat(), "ids": [pid for pid, _ in anuncios], "urls": urls,
                            "origem": "carrossel"}
    tg.enviar_texto(chat, lote.texto_lote(urls).replace("Lote 1 de até 1 hoje", f"Lote do carrossel “{titulo}”"),
                    html=True)


def _lote_vencido(estado, hoje):
    extra = estado.get("lote_extra")
    if extra and (hoje - datetime.fromisoformat(extra.get("dia") or hoje.isoformat()).date()).days > LOTE_DIAS:
        estado["lote_extra"] = None


def processar(tg, chat, estado, ml, agora, shp=None, log=print, caminho=PEDIDOS):
    """Atende os pedidos de `pedidos/carrosseis.json` (uma vez cada) e completa os parciais."""
    pedidos = ler_pedidos(caminho)
    feitos = estado.setdefault("carrosseis_links", {})
    links_ml = estado.setdefault("links", {})
    hoje = agora.date()
    _lote_vencido(estado, hoje)
    ids_pedidos = {p["id"] for p in pedidos}
    for pedido_id in list(feitos):  # esquece pedidos velhos que já saíram do arquivo
        if pedido_id not in ids_pedidos and (hoje - datetime.fromisoformat(feitos[pedido_id]["dia"]).date()).days > 30:
            del feitos[pedido_id]
    for p in pedidos:
        titulo = p.get("titulo") or p["id"]
        reg = feitos.get(p["id"])
        if reg is None:
            itens = []
            for it in p["itens"]:
                pid = str(it["id"])
                link = link_shopee(shp, pid, log) if _e_shopee(pid) else links_ml.get(pid)
                itens.append({"id": pid, "nome": it.get("nome") or pid, "link": link})
            completo = all(i["link"] for i in itens)
            # grava antes de mandar: se o Telegram falhar, não repete a cada rodada
            feitos[p["id"]] = {"dia": hoje.isoformat(), "titulo": titulo, "itens": itens, "completo": completo}
            log(f"Links do carrossel {p['id']}: {sum(1 for i in itens if i['link'])}/{len(itens)}.")
            tg.enviar_texto(chat, mensagem(titulo, [(i["nome"], i["link"], i["id"]) for i in itens], completo))
            sem_link = [i["id"] for i in itens if not i["link"] and not _e_shopee(i["id"])]
            if sem_link and not estado.get("lote_extra"):
                _mandar_lote(tg, chat, estado, ml, titulo, sem_link, hoje, log)
            elif sem_link:
                tg.enviar_texto(chat, "⏳ Ainda há um lote do Linkbuilder esperando os links. Quando ele for "
                                      "resolvido, eu mando o lote que falta deste carrossel.")
            continue
        if reg.get("completo"):
            continue
        if (hoje - datetime.fromisoformat(reg["dia"]).date()).days > VALIDADE_DIAS:
            reg["completo"] = True  # desiste em silêncio
            continue
        mudou = False
        for i in reg["itens"]:
            if i["link"]:
                continue
            i["link"] = link_shopee(shp, i["id"], log) if _e_shopee(i["id"]) else links_ml.get(i["id"])
            mudou = mudou or bool(i["link"])
        if all(i["link"] for i in reg["itens"]):
            reg["completo"] = True
            if mudou:
                tg.enviar_texto(chat, mensagem(reg["titulo"], [(i["nome"], i["link"], i["id"]) for i in reg["itens"]]))
            log(f"Links do carrossel {p['id']}: completo.")
            continue
        faltam = [i["id"] for i in reg["itens"] if not i["link"] and not _e_shopee(i["id"])]
        if faltam and not estado.get("lote_extra") and \
                not any(pid in (estado.get("lote_extra") or {}).get("ids", []) for pid in faltam):
            _mandar_lote(tg, chat, estado, ml, reg["titulo"], faltam, hoje, log)
