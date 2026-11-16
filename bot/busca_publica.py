"""Busca sob pedido: a pessoa escreve o que procura (ex.: "fralda G") e recebe as melhores opções de agora.

- Mercado Livre: só produtos que já têm link oficial, com o preço conferido na hora.
- Shopee: busca ao vivo pela API oficial, com as regras de sempre (nota, vendas, comissão, nicho).
- Vale tudo o que vale para os posts: NBCAL, bloqueios e faixa infantil.

O admin testa com `achar <produto>`. Para as outras pessoas, só responde com BUSCA_PUBLICA=1.
O repositório é público: não guarda quem perguntou, só um código embaralhado para o limite por pessoa
e a contagem dos termos mais procurados (para você saber o que o grupo quer).
"""
import hashlib
import html
import os
import re
from datetime import datetime, timedelta

from . import mensagens
from .filtros import fora_da_faixa, motivo_bloqueio, normalizar

MAX_ML, MAX_SHOPEE = 3, 2
LIMITE_POR_HORA = 5
RODAPE = "Preço e estoque podem mudar a qualquer momento. #publi · links de afiliado"
_VAZIAS = {"de", "da", "do", "para", "pra", "com", "sem", "em", "um", "uma", "o", "a", "os", "as", "e", "tamanho", "tam"}
BOAS_VINDAS = ("🪇 <b>Chocalho de Ofertas</b>\n\nMe diga o que você procura (ex.: <i>fralda G</i>, <i>carrinho de bebê</i>, "
               "<i>mochila infantil</i>) e eu respondo com as melhores opções que achei agora no Mercado Livre e na Shopee.")


def palavras(termo):
    return [w for w in re.findall(r"[a-z0-9]+", normalizar(termo)) if w not in _VAZIAS]


def _bate(titulo_norm, tokens):
    """Todas as palavras do pedido aparecem no título (palavra inteira; aceita plural simples)."""
    return all(re.search(rf"\b{re.escape(w)}(s|es)?\b", titulo_norm) for w in tokens)


def _no_comeco(titulo, tokens, ate=6):
    """A primeira palavra do pedido aparece entre as 6 primeiras do título."""
    inicio = re.findall(r"[a-z0-9]+", normalizar(titulo))[:ate]
    return any(w == tokens[0] or w in (tokens[0] + "s", tokens[0] + "es") for w in inicio)


def _chave(item, frase):
    """Ordem: quem tem o pedido como frase no título primeiro; depois o mais barato (por unidade, se houver)."""
    por_un = mensagens.preco_por_unidade(item["titulo"], item["preco"])
    return (frase not in normalizar(item["titulo"]), por_un[0] if por_un else item["preco"])


def do_mercado_livre(termo, estado, ml=None, log=print, maximo=MAX_ML):
    """Produtos com link oficial que batem com o pedido, com o preço conferido agora."""
    from . import lote

    tokens, frase = palavras(termo), " ".join(palavras(termo))
    if not tokens:
        return []
    candidatos = []
    for pid, link in (estado.get("links") or {}).items():
        titulo = ((estado.get("cache") or {}).get(pid) or [None])[0]
        hist = ((estado.get("precos") or {}).get(pid) or {}).get("historico") or []
        if not titulo or not hist or not _bate(normalizar(titulo), tokens):
            continue
        dados = (estado.get("descobertos") or {}).get(pid) or (estado.get("acompanhados") or {}).get(pid) or {}
        if motivo_bloqueio(titulo) or fora_da_faixa(titulo, dados.get("categoria"), dados.get("regra")):
            continue
        candidatos.append({"id": pid, "loja": "ml", "titulo": titulo, "preco": float(hist[-1][1]), "link": link,
                           "imagem": ((estado.get("cache") or {}).get(pid) or [None, None])[1]})
    candidatos.sort(key=lambda i: _chave(i, frase))
    saida = []
    for item in candidatos[:maximo * 2]:  # confere o preço de agora (e se o anúncio do link continua no ar)
        if len(saida) >= maximo:
            break
        if ml is not None:
            try:
                info = ml.catalogo(item["id"], item["titulo"], item["imagem"])
            except Exception as e:  # noqa: BLE001 — sem conferir, não entra
                log(f"Busca: não consegui conferir {item['id']}: {type(e).__name__}")
                continue
            if not info or not info.disponivel or not info.preco:
                continue
            if not lote.conferir_anuncio(estado, item["id"], info, log, getattr(ml, "procurar_anuncio", None)):
                continue
            item = {**item, "preco": float(info.preco), "de": info.preco_original}
        saida.append(item)
    return sorted(saida, key=lambda i: _chave(i, frase))


