"""Cupons do canal oficial "Afiliados e Criadores Mercado Livre" no Telegram.

A cada rodada, lê as mensagens novas do canal com a sua conta do Telegram
(API oficial para usuários, via Telethon), separa os cupons e posta no
Chocalho os gerais e os de bebê, brinquedos e moda.

Formato dos posts do canal (exemplos reais):
    🎟️ MOMENTOPROMO 👉 30% OFF
    Compra mín: R$1 | Desconto máx: R$500
    Válido até 31.12, ou enquanto durarem os estoques...
    🔗 https://bit.ly/...

    🎟️ CLIENTESTOP: 10% → 15% OFF     (atualização de um cupom)
    📱 Tecnologia
"""
import asyncio
import html
import json
import os
import re
import unicodedata
from datetime import timedelta
from pathlib import Path

from . import cupons, mensagens
from .cofre import _fernet
from .telegram import TelegramErro

RAIZ = Path(__file__).resolve().parent.parent
ARQ_SESSAO = RAIZ / "data" / "tg_sessao.enc"
ARQ_LOGIN = RAIZ / "data" / "tg_login.enc"

RE_CUPOM = re.compile(r"🎟️?\s*([A-Z0-9]{3,})\s*(?:👉|:)\s*(.+)")
RE_URL = re.compile(r"https?://\S+")
CATEGORIAS_BOAS = ("beb", "brinquedo", "infantil", "crianc", "moda", "roupa", "calcad", "maternidade", "kids")


def _norm(t):
    t = unicodedata.normalize("NFKD", t or "")
    return "".join(c for c in t if not unicodedata.combining(c)).lower()


def _limpa(t):
    return re.sub(r"^[^\wÀ-ú]+", "", t or "").strip()


def _validade(texto, agora):
    n = _norm(texto)
    m = re.search(r"(\d{1,2})[./](\d{1,2})", texto)
    if m:
        try:
            fim = agora.replace(month=int(m.group(2)), day=int(m.group(1)), hour=23, minute=59, second=0,
                                microsecond=0)
        except ValueError:
            return None
        if fim < agora - timedelta(days=60):
            fim = fim.replace(year=fim.year + 1)
        return fim
    if "hoje" in n:
        return agora.replace(hour=23, minute=59, second=0, microsecond=0)
    return None


def parse(texto, agora):
    """Lista de cupons de uma mensagem do canal."""
    achados, validade_msg, link_msg = [], None, None
    for paragrafo in re.split(r"\n\s*\n", texto or ""):
        atual = None
        for linha in (l.strip() for l in paragrafo.splitlines()):
            if not linha:
                continue
            m = RE_CUPOM.search(linha)
            if m:
                desc = m.group(2).strip()
                antes = None
                if "→" in desc:
                    antes, desc = (x.strip() for x in desc.split("→", 1))
                atual = {"codigo": m.group(1), "desconto": desc, "antes": antes, "categoria": None,
                         "minimo": None, "maximo": None, "validade": None, "link": None}
                achados.append(atual)
                continue
            for parte in (x.strip() for x in linha.split("|")):
                n = _norm(parte)
                if "valid" in n:
                    v = _validade(parte, agora)
                    if atual is not None:
                        atual["validade"] = v
                    else:
                        validade_msg = v
                elif RE_URL.search(parte):
                    url = RE_URL.search(parte).group(0)
                    if atual is not None:
                        atual["link"] = url
                    else:
                        link_msg = url
                elif atual is not None and "compra" in n and "min" in n:
                    atual["minimo"] = parte.split(":", 1)[-1].strip()
                elif atual is not None and "desconto" in n and "max" in n:
                    atual["maximo"] = parte.split(":", 1)[-1].strip()
                elif atual is not None and not atual["categoria"] and not re.search(r"\d", parte) \
                        and 2 < len(_limpa(parte)) < 40:
                    atual["categoria"] = _limpa(parte)
    for c in achados:
        c["validade"] = c["validade"] or validade_msg
        c["link"] = c["link"] or link_msg
    return achados


