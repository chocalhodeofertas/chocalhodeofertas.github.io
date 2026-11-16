"""Posts de resumo do dia, além das ofertas uma a uma:

- tabela de fraldas (de manhã): a fralda com o menor preço por unidade em cada tamanho,
  entre o Mercado Livre (só com link oficial) e a Shopee;
- as 5 melhores do dia (21h): as ofertas mais fortes que saíram hoje, com o preço conferido de novo.

Cada um sai uma vez por dia e só quando está ligado (FRALDAS_ATIVO / TOP5_ATIVO = 1).
Não contam no limite de posts nem na regra de repetição: são um resumo do que já saiu ou do que está no ar.
"""
import html
import math
import os
import re
from datetime import datetime

from . import espelho, mensagens, whatsapp
from .filtros import motivo_bloqueio
from .ofertas import tipo_produto
from .telegram import TelegramErro

RODAPE = "Preço e estoque podem mudar a qualquer momento. #publi · links de afiliado"
NOME_LOJA = {"ml": "Mercado Livre", "shopee": "Shopee"}

# ---------------------------------------------------------------- fraldas

TAMANHOS = ["RN", "P", "M", "G", "GG", "XG", "XXG", "XXXG"]
# Tamanho em letras maiúsculas, isolado ("Tamanho M", "XG - 16 Un"); "P/" (para) e "G+" ficam de fora
_RE_TAM = re.compile(r"(?<![\w/])(RN|P|M|G|GG|EG|XG|XXG|XXXG)(?![\w/+])")
_RE_TAM_EXTENSO = re.compile(r"\btam(?:anho)?\.?\s*(rn|p|m|g|gg|eg|xg|xxg|xxxg)\b", re.I)
_PALAVRAS_TAM = [(r"rec[eé]m[- ]nascido", "RN"), (r"tamanho\s+pequen[oa]", "P"), (r"tamanho\s+m[eé]di[oa]", "M"),
                 (r"tamanho\s+extra\s+grande", "XG"), (r"tamanho\s+grande", "G")]
FRALDAS_MIN_TAMANHOS = 3   # com menos tamanhos que isso, a tabela não sai
FRALDAS_QUEDA = 0.02       # mostra "ontem era R$ X" quando ficou pelo menos 2% mais barata


def tamanho_fralda(titulo):
    """Tamanho da fralda pelo título (RN, P, M, G, GG, XG, XXG, XXXG), ou None se não der para ter certeza
    (sem tamanho ou com mais de um, como nos anúncios "P M G")."""
    titulo = titulo or ""
    achados = {m.upper() for m in _RE_TAM.findall(titulo)} | {m.upper() for m in _RE_TAM_EXTENSO.findall(titulo)}
    for padrao, tam in _PALAVRAS_TAM:
        if re.search(padrao, titulo, re.I):
            achados.add(tam)
    achados = {"XG" if t == "EG" else t for t in achados}
    return achados.pop() if len(achados) == 1 else None


def item_fralda(pid, loja, titulo, preco, link, link_wa=None):
    """Monta o item da tabela, ou None se não for fralda descartável com tamanho e quantidade claros."""
    if not titulo or not preco or not link or motivo_bloqueio(titulo):
        return None
    por_un = mensagens.preco_por_unidade(titulo, preco)
    tam = tamanho_fralda(titulo)
    if not por_un or por_un[1] != "por fralda" or not tam:
        return None
    return {"id": pid, "loja": loja, "titulo": titulo[:110], "preco": float(preco), "por_un": round(por_un[0], 4),
            "tam": tam, "link": link, "link_wa": link_wa or link}


def guardar_fraldas_ml(estado, produtos, infos, agora, link_oficial=lambda link: True):
    """Chamado a cada rodada: guarda as fraldas do Mercado Livre com o preço que acabou de ser conferido."""
    itens = []
    for p in produtos:
        info = infos.get(p.id)
        if not info or not info.disponivel or not info.preco or not link_oficial(p.link_afiliado):
            continue
        item = item_fralda(p.id, "ml", info.titulo, info.preco, p.link_afiliado)
        if item:
            itens.append(item)
    estado["fraldas_ml"] = {"em": agora.isoformat(timespec="minutes"), "itens": itens}