def da_shopee(termo, shp, log=print, maximo=MAX_SHOPEE):
    """Busca ao vivo na Shopee (API oficial), só o que passa nas regras do Chocalho."""
    if shp is None:
        return []
    from .shopee import MAIS_VENDIDOS, ShopeeErro
    from .shopee_ofertas import aprovado, pontos

    tokens = palavras(termo)
    try:
        achados = shp.buscar(termo, ordem=MAIS_VENDIDOS, limite=30)
    except ShopeeErro as e:
        log(f"Busca: Shopee falhou: {e}")
        return []
    # Só entra quando o que a pessoa pediu está no começo do nome (senão vem acessório que só cita a palavra)
    bons = [p for p in achados if not aprovado(p) and _bate(normalizar(p.titulo), tokens) and _no_comeco(p.titulo, tokens)]
    bons.sort(key=pontos, reverse=True)
    saida = []
    for p in bons[:maximo]:
        try:
            link = shp.link_curto(p.link_produto or p.link, ["busca"]) or p.link
        except ShopeeErro:
            link = p.link
        saida.append({"id": p.id, "loja": "shopee", "titulo": p.titulo, "preco": p.preco, "link": link,
                      "a_partir": bool(p.preco_max and p.preco_max > p.preco * 1.02), "nota": p.nota, "vendas": p.vendas})
    return saida


def montar(termo, itens, agora):
    """Resposta em HTML do Telegram."""
    pedido = html.escape(" ".join((termo or "").split())[:60])
    if not itens:
        return (f"🔎 Não achei agora uma boa oferta de <b>{pedido}</b>.\n"
                "Tente outro nome (ex.: marca ou tamanho) ou procure de novo mais tarde: os preços mudam o dia todo.")
    linhas = [f"🔎 <b>{pedido}</b>: o que achei agora", ""]
    for n, i in enumerate(itens, 1):
        loja = "Shopee" if i["loja"] == "shopee" else "Mercado Livre"
        linhas.append(f"{n}. {html.escape(mensagens._titulo_curto(i['titulo'], 80))}")
        preco = f"{'A partir de ' if i.get('a_partir') else ''}<b>{mensagens.brl(i['preco'])}</b>"
        if i.get("de") and i["de"] > i["preco"]:
            preco = f"De <s>{mensagens.brl(i['de'])}</s> por <b>{mensagens.brl(i['preco'])}</b>"
        por_un = mensagens.preco_por_unidade(i["titulo"], i["preco"]) if not i.get("a_partir") else None
        if por_un:
            preco += f" ({mensagens.brl(por_un[0])} {por_un[1]})"
        linhas.append(f"{preco} · {loja}")
        if i.get("nota") and i.get("vendas"):
            linhas.append(f"⭐ {str(round(i['nota'], 1)).replace('.', ',')} · {mensagens._vendidos(i['vendas'])}")
        linhas.append(f"👉 {html.escape(i['link'])}")
        linhas.append("")
    linhas.append(f"<i>Preços conferidos às {agora:%Hh%M}. {RODAPE}</i>")
    return "\n".join(linhas)


