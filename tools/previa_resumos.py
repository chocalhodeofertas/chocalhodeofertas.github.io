"""Prévia dos formatos novos SÓ para o admin: tabela de fraldas, as 5 melhores do dia e o gráfico de preço.

Não posta no canal nem no grupo e não grava nada no estado do bot.
Uso (workflow inspecao): script=previa_resumos, args="fraldas top5 grafico" (ou só um deles).
"""
import os
import sys
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from bot import estado as est
from bot import grafico, mensagens, resumos, shopee_ofertas
from bot.mercadolivre import MercadoLivre, token_do_app
from bot.ofertas import Oferta
from bot.telegram import Telegram

agora = datetime.now(ZoneInfo("America/Sao_Paulo"))
quais = (sys.argv[1] if len(sys.argv) > 1 and sys.argv[1].strip() else "fraldas top5 grafico").split()
estado = est.carregar("data/estado.json")
tg = Telegram(os.environ["TELEGRAM_BOT_TOKEN"])
admin = os.environ.get("TELEGRAM_ADMIN_CHAT_ID") or "787296152"
shp = None
try:
    from bot.shopee import Shopee
    shp = Shopee(os.environ.get("SHOPEE_APP_ID"), os.environ.get("SHOPEE_SECRET"))
except Exception as e:  # noqa: BLE001
    print("Shopee indisponível:", type(e).__name__)
ml = None
try:
    ml = MercadoLivre(token_do_app(os.environ.get("ML_CLIENT_ID"), os.environ.get("ML_CLIENT_SECRET")))
except Exception as e:  # noqa: BLE001
    print("Mercado Livre indisponível:", type(e).__name__)


def _preco_ml(pid):
    """Preço de agora no ML (None se não der para conferir)."""
    titulo, imagem = (estado.get("cache", {}).get(pid) or [None, None])[:2]
    try:
        info = ml.catalogo(pid, titulo, imagem) if ml else None
        return info.preco if info and info.disponivel else None
    except Exception:  # noqa: BLE001
        return None


if "fraldas" in quais:
    guardado = estado.get("fraldas_ml") or {}
    conferidos = True
    try:
        fresco = (agora - datetime.fromisoformat(guardado.get("em"))).total_seconds() < 3600
    except (TypeError, ValueError):
        fresco = False
    if not fresco:  # o ciclo ainda não guardou as fraldas desta hora: monta pelo último preço visto
        itens = []
        for pid, (titulo, _img) in estado.get("cache", {}).items():
            hist = (estado["precos"].get(pid) or {}).get("historico") or []
            link = estado.get("links", {}).get(pid)
            if not hist or not link or not resumos.item_fralda(pid, "ml", titulo, hist[-1][1], link):
                continue
            preco = _preco_ml(pid)
            conferidos = conferidos and preco is not None
            item = resumos.item_fralda(pid, "ml", titulo, preco or hist[-1][1], link)
            if item:
                itens.append(item)
        estado["fraldas_ml"] = {"em": agora.isoformat(timespec="minutes"), "itens": itens}
    escolhidas = resumos.tabela_fraldas(estado, agora, shp, print, shopee_ofertas.links if shp else None)
    print(resumos.montar_fraldas(escolhidas, agora, "whatsapp"))
    nota = "" if conferidos else "\n(os preços do Mercado Livre desta prévia são os últimos que o bot viu)"
    tg.enviar_texto(admin, f"🧪 <b>PRÉVIA · tabela de fraldas</b> (nada foi postado){nota}", html=True)
    if escolhidas:
        tg.enviar_texto(admin, resumos.montar_fraldas(escolhidas, agora, "telegram"), html=True)
        tg.enviar_texto(admin, "[versão do WhatsApp]\n\n" + resumos.montar_fraldas(escolhidas, agora, "whatsapp"))
    else:
        tg.enviar_texto(admin, "Nenhuma fralda com tamanho e quantidade claros agora.")