def fraldas_shopee(shp, log=print):
    """Fraldas da Shopee aprovadas pelas regras de sempre (nota, vendas, comissão) e com preço único."""
    from .shopee import MAIS_VENDIDOS, ShopeeErro
    from .shopee_ofertas import aprovado

    vistos = {}
    for termo, cat in (("fralda descartável", None), ("", 100683)):
        try:
            for p in shp.buscar(termo, ordem=MAIS_VENDIDOS, limite=50, categoria=cat):
                vistos.setdefault(p.id, p)
        except ShopeeErro as e:
            log(f"Fraldas: busca na Shopee falhou: {e}")
    saida = []
    for p in vistos.values():
        if aprovado(p) or (p.preco_max and p.preco_max > p.preco * 1.02):
            continue  # reprovado, ou anúncio com vários preços ("a partir de"): não dá para calcular por fralda
        item = item_fralda(p.id, "shopee", p.titulo, p.preco, p.link)
        if item:
            item["_produto"] = p
            saida.append(item)
    return saida


def escolher_fraldas(itens):
    """A mais barata por fralda em cada tamanho, na ordem RN, P, M, G..."""
    melhor = {}
    for i in itens:
        atual = melhor.get(i["tam"])
        if atual is None or i["por_un"] < atual["por_un"]:
            melhor[i["tam"]] = i
    return [melhor[t] for t in TAMANHOS if t in melhor]


def montar_fraldas(escolhidas, agora, formato="telegram", ontem=None):
    """Texto da tabela. ontem: {tamanho: preço por fralda da tabela anterior}."""
    tg = formato == "telegram"
    b = (lambda t: f"<b>{t}</b>") if tg else (lambda t: f"*{t}*")
    it = (lambda t: f"<i>{t}</i>") if tg else (lambda t: f"_{t}_")
    esc = html.escape if tg else (lambda t: t)
    linhas = [b("🧷 Fraldas: o menor preço por unidade que o Chocalho achou hoje"), ""]
    for i in escolhidas:
        cab = f"{b(i['tam'])} · {b(mensagens.brl(i['por_un']))} por fralda"
        antes = (ontem or {}).get(i["tam"])
        if antes and i["por_un"] <= antes * (1 - FRALDAS_QUEDA):
            cab += f" ⬇️ ontem era {mensagens.brl(antes)}"
        linhas.append(cab)
        linhas.append(esc(mensagens._titulo_curto(i["titulo"], 80)))
        loja = NOME_LOJA[i["loja"]]
        if tg:
            linhas.append(f"{mensagens.brl(i['preco'])} · 👉 <a href=\"{html.escape(i['link'], quote=True)}\">"
                          f"Ver {'na' if i['loja'] == 'shopee' else 'no'} {loja}</a>")
        else:
            linhas.append(f"{mensagens.brl(i['preco'])} {'na' if i['loja'] == 'shopee' else 'no'} {loja}")
            linhas.append(f"👉 {i['link_wa']}")
        linhas.append("")
    linhas.append(it(f"Preços conferidos às {agora:%Hh%M}. {RODAPE}"))
    return "\n".join(linhas)


def tabela_fraldas(estado, agora, shp=None, log=print, links=None):
    """Junta ML (guardado na rodada, com até 1 h) e Shopee (busca na hora) e devolve as escolhidas."""
    itens = []
    ml = estado.get("fraldas_ml") or {}
    try:
        fresco = (agora - datetime.fromisoformat(ml.get("em"))).total_seconds() < 3600
    except (TypeError, ValueError):
        fresco = False
    if fresco:
        itens += ml.get("itens") or []
    if shp is not None:
        itens += fraldas_shopee(shp, log)
    escolhidas = escolher_fraldas(itens)
    for i in escolhidas:  # link da Shopee com etiqueta por canal, só para quem entrou na tabela
        p = i.pop("_produto", None)
        if p is not None and links:
            i["link"], i["link_wa"] = links(shp, p, log)
    return escolhidas