def procurar(termo, estado, agora, ml=None, shp=None, log=print):
    """Resposta pronta para um pedido (ou a explicação de por que não dá)."""
    termo = " ".join((termo or "").split())
    if len(termo) < 3 or len(termo) > 60 or not palavras(termo):
        return "Escreva o nome do produto que você procura. Ex.: <i>fralda G</i> ou <i>mochila infantil</i>."
    motivo = motivo_bloqueio(termo)
    if motivo:
        if "NBCAL" in motivo:
            return ("O Chocalho não divulga mamadeiras, bicos, chupetas nem fórmulas e leites infantis "
                    "(regra de proteção ao aleitamento). Posso procurar outro produto para você.")
        return "Esse tipo de produto o Chocalho não divulga. Posso procurar outro para você."
    itens = do_mercado_livre(termo, estado, ml, log) + da_shopee(termo, shp, log)
    _contar(estado, termo, agora, bool(itens))
    return montar(termo, itens, agora)


# ---------------------------------------------------------------- limite por pessoa e termos mais procurados

def _codigo(chat_id):
    """Código embaralhado da conversa (o repositório é público: o número de quem perguntou não fica guardado)."""
    sal = os.environ.get("TELEGRAM_BOT_TOKEN") or "chocalho"
    return hashlib.sha256(f"{sal}:{chat_id}".encode()).hexdigest()[:12]


def pode(estado, chat_id, agora, limite=LIMITE_POR_HORA):
    """Até 5 buscas por hora por pessoa."""
    reg = estado.setdefault("buscas", {})
    corte = (agora - timedelta(hours=1)).isoformat(timespec="minutes")
    for k in [k for k, v in reg.items() if not [t for t in v if t >= corte]]:
        del reg[k]
    cod = _codigo(chat_id)
    feitas = [t for t in reg.get(cod, []) if t >= corte]
    if len(feitas) >= limite:
        return False
    reg[cod] = feitas + [agora.isoformat(timespec="minutes")]
    return True


def _contar(estado, termo, agora, achou):
    """Conta os termos mais procurados nos últimos 30 dias (sem dizer quem procurou)."""
    reg = estado.setdefault("buscas_termos", {})
    chave = " ".join(palavras(termo))[:40]
    if not chave:
        return
    item = reg.setdefault(chave, {"n": 0, "sem": 0})
    item["n"] += 1
    item["sem"] += 0 if achou else 1
    item["em"] = agora.date().isoformat()
    corte = (agora.date() - timedelta(days=30)).isoformat()
    for k in [k for k, v in reg.items() if v.get("em", "") < corte]:
        del reg[k]


def mais_procurados(estado, n=5):
    reg = estado.get("buscas_termos") or {}
    return sorted(reg.items(), key=lambda kv: -kv[1]["n"])[:n]


def _shopee(log=print):
    if os.environ.get("SHOPEE_ATIVO") != "1":
        return None
    try:
        from .shopee import Shopee
        return Shopee(os.environ.get("SHOPEE_APP_ID"), os.environ.get("SHOPEE_SECRET"))
    except Exception as e:  # noqa: BLE001
        log(f"Busca: Shopee desligada: {type(e).__name__}")
        return None


def atender(msg, tg, ml, estado, agora, log=print, shp=None):
    """Mensagem de alguém que não é o admin, no privado do bot. Só responde com BUSCA_PUBLICA=1."""
    if os.environ.get("BUSCA_PUBLICA") != "1":
        return False
    chat = msg.get("chat") or {}
    texto = (msg.get("text") or "").strip()
    if chat.get("type") != "private" or not texto:
        return False
    if texto.startswith("/start") or normalizar(texto) in ("oi", "ola", "ajuda", "/ajuda", "/help", "menu"):
        resposta = BOAS_VINDAS
    elif not pode(estado, chat.get("id"), agora):
        resposta = "Você já fez várias buscas nesta hora. Tente de novo daqui a pouco. 🙂"
    else:
        termo = re.sub(r"^/?(buscar|achar|procurar|quero)\s+", "", texto, flags=re.I)
        resposta = procurar(termo, estado, agora, ml, shp or _shopee(log), log)
    try:
        tg.enviar_texto(chat.get("id"), resposta, html=True)
    except Exception as e:  # noqa: BLE001 — uma resposta que falha não derruba a rodada
        log(f"Busca: não consegui responder: {type(e).__name__}")
    return True
