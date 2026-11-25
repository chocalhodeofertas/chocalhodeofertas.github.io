"""Espelho: lê canais de ofertas de bebê/criança no Telegram e aproveita os links do ML e da Shopee.

Nada é repostado como veio. Cada link vira só um "candidato": o bot confere o produto pela API oficial,
aplica os filtros de nicho/NBCAL, a repetição de 7 dias e o histórico de preço, e posta com o NOSSO link.

Fontes em FONTES_OFERTAS_TG (separadas por vírgula): @usuario, link t.me ou o título do canal
(a conta do Telegram conectada ao bot precisa ter entrado no canal).
"""
import asyncio
import json
import os
import re
from datetime import datetime, timedelta

import requests

HORAS_CANDIDATO = 48      # quanto tempo um link visto num canal continua candidato
MSGS_PRIMEIRA_VEZ = 20    # ao conectar uma fonte nova, olha as últimas N mensagens
MSGS_POR_RODADA = 60
_RE_URL = re.compile(r"https?://[^\s<>\"')\]]+")
_UA = {"User-Agent": "Mozilla/5.0 (Linux; Android 13) AppleWebKit/537.36 Chrome/124 Mobile Safari/537.36"}
_RE_SHOPEE = re.compile(r"(?:-i\.|/product/|shopee\.com\.br/(?!product/)[^/?#]+/)(\d{4,})[./](\d{5,})")


def fontes_configuradas():
    bruto = os.environ.get("FONTES_OFERTAS_TG") or ""
    return [f.strip() for f in bruto.split(",") if f.strip() and f.strip().lower() not in ("nenhum", "off", "0")]


def _estado(estado):
    e = estado.setdefault("espelho", {})
    for k in ("fontes", "ml", "shopee", "links", "shopee_titulos"):
        e.setdefault(k, {})
    return e


# ---------- leitura do Telegram ----------

async def _resolver(client, fonte):
    """@usuario / t.me/... / convite, ou o título de um canal em que a conta já entrou."""
    if re.match(r"^(@|https?://|t\.me/)", fonte) or re.fullmatch(r"[A-Za-z0-9_]{5,}", fonte):
        from .cupons_ml import _resolver as resolver_link
        return await resolver_link(client, fonte)
    alvo = fonte.casefold()
    async for d in client.iter_dialogs():
        if (d.name or "").strip().casefold() == alvo:
            return d.entity
    raise RuntimeError("a conta do Telegram ainda não entrou nesse canal")


async def _ler(api_id, api_hash, sessao, fontes, cache=None):
    """fontes: [(nome, desde)] -> [[(id, texto)] | Exception] na mesma ordem.

    cache {nome: [id, access_hash]} evita procurar o @ toda rodada (o Telegram limita essas buscas)."""
    from telethon.tl.types import InputPeerChannel
    cache = {} if cache is None else cache
    from telethon import TelegramClient
    from telethon.sessions import StringSession

    client = TelegramClient(StringSession(sessao), int(api_id), api_hash)
    await client.connect()
    try:
        if not await client.is_user_authorized():
            raise RuntimeError("o login do Telegram expirou; rode de novo o 'Conectar Telegram'")
        saida = []
        for nome, desde in fontes:
            try:
                if nome in cache:
                    chat = InputPeerChannel(*cache[nome])
                else:
                    ent = await _resolver(client, nome)
                    if getattr(ent, "access_hash", None):
                        cache[nome] = [ent.id, ent.access_hash]
                    chat = ent
                msgs = []
                limite = MSGS_POR_RODADA if desde else MSGS_PRIMEIRA_VEZ
                async for m in client.iter_messages(chat, min_id=desde or 0, limit=limite):
                    texto = m.message or ""
                    # links "escondidos" atrás de texto/botão também contam
                    for ent in getattr(m, "entities", None) or []:
                        url = getattr(ent, "url", None)
                        if url:
                            texto += "\n" + url
                    for linha in getattr(m, "buttons", None) or []:
                        for b in linha:
                            if getattr(b, "url", None):
                                texto += "\n" + b.url
                    msgs.append((m.id, texto))
                saida.append(sorted(msgs))
            except Exception as e:  # noqa: BLE001
                cache.pop(nome, None)
                saida.append(e)
        return saida
    finally:
        await client.disconnect()


# ---------- links ----------

def expandir(url, session=None, timeout=10):
    """Segue os redirecionamentos (meli.la, s.shopee, bit.ly...) até a página da loja."""
    s = session or requests
    try:
        r = s.get(url, allow_redirects=True, timeout=timeout, headers=_UA, stream=True)
        final = r.url
        r.close()
        return final
    except requests.RequestException:
        return url