def talvez_fraldas(tg, cfg, estado, agora, shp=None, log=print, links=None):
    """Uma vez por dia, a partir de FRALDAS_HORA (10h), se FRALDAS_ATIVO=1."""
    if os.environ.get("FRALDAS_ATIVO") != "1":
        return False
    hoje = agora.date().isoformat()
    hora = int(os.environ.get("FRALDAS_HORA") or 10)
    if estado.get("fraldas_enviado") == hoje or not (hora <= agora.hour < cfg.hora_fim):
        return False
    escolhidas = tabela_fraldas(estado, agora, shp, log, links)
    if len(escolhidas) < FRALDAS_MIN_TAMANHOS:
        log(f"Fraldas: só {len(escolhidas)} tamanho(s) com preço claro agora; tento na próxima rodada.")
        return False
    ontem = (estado.get("fraldas_tabela") or {}).get("valores")
    try:
        tg.enviar_texto(cfg.canal, montar_fraldas(escolhidas, agora, "telegram", ontem), html=True)
    except TelegramErro as e:
        log(f"Fraldas: não consegui postar a tabela: {e}")
        return False
    whatsapp.enfileirar(montar_fraldas(escolhidas, agora, "whatsapp", ontem), agora=agora)
    estado["fraldas_enviado"] = hoje
    estado["fraldas_tabela"] = {"dia": hoje, "valores": {i["tam"]: i["por_un"] for i in escolhidas}}
    log(f"Tabela de fraldas postada ({', '.join(i['tam'] for i in escolhidas)}).")
    return True


# ---------------------------------------------------------------- as 5 melhores do dia

TOP_N = 5
TOP_MIN = 3        # com menos que isso depois de conferir os preços, o resumo não sai
TOP_POR_LOJA = 3   # no máximo 3 da mesma loja


def registrar(estado, oferta, agora, loja="ml", tipo=None):
    """Guarda cada oferta postada hoje (com o link que saiu), para o resumo das 21h."""
    reg = estado.get("posts_dia")
    dia = agora.date().isoformat()
    if not isinstance(reg, dict) or reg.get("dia") != dia:
        reg = estado["posts_dia"] = {"dia": dia, "itens": []}
    reg["itens"] = [i for i in reg["itens"] if i.get("id") != oferta.id]
    reg["itens"].append({
        "id": oferta.id, "loja": loja, "tipo": tipo, "titulo": (oferta.titulo or "")[:110],
        "hora": agora.strftime("%H:%M"), "cupom": bool(getattr(oferta, "cupom", None)),
        "preco": oferta.preco, "de": oferta.preco_de, "normal": getattr(oferta, "preco_normal", None),
        "selo": getattr(oferta, "selo_dias", None), "a_partir": bool(getattr(oferta, "a_partir", False)),
        "link": oferta.link, "link_wa": getattr(oferta, "link_wa", None) or oferta.link,
        "imagem": oferta.imagem, "categoria": oferta.categoria or "",
        "vendas": getattr(oferta, "vendas", 0) or 0, "nota": getattr(oferta, "nota", 0) or 0,
        "fonte": espelho.fonte(estado, oferta.id),
    })


def forca(item):
    """Quão forte é a oferta: queda vista pelo próprio bot vale mais que o "de" do anúncio."""
    preco = item.get("preco") or 0
    real = 1 - preco / item["normal"] if item.get("normal") and item["normal"] > preco else 0
    anuncio = 1 - preco / item["de"] if item.get("de") and item["de"] > preco else 0
    return max(real * 1.5, min(anuncio, 0.5) * 0.6) + (0.05 if item.get("selo") else 0)


def _ordem(item):
    return (forca(item), math.log10(max(item.get("vendas") or 0, 1)) * (item.get("nota") or 0))


def escolher_top(itens, n=TOP_N, conferir=None, log=print):
    """As n mais fortes do dia: no máximo TOP_POR_LOJA por loja e uma por tipo de produto
    (se faltar gente, completa sem o limite por loja).
    conferir(item) devolve o preço de agora (ou None se acabou/não deu para conferir): só entra
    quem continua com o preço do post, ou mais barato."""
    ordenados = sorted(itens, key=_ordem, reverse=True)
    escolhidas, por_loja, tipos, fora = [], {}, set(), set()
    for limite_loja in (TOP_POR_LOJA, n):
        for item in ordenados:
            if len(escolhidas) >= n:
                break
            tp = tipo_produto(item["titulo"])
            if item["id"] in fora or tp in tipos or por_loja.get(item["loja"], 0) >= limite_loja:
                continue
            if conferir is not None:
                agora_custa = conferir(item)
                if not agora_custa or agora_custa > item["preco"] * 1.01:
                    log(f"Top do dia: {item['id']} ficou de fora (preço mudou ou acabou).")
                    fora.add(item["id"])
                    continue
                item = {**item, "preco": float(agora_custa)}
            fora.add(item["id"])
            por_loja[item["loja"]] = por_loja.get(item["loja"], 0) + 1
            tipos.add(tp)
            escolhidas.append(item)
    return sorted(escolhidas, key=_ordem, reverse=True)


