"""Mensagens que você manda para o bot no privado.

- Link de afiliado (meli.la/...)  → o bot descobre o produto e posta no canal
- "cupom ..."                      → formata o cupom e posta no canal
- "resumo"                         → números do canal
- Vários meli.la de uma vez        → resposta de um lote do Linkbuilder
"""
import html
import random
import re
import unicodedata
from datetime import timedelta

import requests

from . import estado as est
from . import lote, mensagens
from .filtros import motivo_bloqueio
from .mercadolivre import AcessoNegado, ErroML
from .ofertas import Oferta
from .telegram import TelegramErro

RE_PRODUTO_ML = re.compile(r"https?://\S*mercadoli(?:vre|bre)\.com\S*", re.I)
MAX_AVULSOS = 5  # acima disso, a mensagem é tratada como resposta de lote
UA = {
    "User-Agent": "Mozilla/5.0 (iPhone; CPU iPhone OS 17_0 like Mac OS X) AppleWebKit/605.1.15 Mobile/15E148",
    "Accept-Language": "pt-BR",
}

AJUDA = (
    "🪇 <b>O que você pode me mandar</b>\n\n"
    "🔗 <b>Um link de afiliado</b> (meli.la/...) → eu descubro o produto e posto no canal\n\n"
    "🎟️ <b>cupom</b> + o texto do cupom → eu formato e posto. Ex.:\n"
    "<code>cupom 20% OFF em brinquedos acima de R$ 99, código BRINCA20</code>\n\n"
    "📊 <b>resumo</b> → números do canal agora\n\n"
    "📦 Para os lotes do Linkbuilder, cole todos os links gerados numa mensagem só.\n\n"
    "<i>Eu leio as mensagens a cada 20 min, das 8h às 22h.</i>"
)


def _norm(texto):
    texto = unicodedata.normalize("NFKD", texto or "")
    return "".join(c for c in texto if not unicodedata.combining(c)).lower().strip()


# ---------- descobrir o produto de um meli.la ----------

def resolver_meli(link, session=None):
    """Abre o link (a sua página social) e pega o produto em destaque.

    Retorna (tipo, id) ou None. O produto em destaque é o primeiro anúncio da
    página; o product_id dele aparece logo depois do item_id.
    """
    s = session or requests
    try:
        r = s.get(link, headers=UA, timeout=25)
    except requests.RequestException:
        return None
    texto = r.text or ""
    item = re.search(r'"item_id":"(MLB\d+)"', texto)
    prod = re.search(r'"product_id":"(MLB\d+)"', texto[item.start():] if item else texto)
    if prod and (not item or prod.start() < 3000):
        return "catalogo", prod.group(1)
    if item:
        return "item", item.group(1)
    return None


# ---------- postar ----------

def enviar_copias(tg, chat, oferta, rng=random):
    """Mensagem com o texto do WhatsApp e botões que abrem WhatsApp e X já preenchidos."""
    wa = mensagens.montar_whatsapp(oferta, rng)
    tg.enviar_texto(chat, "📋 Toque no bloco abaixo para copiar e cole no WhatsApp:\n\n<pre>"
                    + html.escape(wa) + "</pre>", html=True,
                    botoes=mensagens.botoes_compartilhar(wa, mensagens.montar_x(oferta)))