# ---------- preço pela página do link de OUTRO canal (25/11) ----------
# Desde 23/11 a API do ML não dá mais preço de catálogo. O link de afiliado de outro canal abre a vitrine dele no ML,
# e o 1º cartão dessa página ("polycards") é o produto divulgado, com o anúncio, o preço atual e o "de".
# O bot já abria esses links para descobrir o produto; agora também lê o cartão. NUNCA vale para os links do
# Leonardo (regra dele): só links que chegam das fontes do espelho.
PAGINA_RELER_MIN = 60  # antes de postar, preço lido há mais que isso é relido na página


def ler_cartao(texto):
    """1º cartão da página (produto do link) → {produto, item, preco, de, rotulo, titulo, pix} ou None."""
    i = (texto or "").find('"polycards":')
    if i < 0:
        return None
    try:
        cartoes, _ = json.JSONDecoder().raw_decode(texto[i + len('"polycards":'):])
    except ValueError:
        return None
    if not isinstance(cartoes, list) or not cartoes:
        return None
    c = cartoes[0]
    md = c.get("metadata") or {}
    comps = {x.get("type"): x.get(x.get("type")) for x in c.get("components") or []}
    preco = comps.get("price") or {}
    atual = (preco.get("current_price") or {}).get("value")
    rotulo = (preco.get("discount_label") or {}).get("text") or ""
    if not md.get("id") or not atual:
        return None
    pix = None
    normal = float(atual)
    if "pix" in rotulo.lower():
        # "46% OFF no Pix": o preço grande é o do Pix; o normal vem em "ou {price_total} em outros meios"
        parc = preco.get("installments") or {}
        total = next((v["price"]["value"] for v in parc.get("values") or []
                      if v.get("key") == "price_total" and (v.get("price") or {}).get("value")), None)
        pix, normal = float(atual), (float(total) if total else None)
    cupom = None
    for pr in comps.get("promotions") or []:
        if pr.get("type") != "coupon":
            continue
        valor = next((v["price"]["value"] for v in pr.get("values") or [] if (v.get("price") or {}).get("value")), None)
        pct = re.search(r"(\d+(?:[.,]\d+)?)\s*%\s*OFF", pr.get("text") or "", re.I)
        if valor:
            cupom = {"preco": float(valor)}
        elif pct:
            cupom = {"desconto": f"{pct.group(1).replace('.', ',')}% OFF"}
        break
    return {"produto": md.get("product_id"), "item": md.get("id"), "preco": normal,
            "de": (preco.get("previous_price") or {}).get("value"), "rotulo": rotulo,
            "titulo": ((comps.get("title") or {}).get("text") or "")[:150], "pix": pix, "cupom": cupom}


def ler_pagina(url, session=None, timeout=20):
    """Abre o link (de outro canal) como navegador e lê o cartão do produto. (url final, cartão ou None)."""
    s = session or requests
    try:
        r = s.get(url, allow_redirects=True, timeout=timeout, headers={**_UA, "Accept-Language": "pt-BR,pt;q=0.9"})
        return r.url, ler_cartao(r.text)
    except requests.RequestException:
        return url, None


def _pagina_util(cartao):
    """Cartão que serve de preço: de catálogo e com o preço normal (no "no Pix", o normal vem nas parcelas)."""
    return bool(cartao and cartao.get("produto") and cartao.get("preco"))


def extras_pagina(estado, pid, preco):
    """(preço no Pix, cupom do anúncio no formato do cupom_oferta) lidos na página; None quando não há.
    O Pix só conta se for menor que o preço do post; o cupom com preço só conta se economizar R$ 1+."""
    pg = (_estado(estado)["ml"].get(pid) or {}).get("pagina") or {}
    pix = pg.get("pix") if pg.get("pix") and preco and pg["pix"] < preco - 0.5 else None
    c = pg.get("cupom") or {}
    cupom = None
    if c.get("preco") and preco and preco - c["preco"] >= 1:
        cupom = {"origem": "pagina", "preco": round(c["preco"], 2), "economia": round(preco - c["preco"], 2), "desconto": ""}
    elif c.get("desconto"):
        cupom = {"origem": "pagina", "preco": None, "economia": 0.0, "desconto": c["desconto"]}
    return pix, cupom