if "top5" in quais:
    reg = estado.get("posts_dia") or {}
    itens = (reg.get("itens") or []) if reg.get("dia") == agora.date().isoformat() else []
    origem = "de hoje"
    if len(itens) < 5:  # ainda sem a lista do dia: monta com o que saiu hoje (ou ontem) pelo registro de posts
        for dia, origem in ((agora.date(), "de hoje"), (agora.date() - timedelta(days=1), "de ontem")):
            d, itens = dia.isoformat(), []
            for pid, v in estado.get("postados", {}).items():
                link = estado.get("links", {}).get(pid)
                if v.get("quando", "").startswith(d) and v.get("titulo") and link:
                    de = round(v["preco"] / (1 - v["desconto"]), 2) if v.get("desconto") else None
                    cat = ((estado.get("descobertos", {}).get(pid) or {}).get("categoria")) or ""
                    itens.append({"id": pid, "loja": "ml", "tipo": "catalogo", "titulo": v["titulo"], "preco": v["preco"],
                                  "de": de, "link": link, "link_wa": link, "categoria": cat,
                                  "imagem": (estado.get("cache", {}).get(pid) or [None, None])[1]})
            for pid, v in (estado.get("shopee", {}).get("titulos") or {}).items():
                if v.get("quando", "").startswith(d) and shp:
                    try:
                        p = shp.item(int(pid.removeprefix("SHP")))
                    except Exception:  # noqa: BLE001
                        p = None
                    if p and len([i for i in itens if i["loja"] == "shopee"]) < 6:
                        link_tg, link_wa = shopee_ofertas.links(shp, p, print)
                        o = shopee_ofertas.para_oferta(p, estado, agora, link_tg, link_wa)
                        itens.append({"id": pid, "loja": "shopee", "titulo": o.titulo, "preco": v.get("preco") or o.preco,
                                      "de": o.preco_de, "a_partir": o.a_partir, "link": link_tg, "link_wa": link_wa,
                                      "categoria": o.categoria, "vendas": o.vendas, "nota": o.nota, "selo": o.selo_dias})
            if len(itens) >= 5:
                break
    top = resumos.escolher_top(itens, resumos.TOP_N, resumos.conferidor(ml, shp, print), print)
    print(resumos.montar_top(top, agora, "whatsapp"))
    tg.enviar_texto(admin, f"🧪 <b>PRÉVIA · as melhores do dia</b> (nada foi postado; com as ofertas {origem}, "
                    f"preços conferidos agora)", html=True)
    if top:
        tg.enviar_texto(admin, resumos.montar_top(top, agora, "telegram"), html=True)
        tg.enviar_texto(admin, "[versão do WhatsApp]\n\n" + resumos.montar_top(top, agora, "whatsapp"))
    else:
        tg.enviar_texto(admin, "Nenhuma oferta do dia continua com o preço do post agora.")

if "grafico" in quais:
    # O produto com a queda mais clara no histórico (o selo de verdade só começa com 14 dias de histórico)
    melhor = None
    for pid in estado.get("links", {}):
        serie = est.serie_diaria(estado, pid, agora, 30, com_hoje=True)
        if len(serie) < 7 or pid not in estado.get("cache", {}):
            continue
        precos = [p for _, p in serie]
        queda = 1 - precos[-1] / min(precos[:-1])
        if queda > 0.05 and (melhor is None or queda > melhor[0]):
            melhor = (queda, pid, serie)
    if not melhor:
        tg.enviar_texto(admin, "🧪 PRÉVIA · gráfico: nenhum produto com link caiu de preço hoje para servir de exemplo.")
    else:
        _, pid, serie = melhor
        titulo, imagem = estado["cache"][pid][:2]
        png = grafico.gerar(titulo, serie, "ml")
        os.makedirs("saida", exist_ok=True)
        with open("saida/grafico_previa.png", "wb") as f:
            f.write(png)
        o = Oferta(id=pid, titulo=titulo, preco=serie[-1][1], preco_de=None, desconto=0.0, abaixo_do_habitual=None,
                   menor_preco_historico=False, link=estado["links"][pid], imagem=imagem, categoria="")
        o.selo_dias = (serie[-1][0] - serie[0][0]).days
        tg.enviar_texto(admin, "🧪 <b>PRÉVIA · gráfico de preço</b> (nada foi postado). No canal, a oferta com o selo "
                        "de menor preço sairia assim: foto do produto + gráfico.", html=True)
        try:
            import random
            tg.enviar_oferta_com_grafico(admin, mensagens.montar_telegram(o, random.Random(1)), imagem, png)
        except Exception as e:  # noqa: BLE001
            print("álbum falhou:", type(e).__name__)
            tg.enviar_foto(admin, png, "Gráfico de preço (exemplo)")