def relevante(cupom, categorias=None):
    """Cupom geral (sem categoria) ou de uma categoria do nicho."""
    if (categorias or "").strip().lower() == "todas":
        return True
    if not cupom.get("categoria"):
        return True
    alvo = _norm(cupom["categoria"])
    boas = [c.strip() for c in (categorias or "").split(",") if c.strip()] or CATEGORIAS_BOAS
    return any(_norm(b) in alvo for b in boas)


def bloco_html(c):
    e = html.escape
    linhas = [f"<b>🎟️ {e(c['codigo'])}</b> 👉 <b>{e(c['desconto'])}</b>"]
    if c.get("categoria"):
        linhas.append(f"📂 {e(c['categoria'])}")
    regras = [x for x in (f"Compra mín.: {e(c['minimo'])}" if c.get("minimo") else "",
                          f"Desconto máx.: {e(c['maximo'])}" if c.get("maximo") else "") if x]
    if regras:
        linhas.append(" · ".join(regras))
    if c.get("validade"):
        linhas.append(f"⏰ Válido até {c['validade']:%d/%m}")
    if c.get("link"):
        linhas.append(f'👉 <a href="{e(c["link"], quote=True)}">Ativar o cupom</a>')
    return "\n".join(linhas)


def texto_whatsapp(lista):
    partes = ["*🎟️ Cupons do Mercado Livre*", ""]
    for c in lista:
        partes.append(f"*{c['codigo']}* 👉 *{c['desconto']}*")
        if c.get("categoria"):
            partes.append(f"📂 {c['categoria']}")
        regras = " · ".join(x for x in (f"Compra mín.: {c['minimo']}" if c.get("minimo") else "",
                                        f"Desconto máx.: {c['maximo']}" if c.get("maximo") else "") if x)
        if regras:
            partes.append(regras)
        if c.get("validade"):
            partes.append(f"⏰ Válido até {c['validade']:%d/%m}")
        if c.get("link"):
            partes.append(f"👉 {c['link']}")
        partes.append("")
    partes.append(f"_{cupons.RODAPE}_")
    return "\n".join(partes)


def _novo_desconto(estado, c):
    """Mantém o bloco já postado (mínimo, máximo...) e só troca o desconto."""
    post = (estado.get("posts_cupom") or {}).get(str(estado["cupons"][c["codigo"]]["post"])) or {}
    antigo = next((b["html"] for b in post.get("blocos", []) if b["codigo"] == c["codigo"]), None)
    if not antigo:
        return bloco_html(c)
    novo = re.sub(r"👉 <b>[^<]*</b>", f"👉 <b>{html.escape(c['desconto'])}</b> ⬆️", antigo, count=1)
    if c.get("validade"):
        novo = re.sub(r"⏰ Válido até \d\d/\d\d", f"⏰ Válido até {c['validade']:%d/%m}", novo)
    return novo


def tratar_mensagem(texto, tg, cfg, estado, agora, categorias=None, log=print):
    """Posta os cupons novos e avisa das atualizações. Retorna quantos cupons postou."""
    novos, ja = [], cupons.ativos(estado)
    for c in parse(texto, agora):
        if c["codigo"] in ja:
            if c["antes"]:
                cupons.atualizar_bloco(tg, cfg, estado, c["codigo"], _novo_desconto(estado, c),
                                       f"⬆️ Melhorou! O cupom <b>{html.escape(c['codigo'])}</b> agora dá "
                                       f"<b>{html.escape(c['desconto'])}</b>", validade=c.get("validade"))
                log(f"Cupom {c['codigo']} atualizado para {c['desconto']}.")
            continue  # repetido: o canal costuma relembrar os mesmos cupons
        if c["codigo"] in (estado.get("cupons") or {}):
            continue  # já esgotou ou venceu
        if c.get("validade") and c["validade"] < agora:
            continue
        if not relevante(c, categorias):
            log(f"Cupom {c['codigo']} ignorado (categoria: {c['categoria']}).")
            continue
        novos.append(c)
    if not novos:
        return 0
    titulo = "🎟️ <b>Cupom do Mercado Livre</b>" if len(novos) == 1 else "🎟️ <b>Cupons do Mercado Livre</b>"
    cupons.publicar(tg, cfg, estado, titulo, [(c["codigo"], bloco_html(c), c["validade"]) for c in novos], agora)
    log(f"Cupons postados: {', '.join(c['codigo'] for c in novos)}.")
    if cfg.admin_chat:
        wa = texto_whatsapp(novos)
        try:
            tg.enviar_texto(cfg.admin_chat, "📋 Cupons para o WhatsApp:\n\n<pre>" + html.escape(wa) + "</pre>",
                            html=True, botoes=mensagens.botoes_compartilhar(wa, wa[:270]))
        except TelegramErro:
            pass
    return len(novos)