def postar_link(link, tg, ml, estado, cfg, agora, session=None, rng=random):
    """Posta no canal a oferta de um link de afiliado. Retorna a resposta para você."""
    achado = resolver_meli(link, session)
    if not achado:
        return f"⚠️ Não consegui descobrir o produto de {link}. Confira se o link abre a oferta."
    tipo, pid = achado
    try:
        info = ml.catalogo(pid) if tipo == "catalogo" else ml.itens([pid]).get(pid)
    except (ErroML, AcessoNegado) as e:
        return f"⚠️ Não consegui consultar o produto {pid} no Mercado Livre ({e})."
    if not info or not info.preco or not info.disponivel:
        return f"⚠️ O produto {pid} está sem preço ou sem estoque agora. Não postei."
    motivo = motivo_bloqueio(info.titulo)
    if motivo:
        return f"🚫 Não posso postar “{info.titulo[:60]}”: {motivo}."

    categoria = (estado.get("descobertos", {}).get(pid) or estado.get("manuais", {}).get(pid) or {}).get(
        "categoria", "outros")
    preco = float(info.preco)
    de = float(info.preco_original) if (info.preco_original or 0) > preco else None
    oferta = Oferta(pid, info.titulo, preco, de, (1 - preco / de) if de else 0.0,
                    None, False, link, info.imagem, categoria)

    # Guarda o link e passa a acompanhar o produto para repostar no futuro
    estado["links"][pid] = link
    if pid not in estado.get("descobertos", {}):
        estado.setdefault("manuais", {})[pid] = {"tipo": tipo, "categoria": categoria}
    try:
        tg.enviar_oferta(cfg.canal, mensagens.montar_telegram(oferta, rng), oferta.imagem)
    except TelegramErro as e:
        return f"⚠️ Não consegui postar no canal: {e}"
    est.registrar_post(estado, pid, preco, agora, info.titulo, oferta.desconto)
    try:
        enviar_copias(tg, cfg.admin_chat, oferta, rng)
    except TelegramErro:
        pass
    desc = f" (-{round(oferta.desconto * 100)}%)" if de else ""
    return f"✅ Postado: {info.titulo[:70]} — {mensagens.brl(preco)}{desc}"


def postar_cupom(texto, tg, cfg):
    corpo = re.sub(r"^\s*/?cupom\s*[:\-–]?\s*", "", texto, flags=re.I).strip()
    if not corpo:
        return "Escreva o cupom depois da palavra cupom. Ex.: cupom 15% OFF em fraldas, código FRALDA15"
    tem_link = bool(lote.RE_MELI.search(corpo))
    rodape = "Cupons têm quantidade e prazo limitados."
    if tem_link:
        rodape += " #publi · link de afiliado"
    msg = f"🎟️ <b>Cupom pra economizar!</b>\n\n{html.escape(corpo)}\n\n<i>{rodape}</i>"
    try:
        tg.enviar_texto(cfg.canal, msg, html=True)
    except TelegramErro as e:
        return f"⚠️ Não consegui postar o cupom: {e}"
    wa = f"*🎟️ Cupom pra economizar!*\n\n{corpo}\n\n_{rodape}_"
    try:
        tg.enviar_texto(cfg.admin_chat, "📋 Cupom para o WhatsApp:\n\n<pre>" + html.escape(wa) + "</pre>",
                        html=True, botoes=mensagens.botoes_compartilhar(wa, "🎟️ " + corpo[:240]))
    except TelegramErro:
        pass
    return "✅ Cupom postado no canal!"


# ---------- resumo ----------

def montar_resumo(estado, cfg, tg, agora):
    hoje = agora.date().isoformat()
    ontem = (agora.date() - timedelta(days=1)).isoformat()
    linhas = [f"📊 <b>Resumo do Chocalho — {agora:%d/%m}</b>", ""]

    hist = estado.setdefault("membros_hist", {})
    try:
        total = tg.membros(cfg.canal)
        hist[hoje] = total
        for dia in sorted(hist)[:-8]:
            del hist[dia]
        dif = f" ({total - hist[ontem]:+d} desde ontem)" if ontem in hist else ""
        linhas.append(f"👥 Membros: <b>{total}</b>{dif}")
    except (TelegramErro, AttributeError):
        pass
    mov = (estado.get("membros_dia") or {}).get(hoje)
    if mov:
        linhas.append(f"   ➕ {mov.get('entrou', 0)} entraram · ➖ {mov.get('saiu', 0)} saíram hoje")

    linhas.append(f"📣 Posts hoje: <b>{est.posts_hoje(estado, agora)}</b> (limite {cfg.max_por_dia})")
    linhas.append(f"🔗 Produtos com link oficial: {len(estado.get('links', {}))}")
    if estado.get("aguardando_link"):
        linhas.append(f"⏳ Ofertas boas esperando link: {estado['aguardando_link']}")
    feitos = (estado.get("lotes_dia") or {}).get(hoje, 0)
    pend = " (1 esperando sua resposta)" if (estado.get("lote") or {}).get("dia") == hoje else ""
    linhas.append(f"📦 Lotes hoje: {feitos} de {cfg.lotes_por_dia}{pend}")

    de_hoje = [p for p in estado.get("postados", {}).values()
               if str(p.get("quando", "")).startswith(hoje) and p.get("titulo")]
    de_hoje.sort(key=lambda p: p.get("desconto") or 0, reverse=True)
    if de_hoje:
        linhas += ["", "🏆 <b>Maiores descontos postados hoje</b>"]
        for p in de_hoje[:3]:
            linhas.append(f"• -{round((p.get('desconto') or 0) * 100)}% {html.escape(p['titulo'][:55])}")
    return "\n".join(linhas)