_NUMEROS = ["1️⃣", "2️⃣", "3️⃣", "4️⃣", "5️⃣"]


def _linha_preco(item, b, s):
    preco = item["preco"]
    if item.get("de") and item["de"] > preco:
        return f"De {s(mensagens.brl(item['de']))} por {b(mensagens.brl(preco))} (-{round((1 - preco / item['de']) * 100)}%)"
    if item.get("normal") and item["normal"] > preco:
        return f"Por {b(mensagens.brl(preco))} (vinha custando {mensagens.brl(item['normal'])})"
    return f"{'A partir de' if item.get('a_partir') else 'Por'} {b(mensagens.brl(preco))}"


def montar_top(escolhidas, agora, formato="telegram"):
    tg = formato == "telegram"
    b = (lambda t: f"<b>{t}</b>") if tg else (lambda t: f"*{t}*")
    s = (lambda t: f"<s>{t}</s>") if tg else (lambda t: f"~{t}~")
    it = (lambda t: f"<i>{t}</i>") if tg else (lambda t: f"_{t}_")
    esc = html.escape if tg else (lambda t: t)
    n = len(escolhidas)
    linhas = [b(f"🪇 As {n} melhores ofertas de hoje no Chocalho"), ""]
    for k, item in enumerate(escolhidas):
        emoji = mensagens.EMOJI_CATEGORIA.get(item.get("categoria"), "✨")
        linhas.append(f"{_NUMEROS[k]} {emoji} {esc(mensagens._titulo_curto(item['titulo'], 70))}")
        loja = NOME_LOJA.get(item["loja"], "")
        linhas.append(_linha_preco(item, b, s) + ("" if tg else f" · {loja}"))  # no Telegram a loja vai no link
        if item.get("selo"):
            linhas.append(f"📉 Menor preço que o Chocalho viu em {item['selo']} dias")
        prep = "na" if item["loja"] == "shopee" else "no"
        if tg:
            linhas.append(f"👉 <a href=\"{html.escape(item['link'], quote=True)}\">Ver oferta {prep} {loja}</a>")
        else:
            linhas.append(f"👉 {item['link_wa']}")
        linhas.append("")
    linhas.append(it(f"Preços conferidos às {agora:%Hh%M}. {RODAPE}"))
    return "\n".join(linhas)


def conferidor(ml=None, shp=None, log=print):
    """Função que consulta o preço de agora de um item do resumo (None = não entra)."""
    def conferir(item):
        try:
            if item["loja"] == "shopee":
                if shp is None:
                    return None
                p = shp.item(int(str(item["id"]).removeprefix("SHP")))
                return p.preco if p and p.preco else None
            if ml is None:
                return None
            if item.get("tipo") == "item":
                info = ml.itens([item["id"]]).get(item["id"])
            else:
                info = ml.catalogo(item["id"], item["titulo"], item.get("imagem"))
            return info.preco if info and info.disponivel and info.preco else None
        except Exception as e:  # noqa: BLE001 — sem conferir, não entra no resumo
            log(f"Top do dia: não consegui conferir {item['id']}: {type(e).__name__}")
            return None
    return conferir