# ---------- conexão com o Telegram (conta de usuário) ----------

def _chave(api_hash):
    return _fernet(api_hash + ":telegram")


def guardar_seguro(dados, api_hash, caminho):
    Path(caminho).parent.mkdir(parents=True, exist_ok=True)
    Path(caminho).write_bytes(_chave(api_hash).encrypt(json.dumps(dados).encode()) + b"\n")


def ler_seguro(api_hash, caminho):
    if not Path(caminho).exists():
        return None
    return json.loads(_chave(api_hash).decrypt(Path(caminho).read_bytes().strip()))


async def _resolver(client, convite):
    convite = convite.strip()
    m = re.search(r"(?:\+|joinchat/)([\w-]+)", convite)
    if m:
        from telethon.tl.functions.messages import CheckChatInviteRequest

        r = await client(CheckChatInviteRequest(m.group(1)))
        if getattr(r, "chat", None) is not None and r.__class__.__name__ == "ChatInviteAlready":
            return r.chat
        raise RuntimeError("a conta do Telegram ainda não entrou no canal de cupons")
    return await client.get_entity(convite.rsplit("/", 1)[-1].lstrip("@"))


async def _buscar(api_id, api_hash, sessao, convite, desde):
    from telethon import TelegramClient
    from telethon.sessions import StringSession

    client = TelegramClient(StringSession(sessao), int(api_id), api_hash)
    await client.connect()
    try:
        if not await client.is_user_authorized():
            raise RuntimeError("o login do Telegram expirou; rode de novo o 'Conectar Telegram'")
        chat = await _resolver(client, convite)
        msgs = []
        async for m in client.iter_messages(chat, min_id=desde or 0, limit=1 if not desde else 40):
            msgs.append((m.id, m.message or ""))
        return sorted(msgs)
    finally:
        await client.disconnect()


def processar(tg, cfg, estado, agora, log=print):
    """Lê o canal de cupons e posta o que for novo. Sem configuração, não faz nada."""
    api_id, api_hash = os.environ.get("TG_API_ID"), os.environ.get("TG_API_HASH")
    convite = os.environ.get("TG_CANAL_CUPONS")
    if not (api_id and api_hash and convite and ARQ_SESSAO.exists()):
        return
    try:
        sessao = ler_seguro(api_hash, ARQ_SESSAO)["sessao"]
        desde = estado.get("cupons_ml_ultimo")
        msgs = asyncio.run(_buscar(api_id, api_hash, sessao, convite, desde))
    except Exception as e:  # noqa: BLE001
        log(f"Aviso: não consegui ler o canal de cupons: {e}")
        if estado.get("cupons_ml_erro_dia") != agora.date().isoformat() and cfg.admin_chat:
            estado["cupons_ml_erro_dia"] = agora.date().isoformat()
            try:
                tg.enviar_texto(cfg.admin_chat, f"⚠️ Não consegui ler o canal de cupons do Mercado Livre: {e}")
            except TelegramErro:
                pass
        return
    if not msgs:
        return
    if not desde:
        # Primeira vez: só marca a posição, para não postar cupons antigos
        estado["cupons_ml_ultimo"] = msgs[-1][0]
        log("Canal de cupons conectado. A partir de agora posto os cupons novos.")
        return
    for mid, texto in msgs:
        try:
            tratar_mensagem(texto, tg, cfg, estado, agora, os.environ.get("CUPONS_CATEGORIAS"), log)
        except TelegramErro as e:
            log(f"Aviso: erro ao postar cupom: {e}")
        estado["cupons_ml_ultimo"] = mid