def talvez_resumo_diario(tg, estado, cfg, agora, log=print):
    """Manda o resumo uma vez por dia, na última hora de postagem."""
    hoje = agora.date().isoformat()
    if not cfg.admin_chat or agora.hour < cfg.hora_fim - 1 or agora.hour >= cfg.hora_fim:
        return
    if estado.get("resumo_enviado") == hoje:
        return
    try:
        tg.enviar_texto(cfg.admin_chat, montar_resumo(estado, cfg, tg, agora), html=True)
        estado["resumo_enviado"] = hoje
        log("Resumo diário enviado.")
    except TelegramErro as e:
        log(f"Aviso: não consegui mandar o resumo: {e}")


# ---------- leitura das mensagens ----------

def _registrar_membro(estado, cm, agora):
    dentro = {"member", "administrator", "creator", "restricted"}
    antes = (cm.get("old_chat_member") or {}).get("status")
    depois = (cm.get("new_chat_member") or {}).get("status")
    hoje = agora.date().isoformat()
    dia = (estado.get("membros_dia") or {}).get(hoje, {"entrou": 0, "saiu": 0})
    if antes not in dentro and depois in dentro:
        dia["entrou"] += 1
    elif antes in dentro and depois not in dentro:
        dia["saiu"] += 1
    estado["membros_dia"] = {hoje: dia}


def tratar_texto(texto, tg, ml, estado, cfg, agora, session=None, rng=random):
    """Decide o que fazer com uma mensagem sua. Retorna a resposta (ou None)."""
    t = (texto or "").strip()
    n = _norm(t)
    if n.startswith(("cupom", "/cupom")):
        return postar_cupom(t, tg, cfg)
    if n in ("resumo", "/resumo", "status", "/status"):
        return montar_resumo(estado, cfg, tg, agora)
    links = lote.RE_MELI.findall(t)
    if links:
        pendente = estado.get("lote")
        if pendente and len(links) == len(pendente["ids"]):
            return lote.aplicar_resposta(estado, t)[1]
        if len(links) <= MAX_AVULSOS:
            respostas = [postar_link(l, tg, ml, estado, cfg, agora, session, rng)
                         for l in dict.fromkeys(links)]
            return "\n".join(respostas)
        return lote.aplicar_resposta(estado, t)[1]
    if RE_PRODUTO_ML.search(t):
        return ("Para postar, preciso do <b>link de afiliado</b>: no app do Mercado Livre, "
                "abra o produto → Compartilhar → copie o link (meli.la/...) e me mande.")
    return AJUDA


def processar(tg, ml, estado, cfg, agora, log=print, session=None, rng=random):
    """Lê as mensagens novas (suas e de entradas/saídas do canal)."""
    try:
        updates = tg.atualizacoes(offset=estado.get("tg_offset"))
    except Exception as e:  # noqa: BLE001
        log(f"Aviso: não consegui ler mensagens do Telegram: {e}")
        return
    for u in updates:
        estado["tg_offset"] = u["update_id"] + 1
        if u.get("chat_member"):
            _registrar_membro(estado, u["chat_member"], agora)
            continue
        msg = u.get("message") or {}
        if str((msg.get("chat") or {}).get("id")) != str(cfg.admin_chat):
            continue
        resposta = tratar_texto(msg.get("text") or msg.get("caption") or "", tg, ml, estado, cfg, agora,
                                session, rng)
        if resposta:
            log(re.sub(r"<[^>]+>", "", resposta)[:300])
            try:
                tg.enviar_texto(cfg.admin_chat, resposta, html=True)
            except TelegramErro:
                try:
                    tg.enviar_texto(cfg.admin_chat, re.sub(r"<[^>]+>", "", resposta))
                except TelegramErro:
                    pass