def talvez_top(tg, cfg, estado, agora, ml=None, shp=None, log=print):
    """Uma vez por dia, a partir de TOP5_HORA (21h), se TOP5_ATIVO=1."""
    if os.environ.get("TOP5_ATIVO") != "1":
        return False
    hoje = agora.date().isoformat()
    hora = int(os.environ.get("TOP5_HORA") or 21)
    if estado.get("top5_enviado") == hoje or not (hora <= agora.hour < cfg.hora_fim):
        return False
    reg = estado.get("posts_dia") or {}
    itens = reg.get("itens") or [] if reg.get("dia") == hoje else []
    if len(itens) < TOP_MIN:
        return False
    escolhidas = escolher_top(itens, TOP_N, conferidor(ml, shp, log), log)
    estado["top5_enviado"] = hoje  # tenta uma vez só por dia (cada tentativa confere preços nas lojas)
    if len(escolhidas) < TOP_MIN:
        log(f"Top do dia: só {len(escolhidas)} oferta(s) continuam com o preço do post; hoje não sai.")
        return False
    try:
        tg.enviar_texto(cfg.canal, montar_top(escolhidas, agora, "telegram"), html=True)
    except TelegramErro as e:
        log(f"Top do dia: não consegui postar: {e}")
        return False
    whatsapp.enfileirar(montar_top(escolhidas, agora, "whatsapp"), agora=agora)
    log(f"Top do dia postado ({len(escolhidas)} ofertas).")
    return True


# ---------------------------------------------------------------- cupons da Shopee (link da página de cupons)

def montar_cupons_shopee(link, formato="telegram"):
    tg = formato == "telegram"
    b = (lambda t: f"<b>{t}</b>") if tg else (lambda t: f"*{t}*")
    it = (lambda t: f"<i>{t}</i>") if tg else (lambda t: f"_{t}_")
    onde = f'👉 <a href="{html.escape(link, quote=True)}">Ver os cupons de hoje</a>' if tg else f"👉 {link}"
    return "\n".join([
        b("🎟️ Cupons da Shopee de hoje"), "",
        "Antes de fechar a compra, passe na página de cupons e ative os que servem para você. "
        "Tem desconto e frete grátis, e eles mudam todo dia.", "",
        onde, "",
        it("Cupons têm quantidade e prazo limitados. #publi · link de afiliado"),
    ])


def talvez_cupons_shopee(tg, cfg, estado, agora, log=print):
    """Uma vez por dia, a partir de CUPONS_SHOPEE_HORA (9h), se CUPONS_SHOPEE_ATIVO=1."""
    from .comandos import link_cupons_shopee

    hoje = agora.date().isoformat()
    hora = int(os.environ.get("CUPONS_SHOPEE_HORA") or 9)
    if (os.environ.get("CUPONS_SHOPEE_ATIVO") != "1" or estado.get("cupons_shopee_enviado") == hoje
            or not (hora <= agora.hour < cfg.hora_fim)):
        return False
    link = link_cupons_shopee()
    try:
        tg.enviar_texto(cfg.canal, montar_cupons_shopee(link, "telegram"), html=True)
    except TelegramErro as e:
        log(f"Cupons da Shopee: não consegui postar: {e}")
        return False
    whatsapp.enfileirar(montar_cupons_shopee(link, "whatsapp"), agora=agora, loja="shopee")
    estado["cupons_shopee_enviado"] = hoje
    log("Cupons da Shopee do dia postados.")
    return True


# ---------------------------------------------------------------- chamada da rodada

def _shopee(log=print):
    if os.environ.get("SHOPEE_ATIVO") != "1":
        return None
    from .shopee import Shopee, ShopeeErro
    try:
        return Shopee(os.environ.get("SHOPEE_APP_ID"), os.environ.get("SHOPEE_SECRET"))
    except ShopeeErro as e:
        log(f"Resumos: Shopee desligada: {e}")
        return None


def rodar(tg, cfg, estado, agora, ml=None, log=print, shp=None):
    """Chamado no fim de cada rodada: posta o que estiver na hora (e ligado)."""
    talvez_cupons_shopee(tg, cfg, estado, agora, log)
    hoje = agora.date().isoformat()
    na_hora = lambda chave, padrao: int(os.environ.get(chave) or padrao) <= agora.hour < cfg.hora_fim  # noqa: E731
    fraldas = (os.environ.get("FRALDAS_ATIVO") == "1" and estado.get("fraldas_enviado") != hoje
               and na_hora("FRALDAS_HORA", 10))
    top = os.environ.get("TOP5_ATIVO") == "1" and estado.get("top5_enviado") != hoje and na_hora("TOP5_HORA", 21)
    if not (fraldas or top):
        return
    shp = shp or _shopee(log)
    if fraldas:
        from .shopee_ofertas import links
        talvez_fraldas(tg, cfg, estado, agora, shp, log, links)
    if top:
        talvez_top(tg, cfg, estado, agora, ml, shp, log)