def info_pagina(estado, pid, cache=None):
    """InfoProduto montado com o preço lido na página do outro canal (quando a API recusa). None se não houver."""
    from .mercadolivre import InfoProduto
    pg = (_estado(estado)["ml"].get(pid) or {}).get("pagina")
    if not pg or not pg.get("preco") or not pg.get("item"):
        return None
    titulo, imagem = (cache or {}).get(pid) or (pg.get("titulo"), None)
    de = pg.get("de")
    return InfoProduto(id=pid, titulo=titulo or pg.get("titulo") or pid, preco=pg["preco"],
                       preco_original=float(de) if de else None, imagem=imagem, disponivel=True,
                       item_id=pg["item"], ativos={pg["item"]: (pg["preco"], float(de) if de else None)}, total=1)


def reler_pagina(estado, pid, agora, session=None, ler=None):
    """Relê o link do outro canal antes do post. Devolve o InfoProduto atualizado, ou None se o cartão sumiu,
    mudou de anúncio ou não deu para ler (aí não posta: sem confirmar o preço, não sai)."""
    reg = _estado(estado)["ml"].get(pid) or {}
    pg = reg.get("pagina")
    if not pg:
        return None
    lido = datetime.fromisoformat(pg["lido"]) if pg.get("lido") else None
    if lido and (agora - lido).total_seconds() < PAGINA_RELER_MIN * 60:
        return info_pagina(estado, pid)
    _, cartao = (ler or ler_pagina)(reg.get("url"), session)
    if not _pagina_util(cartao) or cartao["item"] != pg["item"]:
        return None
    pg.update(preco=cartao["preco"], de=cartao["de"], rotulo=cartao["rotulo"], pix=cartao.get("pix"),
              cupom=cartao.get("cupom"), lido=agora.isoformat(timespec="minutes"))
    return info_pagina(estado, pid)


def classificar(url):
    """('ml', tipo, id) | ('shopee', item_id) | None."""
    if "shopee.com" in url:
        m = _RE_SHOPEE.search(url)
        return ("shopee", m.group(2)) if m else None
    if "mercadolivre.com" in url or "mercadolibre.com" in url:
        from .mercadolivre import extrair_id
        try:
            tipo, pid = extrair_id(url)
        except ValueError:
            return None
        return ("ml", tipo, pid)
    return None


def _loja(texto):
    if re.search(r"meli\.la|mercadolivre\.com|mercadolibre\.com|mercado\.?livre", texto):
        return "ml"
    if re.search(r"shopee\.com|shope\.ee|shp\.ee", texto):
        return "shopee"
    return None


def titulo_da_mensagem(texto):
    """Primeira linha que parece nome de produto (sem preço, link nem chamada)."""
    for linha in (texto or "").splitlines():
        limpa = re.sub(r"[^\w\s,.+\-/%]", " ", linha, flags=re.UNICODE)
        limpa = re.sub(r"\s+", " ", limpa).strip()
        if len(limpa) < 12 or "http" in linha or re.search(r"r\$|\bde:|\bpor:|cupom|compre|link|frete", limpa, re.I):
            continue
        if sum(c.isalpha() for c in limpa) < 8:
            continue
        letras = [c for c in limpa if c.isalpha()]
        if letras and sum(c.isupper() for c in letras) / len(letras) > 0.8:
            continue  # chamada em caixa alta ("CORRE QUE ACABA"), não é o nome do produto
        return limpa[:120]
    return ""


def _catalogo_por_titulo(ml, titulo):
    """Anúncio avulso (bloqueado para o app): acha o produto de catálogo equivalente pelo nome."""
    from .ofertas import parecido
    if not titulo:
        return None
    try:
        achados = ml.buscar_produtos(titulo, 5)
    except Exception:  # noqa: BLE001
        return None
    for pid, nome in achados:
        if parecido(titulo, nome):
            return pid
    return None


# ---------- rodada ----------

def coletar(ml, estado, agora, log=print, ler=None, expandir_url=expandir, ler_pagina_url=ler_pagina):
    """Lê as fontes e guarda os produtos achados como candidatos por 48 h. Retorna quantos entraram."""
    fontes = fontes_configuradas()
    if not fontes:
        return 0
    e = _estado(estado)
    if ler is None:
        from .cupons_ml import ARQ_SESSAO, ler_seguro
        api_id, api_hash = os.environ.get("TG_API_ID"), os.environ.get("TG_API_HASH")
        if not (api_id and api_hash and ARQ_SESSAO.exists()):
            return 0
        sessao = ler_seguro(api_hash, ARQ_SESSAO)["sessao"]

        cache = e.setdefault("entidades", {})

        def ler(lista):
            return asyncio.run(_ler(api_id, api_hash, sessao, lista, cache))
    try:
        resultados = ler([(f, e["fontes"].get(f)) for f in fontes])
    except Exception as erro:  # noqa: BLE001
        log(f"Espelho: não consegui ler o Telegram: {erro}")
        return 0

    ate = (agora + timedelta(hours=HORAS_CANDIDATO)).isoformat(timespec="minutes")
    novos = 0
    sess = requests.Session()
    for fonte, msgs in zip(fontes, resultados):
        if isinstance(msgs, Exception):
            log(f"Espelho: fonte '{fonte}' indisponível: {msgs}")
            continue
        for mid, texto in msgs:
            e["fontes"][fonte] = max(mid, e["fontes"].get(fonte) or 0)
            for url in dict.fromkeys(_RE_URL.findall(texto)):
                url = url.rstrip(".,;")
                if url in e["links"]:
                    continue
                e["links"][url] = agora.date().isoformat()
                pagina = None
                if classificar(url):
                    final = url
                elif _loja(url) == "ml":
                    final, cartao = ler_pagina_url(url, sess)  # abre uma vez (como antes) e lê o preço do cartão
                    if _pagina_util(cartao):
                        pagina = {**{k: cartao.get(k) for k in ("item", "preco", "de", "rotulo", "titulo", "pix", "cupom")},
                                  "url": url, "lido": agora.isoformat(timespec="minutes")}
                else:
                    final = expandir_url(url, sess)
                alvo = ("ml", "catalogo", cartao["produto"]) if pagina else classificar(final)
                if not alvo:
                    # Link de afiliado que não mostra o produto (vitrine "social" do ML, encurtador da Shopee
                    # que só abre no app): procura o produto pelo nome escrito na mensagem
                    loja = _loja(url + " " + final)
                    titulo = titulo_da_mensagem(texto)
                    if loja == "ml":
                        pid = _catalogo_por_titulo(ml, titulo)
                        alvo = ("ml", "catalogo", pid) if pid else None
                    elif loja == "shopee" and titulo:
                        if titulo not in e["shopee_titulos"]:
                            novos += 1
                        e["shopee_titulos"][titulo] = {"ate": ate, "fonte": fonte}
                    if not alvo:
                        continue
                if alvo[0] == "shopee":
                    chave = "SHP" + alvo[1]
                    if chave not in e["shopee"]:
                        novos += 1
                    e["shopee"][chave] = {"ate": ate, "fonte": fonte}
                    continue
                _, tipo, pid = alvo
                if tipo == "item":
                    pid = _catalogo_por_titulo(ml, titulo_da_mensagem(texto))
                    if not pid:
                        continue
                if pid not in e["ml"]:
                    novos += 1
                e["ml"][pid] = {"tipo": "catalogo", "categoria": "outros", "regra": "infantil",
                                "pos": 30, "ate": ate, "fonte": fonte}
                if pagina:
                    e["ml"][pid]["pagina"] = pagina
    limpar(estado, agora)
    if novos:
        log(f"Espelho: {novos} produto(s) novo(s) vindos dos canais de ofertas.")
    return novos


def limpar(estado, agora):
    e = _estado(estado)
    agora_iso = agora.isoformat(timespec="minutes")
    for loja in ("ml", "shopee", "shopee_titulos"):
        for k in [k for k, v in e[loja].items() if v.get("ate", "") < agora_iso]:
            del e[loja][k]
    corte = (agora - timedelta(days=7)).date().isoformat()
    for k in [k for k, d in e["links"].items() if d < corte]:
        del e["links"][k]


def candidatos_ml(estado, agora):
    """{pid: dados} dos produtos do ML vindos das fontes e ainda válidos."""
    limpar(estado, agora)
    return dict(_estado(estado)["ml"])


def ids_shopee(estado, agora, ja_vistos=()):
    limpar(estado, agora)
    return [k for k in _estado(estado)["shopee"] if k not in ja_vistos]


def titulos_shopee(estado, agora):
    """Nomes de produtos da Shopee citados nos canais (link que não abriu fora do app)."""
    limpar(estado, agora)
    return {t: d for t, d in _estado(estado)["shopee_titulos"].items() if not d.get("fora")}


def fonte(estado, pid):
    """Canal de onde o produto veio (sem @), ou None se não veio do espelho."""
    e = estado.get("espelho") or {}
    reg = (e.get("ml") or {}).get(pid) or (e.get("shopee") or {}).get(pid)
    return (reg or {}).get("fonte") or None


def eh_do_espelho(estado, pid):
    e = estado.get("espelho") or {}
    return pid in (e.get("ml") or {}) or pid in (e.get("shopee") or {})
