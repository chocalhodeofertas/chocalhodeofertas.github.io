"""Mensagens que você manda para o bot no privado.

- Link de afiliado (meli.la/...)  → o bot descobre o produto e posta no canal
- "cupom ..."                      → formata o cupom e posta no canal
- "resumo"                         → números do canal
- Vários meli.la de uma vez        → resposta de um lote do Linkbuilder
"""
import html
import os
import random
import re
import unicodedata
from datetime import datetime, timedelta

import requests

from . import estado as est
from . import cupons, lote, mensagens, whatsapp
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
    "<code>cupom 20% OFF em brinquedos acima de R$ 99, código BRINCA20, até 10/11</code>\n"
    "(com a data, eu marco como encerrado sozinho quando vencer)\n"
    "🛍️ <b>cupom shopee</b> + o texto → posto no canal e no grupo com o seu link da página de cupons\n"
    "📣 <b>marcar</b> + texto ou link meli.la → vai para o grupo do WhatsApp com todos marcados, sem “@” (até 2/dia)\n\n"
    "❌ <b>esgotou</b> + código → aviso no canal que o cupom acabou\n"
    "✅ <b>geral</b> + código → cupom sem categoria que você testou passa a entrar nas ofertas · <b>restrito</b> + código desfaz\n\n"
    "📊 <b>resumo</b> → números do canal agora\n"
    "🚫 <b>bloquear</b> + palavra → o bot para de postar produtos com ela · <b>desbloquear</b> + palavra · <b>bloqueados</b>\n"
    "📬 <b>fila</b> → o que vai sair no WhatsApp · <b>tirar 2</b> → cancela o item 2 · <b>limpar fila</b>\n\n"
    "🔎 <b>buscar</b> + produto → melhores ofertas agora · <b>pegar 1 3</b> → manda para o Linkbuilder\n"
    "🙋 <b>achar</b> + produto → a resposta que um membro receberia na busca sob pedido\n"
    "👀 <b>vigiar</b> + produto → aviso quando entrar em promoção · <b>vigias</b> · <b>parar</b> + produto\n"
    "🗂️ <b>categorias</b> → prévia das categorias novas (roupas, games, livros...) · <b>aprovar categorias</b>\n"
    "🎯 <b>temas</b> → quantas promoções cada tema tem agora\n"
    "🎠 <b>carrossel brinquedos</b> / 🎬 <b>reel brinquedos</b> → temático do tema que você escolher\n"
    "🖼️ <b>insta</b> + link meli.la → post, legenda e story do produto escolhido\n"
    "📲 Carrossel e post chegam com ✅ Aprovar / ❌ Recusar: aprovado, o bot publica no Instagram sozinho\n\n"
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

ALERTA_QUEDA = 0.20      # preço 20% abaixo do que vinha custando no histórico do bot
ALERTA_QUEDA_SELO = 0.10  # ou 10% abaixo, quando também é o menor preço em 14+ dias
ALERTA_DIAS_MIN = 7


def motivo_oferta_forte(estado, oferta, agora):
    """Por que a oferta é fora da curva (ou None). Só pelo histórico do próprio bot: o "de" do anúncio não conta."""
    tipico, dias = est.preco_tipico(estado, oferta.id, agora)
    if not tipico or dias < ALERTA_DIAS_MIN or not oferta.preco:
        return None
    queda = round(1 - oferta.preco / tipico, 4)
    if queda >= ALERTA_QUEDA:
        return (f"{round(queda * 100)}% abaixo do que vinha custando ({mensagens.brl(tipico)}) "
                f"nos últimos {min(dias, 30)} dias")
    if getattr(oferta, "selo_dias", None) and queda >= ALERTA_QUEDA_SELO:
        return f"menor preço que o Chocalho viu em {oferta.selo_dias} dias"
    return None


def nota_sem_selo(estado, oferta, agora):
    """Linha do aviso explicando por que o post saiu sem o selo de menor preço (decisão do Leonardo, 17/11)."""
    if getattr(oferta, "selo_dias", None):
        return ""
    from .ofertas import SELO_DIAS_MIN

    _, dias = est.preco_tipico(estado, oferta.id, agora)
    if dias < SELO_DIAS_MIN:
        return (f"ℹ️ O post saiu sem selo: o selo de menor preço precisa de {SELO_DIAS_MIN} dias de histórico "
                f"e este produto tem {dias}.\n")
    return "ℹ️ O post saiu sem selo: o preço não bateu a regra do selo de menor preço (ex.: já esteve mais barato).\n"


def alertar_oferta_forte(tg, cfg, estado, oferta, agora, loja="ml"):
    """Avisa você na hora quando sai uma oferta fora da curva (para destacar nos Stories, por exemplo).
    Até ALERTA_MAX_DIA avisos por dia (padrão 5; 0 desliga) e um por produto."""
    limite = int(os.environ.get("ALERTA_MAX_DIA") or 5)
    if not getattr(cfg, "admin_chat", "") or limite <= 0:
        return False
    hoje = agora.date().isoformat()
    reg = estado.get("alertas")
    if not isinstance(reg, dict) or reg.get("dia") != hoje:
        reg = estado["alertas"] = {"dia": hoje, "ids": []}
    if oferta.id in reg["ids"] or len(reg["ids"]) >= limite:
        return False
    motivo = motivo_oferta_forte(estado, oferta, agora)
    if not motivo:
        return False
    onde = "Shopee" if loja == "shopee" else "Mercado Livre"
    texto = (f"🚨 <b>Oferta forte no canal agora</b> ({onde})\n{html.escape((oferta.titulo or '')[:90])}\n"
             f"<b>{mensagens.brl(oferta.preco)}</b> · {motivo}\n{html.escape(oferta.link or '')}\n"
             f"{nota_sem_selo(estado, oferta, agora)}"
             f"<i>Boa para destacar nos Stories. Aviso {len(reg['ids']) + 1} de até {limite} hoje.</i>")
    try:
        tg.enviar_texto(cfg.admin_chat, texto, html=True)
    except TelegramErro:
        return False
    reg["ids"].append(oferta.id)
    return True


def enviar_copias(tg, chat, oferta, rng=random, fonte=None):
    """Arte da oferta + texto do WhatsApp com botões que abrem WhatsApp e X já preenchidos.
    fonte: canal do Telegram de onde a oferta foi copiada (espelho), para você saber a origem."""
    if hasattr(tg, "enviar_foto"):
        try:
            from . import arte

            tg.enviar_foto(chat, arte.gerar(oferta), "🖼️ Arte para story, feed ou grupo")
        except Exception:  # noqa: BLE001
            pass  # sem arte, segue com o texto
    wa = mensagens.montar_whatsapp(oferta, rng)
    origem = f"🔁 <b>Copiada do canal @{html.escape(fonte)}</b>\n" if fonte else ""
    tg.enviar_texto(chat, origem + "📋 Toque no bloco abaixo para copiar e cole no WhatsApp:\n\n<pre>"
                    + html.escape(wa) + "</pre>", html=True,
                    botoes=mensagens.botoes_compartilhar(wa, mensagens.montar_x(oferta)))


MARCAR_MAX_DIA = 2  # menção oculta incomoda: no máximo 2 por dia, mesmo pedindo


def marcar(texto, tg, ml, estado, cfg, agora, session=None, rng=random):
    """`marcar <texto>` ou `marcar <link meli.la>`: vai para o grupo do WhatsApp com todos os membros marcados
    sem "@" no texto (menção oculta). Só quando o Leonardo pede; o canal do Telegram não muda."""
    corpo = re.sub(r"^\s*/?marcar\b\s*", "", texto or "", flags=re.I).strip()
    if not corpo:
        return ("Mande <b>marcar</b> + o texto (ou + um link meli.la) que vai para o grupo do WhatsApp com todo mundo "
                "marcado, sem aparecer “@”. Ex.:\n<code>marcar 🥄 Separei ofertas para a introdução alimentar!</code>")
    hoje = agora.date().isoformat()
    reg = estado.get("marcacoes")
    if not isinstance(reg, dict) or reg.get("dia") != hoje:
        reg = estado["marcacoes"] = {"dia": hoje, "n": 0}
    if reg["n"] >= MARCAR_MAX_DIA:
        return (f"⚠️ Já foram {MARCAR_MAX_DIA} mensagens com todo mundo marcado hoje. Para não incomodar o grupo "
                "(e não arriscar denúncia), a próxima só amanhã.")
    links = lote.RE_MELI.findall(corpo)
    if links:
        resposta = postar_link(links[0], tg, ml, estado, cfg, agora, session, rng, mencionar=True)
        if resposta and resposta.startswith(("⚠️", "🚫")):
            return resposta
        reg["n"] += 1
        return (resposta or "✅ Postado.") + "\n📣 No grupo do WhatsApp ela vai com todo mundo marcado (sem “@”)."
    if not whatsapp.enfileirar(corpo, None, agora, mencionar=True):
        return "⚠️ O WhatsApp não está ligado nesta rodada; não consegui colocar a mensagem na fila."
    reg["n"] += 1
    return ("📣 Na fila do grupo do WhatsApp, na frente das ofertas, com todo mundo marcado (sem “@”). "
            f"Marcações hoje: {reg['n']} de {MARCAR_MAX_DIA}.")


def postar_link(link, tg, ml, estado, cfg, agora, session=None, rng=random, mencionar=False):
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
    from .cupom_oferta import escolher_cupom

    oferta.cupom = escolher_cupom(estado, oferta, agora, session, log=lambda m: None)
    try:
        tg.enviar_oferta(cfg.canal, mensagens.montar_telegram(oferta, rng), oferta.imagem)
    except TelegramErro as e:
        return f"⚠️ Não consegui postar no canal: {e}"
    whatsapp.enfileirar_oferta(oferta, mensagens.montar_whatsapp(oferta, rng), agora, mencionar=mencionar)
    est.registrar_post(estado, pid, preco, agora, info.titulo, oferta.desconto)
    if oferta.cupom:
        est.contar_dia(estado, agora, "com_cupom")
    try:
        enviar_copias(tg, cfg.admin_chat, oferta, rng)
    except TelegramErro:
        pass
    desc = f" (-{round(oferta.desconto * 100)}%)" if de else ""
    return f"✅ Postado: {info.titulo[:70]} — {mensagens.brl(preco)}{desc}"


def _oferta_do_link(link, ml, estado, session=None):
    """Acha a oferta de um link meli.la: primeiro na vitrine, senão consulta o Mercado Livre."""
    for i in (estado.get("vitrine") or {}).get("itens", []):
        if i.get("link") == link:
            return Oferta(i["id"], i["titulo"], i["preco"], i.get("de"), i.get("desconto") or 0.0,
                          None, False, link, i.get("imagem"), i.get("categoria", "outros")), None
    achado = resolver_meli(link, session)
    if not achado:
        return None, f"⚠️ Não consegui descobrir o produto de {link}."
    tipo, pid = achado
    try:
        info = ml.catalogo(pid) if tipo == "catalogo" else ml.itens([pid]).get(pid)
    except (ErroML, AcessoNegado) as e:
        return None, f"⚠️ Não consegui consultar o produto {pid} ({e})."
    if not info or not info.preco or not info.disponivel:
        return None, f"⚠️ O produto {pid} está sem preço ou sem estoque agora."
    preco = float(info.preco)
    de = float(info.preco_original) if (info.preco_original or 0) > preco else None
    return Oferta(pid, info.titulo, preco, de, (1 - preco / de) if de else 0.0,
                  None, False, link, info.imagem, "outros"), None


def relatorio_areas(tg, ml, cfg, log=print):
    """Mostra as categorias que o bot achou para as áreas novas e exemplos de produtos (não posta nada)."""
    from .descoberta import explorar_areas
    from .filtros import fora_da_faixa

    nomes = {"roupa": "👕 Roupas", "game": "🎮 Games", "livro": "📚 Livros", "escola": "✏️ Escola",
             "esporte": "⚽ Esporte", "casa": "🏠 Casa e quarto", "festa": "🎉 Festa"}
    for area, cats in explorar_areas(ml, log).items():
        linhas = [f"<b>{nomes.get(area, area)}</b>", "Categorias: " + ", ".join(html.escape(n) for _, n, _, _ in cats),
                  "", "Exemplos do que entraria:"]
        ok, barrados = 0, 0
        for cat, _, regra, qtd in cats:
            if ok >= 5:
                break
            try:
                lista = [i for t, i in ml.mais_vendidos(cat) if t == "catalogo"][:qtd]
            except (ErroML, AcessoNegado):
                continue
            achou = 0
            for pid in lista:
                if ok >= 5 or achou >= 2:
                    break
                try:
                    info = ml.catalogo(pid)
                except (ErroML, AcessoNegado):
                    continue
                if not info or not info.titulo:
                    continue
                if motivo_bloqueio(info.titulo) or fora_da_faixa(info.titulo, area, regra):
                    barrados += 1
                    continue
                linhas.append(f"• {html.escape(info.titulo[:70])}")
                ok += 1
                achou += 1
        if not ok:
            linhas.append("(nenhum produto infantil entre os mais vendidos agora)")
        if barrados:
            linhas.append(f"🚫 {barrados} produto(s) de adulto/fora do nicho foram barrados pelos filtros.")
        tg.enviar_texto(cfg.admin_chat, "\n".join(linhas), html=True)
    return ("Se estiver tudo certo, mande <b>aprovar categorias</b> para o bot começar a usar. "
            "Os marcados com 🚫 são barrados pelos filtros.")


def postar_insta(link, tg, ml, estado, cfg, session=None, rng=random, agora=None):
    """Gera o post do Instagram de um produto escolhido por você (não posta no canal)."""
    oferta, erro = _oferta_do_link(link, ml, estado, session)
    if erro:
        return erro
    motivo = motivo_bloqueio(oferta.titulo)
    if motivo:
        return f"🚫 Não posso usar “{oferta.titulo[:60]}”: {motivo}."
    from . import conteudo
    conteudo.enviar_post_produto(tg, cfg.admin_chat, oferta, rng, session, estado=estado, agora=agora)
    return None


RE_CODIGO = re.compile(r"c[oó]digo\s*[:\-]?\s*([A-Za-z0-9_\-]{3,})", re.I)
RE_DATA = re.compile(r"at[eé]\s+(?:o\s+dia\s+)?(\d{1,2})/(\d{1,2})(?:/(\d{2,4}))?"
                     r"(?:\s*(?:[àa]s)?\s*(\d{1,2})\s*(?:h|:)\s*(\d{2})?)?", re.I)
RE_HOJE = re.compile(r"(?:s[oó]\s+)?hoje|at[eé]\s+(?:[àa]s\s+)?(\d{1,2})\s*(?:h|:)\s*(\d{2})?", re.I)


def extrair_codigo(corpo):
    m = RE_CODIGO.search(corpo)
    if m:
        return m.group(1).upper()
    # Sem a palavra "código": pega uma palavra toda em maiúsculas com 4+ letras/números
    cands = [w for w in re.findall(r"\b[A-Z0-9]{4,}\b", corpo) if not w.isdigit() and w not in ("OFF", "FRETE")]
    return cands[-1] if cands else None


def extrair_validade(corpo, agora):
    """'até 10/11', 'até 10/11 às 18h', 'só hoje', 'até 23h59' → datetime (ou None)."""
    m = RE_DATA.search(corpo)
    if m:
        dia, mes, ano, h, mi = m.groups()
        ano = int(ano) + (2000 if ano and len(ano) == 2 else 0) if ano else agora.year
        try:
            fim = agora.replace(year=ano, month=int(mes), day=int(dia),
                                hour=int(h) if h else 23, minute=int(mi) if mi else (0 if h else 59), second=0, microsecond=0)
        except ValueError:
            return None
        if not m.group(3) and fim < agora - timedelta(days=60):
            fim = fim.replace(year=fim.year + 1)  # "até 05/01" dito em dezembro
        return fim
    m = RE_HOJE.search(corpo)
    if m:
        h, mi = (m.group(1), m.group(2)) if m.group(1) else ("23", "59")
        try:
            return agora.replace(hour=int(h), minute=int(mi or 0), second=0, microsecond=0)
        except ValueError:
            return None
    return None


LINK_CUPONS_SHOPEE = "https://s.shopee.com.br/8fTxwjM742"  # link oficial do Leonardo para a página de cupons


def link_cupons_shopee():
    return os.environ.get("SHOPEE_CUPONS_LINK") or LINK_CUPONS_SHOPEE


def postar_cupom_shopee(texto, tg, cfg, estado=None, agora=None):
    """`cupom shopee <texto>`: você repassa um cupom da Shopee (ex.: o que chega na notificação do app)
    e o bot posta no canal e põe na fila do grupo, com o seu link da página de cupons."""
    corpo = re.sub(r"^\s*/?cupom\s+(da\s+)?shopee\s*[:\-–]?\s*", "", texto, flags=re.I).strip()
    if not corpo:
        return ("Escreva o cupom depois de <b>cupom shopee</b>. Ex.:\n"
                "<code>cupom shopee R$ 20 OFF acima de R$ 150, código BEBE20, até 20/11</code>")
    agora = agora or datetime.now()
    estado = estado if estado is not None else {}
    link = link_cupons_shopee()
    rodape = "Cupons têm quantidade e prazo limitados. #publi · link de afiliado"
    codigo = extrair_codigo(corpo)
    validade = extrair_validade(corpo, agora)
    bloco = f"{html.escape(corpo)}\n👉 <a href=\"{html.escape(link, quote=True)}\">Ativar na página de cupons da Shopee</a>"
    try:
        cupons.publicar(tg, cfg, estado, "🎟️ <b>Cupom da Shopee</b>", [(codigo, bloco, validade)], agora, rodape)
    except TelegramErro as e:
        return f"⚠️ Não consegui postar o cupom: {e}"
    wa = f"*🎟️ Cupom da Shopee*\n\n{corpo}\n\n👉 Ative aqui: {link}\n\n_{rodape}_"
    na_fila = whatsapp.enfileirar(wa, None, agora, loja="shopee")
    partes = ["✅ Cupom da Shopee postado no canal" + (" e na fila do grupo do WhatsApp!" if na_fila else "!")]
    if validade:
        partes.append(f"⏰ Vale até {validade:%d/%m às %H:%M}: aí eu marco como encerrado sozinho.")
    partes.append(f"Quando esgotar, me mande: <code>esgotou {html.escape(codigo)}</code>" if codigo
                  else "Quando esgotar, me mande só: <code>esgotou</code>")
    return "\n".join(partes)


def postar_cupom(texto, tg, cfg, estado=None, agora=None):
    corpo = re.sub(r"^\s*/?cupom\s*[:\-–]?\s*", "", texto, flags=re.I).strip()
    if not corpo:
        return "Escreva o cupom depois da palavra cupom. Ex.: cupom 15% OFF em fraldas, código FRALDA15, até 10/11"
    tem_link = bool(lote.RE_MELI.search(corpo))
    rodape = "Cupons têm quantidade e prazo limitados."
    if tem_link:
        rodape += " #publi · link de afiliado"
    codigo = extrair_codigo(corpo)
    validade = extrair_validade(corpo, agora) if agora else None
    estado = estado if estado is not None else {}
    try:
        cupons.publicar(tg, cfg, estado, "🎟️ <b>Cupom pra economizar!</b>",
                        [(codigo, html.escape(corpo), validade)], agora or datetime.now(), rodape)
    except TelegramErro as e:
        return f"⚠️ Não consegui postar o cupom: {e}"
    wa = f"*🎟️ Cupom pra economizar!*\n\n{corpo}\n\n_{rodape}_"
    try:
        tg.enviar_texto(cfg.admin_chat, "📋 Cupom para o WhatsApp:\n\n<pre>" + html.escape(wa) + "</pre>",
                        html=True, botoes=mensagens.botoes_compartilhar(wa, "🎟️ " + corpo[:240]))
    except TelegramErro:
        pass
    partes = ["✅ Cupom postado no canal!"]
    if validade:
        partes.append(f"⏰ Vale até {validade:%d/%m às %H:%M}: aí eu marco como encerrado sozinho.")
    if codigo:
        partes.append(f"Quando esgotar, me mande: <code>esgotou {html.escape(codigo)}</code>")
    else:
        partes.append("Não achei o código. Quando esgotar, me mande só: <code>esgotou</code>")
    return "\n".join(partes)


def esgotar_cupom(texto, tg, cfg, estado):
    codigo = re.sub(r"^\s*/?(esgotou|esgotado|acabou)\s*", "", texto, flags=re.I).strip().upper()
    lista = cupons.ativos(estado)
    if not lista:
        return "Não tenho nenhum cupom ativo registrado."
    if codigo:
        chave = next((k for k in lista if k.upper() == codigo), None)
        if not chave:
            return f"Não achei o cupom {html.escape(codigo)}. Ativos: " + ", ".join(html.escape(k) for k in lista)
    elif len(lista) == 1:
        chave = next(iter(lista))
    else:
        return "Tem mais de um cupom ativo. Me diga qual: " + ", ".join(
            f"<code>esgotou {html.escape(k)}</code>" for k in lista)
    try:
        cupons.marcar(tg, cfg, estado, chave, "esgotado",
                      f"❌ O cupom{cupons.nome(chave)} esgotou! Fica de olho no canal que sempre aparece outro 🪇")
    except TelegramErro as e:
        return f"⚠️ Não consegui avisar no canal: {e}"
    return f"✅ Marquei o cupom{cupons.nome(chave)} como esgotado e avisei no canal."


def marcar_geral(texto, estado, geral=True):
    """'geral CORREHOJE' libera um cupom sem categoria para as ofertas; 'restrito X' desfaz."""
    codigo = re.sub(r"^\s*/?(geral|restrito)\s*", "", texto, flags=re.I).strip().upper()
    lista = cupons.ativos(estado)
    if not codigo:
        marcados = [k for k, c in lista.items() if c.get("geral")]
        return ("Mande <code>geral CÓDIGO</code> depois de testar no carrinho que o cupom vale para "
                "produtos comuns. Liberados agora: " + (", ".join(html.escape(k) for k in marcados) or "nenhum"))
    chave = next((k for k in lista if k.upper() == codigo), None)
    if not chave:
        return f"Não achei o cupom ativo {html.escape(codigo)}. Ativos: " + ", ".join(
            html.escape(k) for k in lista if not k.startswith("#"))
    if geral:
        estado["cupons"][chave]["geral"] = True
        return (f"✅ O cupom {html.escape(chave)} agora entra nas ofertas mesmo sem categoria. "
                "O bot usa sempre o que mais economiza (respeitando mínimo e teto). "
                f"Para desfazer: <code>restrito {html.escape(chave)}</code>")
    estado["cupons"][chave].pop("geral", None)
    return f"↩️ O cupom {html.escape(chave)} voltou a valer só pela categoria dele."


def verificar_cupons(tg, cfg, estado, agora, log=print):
    cupons.verificar(tg, cfg, estado, agora, log)


# ---------- resumo ----------

def _resumo_whatsapp(agora, arquivo=None):
    """Linhas do WhatsApp para o resumo, lidas de data/wa_estado.json (escrito pelo wa/servico.mjs)."""
    import json
    from pathlib import Path

    arq = Path(arquivo) if arquivo else Path(__file__).resolve().parent.parent / "data" / "wa_estado.json"
    try:
        wa = json.loads(arq.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return []
    hoje = agora.date().isoformat()
    ontem = (agora.date() - timedelta(days=1)).isoformat()
    linhas = ["", "💬 <b>WhatsApp</b>"]
    membros = wa.get("membros") or {}
    if hoje in membros:
        dif = f" ({membros[hoje] - membros[ontem]:+d} desde ontem)" if ontem in membros else ""
        linhas.append(f"👥 Membros no grupo: <b>{membros[hoje]}</b>{dif}")
    enviados = wa.get("enviados", 0) if wa.get("dia") == hoje else 0
    linhas.append(f"📣 Posts no grupo hoje: <b>{enviados}</b>")
    apagados = (wa.get("apagados") or {}).get(hoje)
    if apagados:
        linhas.append(f"🧹 Links de outras pessoas apagados: {apagados}")
    if wa.get("pausado_ate") and wa["pausado_ate"] > agora.isoformat():
        linhas.append("🛑 Em pausa de segurança (restrição do WhatsApp)")
    elif wa.get("conectado") is False:
        linhas.append("⚠️ Desconectado: rode o “Conectar WhatsApp”")
    else:
        linhas.append("✅ Conectado")
    return linhas + [""]


def montar_resumo(estado, cfg, tg, agora):
    hoje = agora.date().isoformat()
    ontem = (agora.date() - timedelta(days=1)).isoformat()
    linhas = [f"📊 <b>Resumo do Chocalho — {agora:%d/%m}</b>", ""]

    hist = estado.setdefault("membros_hist", {})
    try:
        total = tg.membros(cfg.canal)
        hist[hoje] = total
        for dia in sorted(hist)[:-30]:
            del hist[dia]
        dif = f" ({total - hist[ontem]:+d} desde ontem)" if ontem in hist else ""
        linhas.append(f"👥 Membros: <b>{total}</b>{dif}")
    except (TelegramErro, AttributeError):
        pass
    mov = (estado.get("membros_dia") or {}).get(hoje)
    if mov:
        linhas.append(f"   ➕ {mov.get('entrou', 0)} entraram · ➖ {mov.get('saiu', 0)} saíram hoje")

    linhas += _resumo_whatsapp(agora)
    linhas.append(f"📣 Posts hoje: <b>{est.posts_hoje(estado, agora)}</b> (limite {cfg.max_por_dia})")
    linhas.append(f"🔗 Produtos com link oficial: {len(estado.get('links', {}))}")
    if estado.get("aguardando_link"):
        linhas.append(f"⏳ Ofertas boas esperando link: {estado['aguardando_link']}")
    feitos = (estado.get("lotes_dia") or {}).get(hoje, 0)
    pend = " (1 esperando sua resposta)" if (estado.get("lote") or {}).get("dia") == hoje else ""
    linhas.append(f"📦 Lotes hoje: {feitos} de {cfg.lotes_por_dia}{pend}")

    copiadas = [i for i in ((estado.get("posts_dia") or {}).get("itens") or [])
                if i.get("fonte") and (estado.get("posts_dia") or {}).get("dia") == hoje]
    linhas.append(f"🔁 Copiadas de outros canais hoje: <b>{len(copiadas)}</b>")
    for i in copiadas[:15]:
        loja = "Shopee" if i.get("loja") == "shopee" else "ML"
        linhas.append(f"   • @{html.escape(i['fonte'])} → {html.escape(i['titulo'][:45])} ({loja})")

    from . import busca_publica
    procurados = busca_publica.mais_procurados(estado)
    if procurados:
        linhas.append("🙋 Mais procurados na busca (30 dias): " + ", ".join(
            f"{html.escape(t)} ({v['n']}x{', ' + str(v['sem']) + ' sem resultado' if v['sem'] else ''})"
            for t, v in procurados))

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


# ---------- palavras bloqueadas ----------

def _titulos_recentes(estado):
    fontes = list(estado.get("postados", {}).values()) + list(estado.get("shopee", {}).get("titulos", {}).values())
    return [v["titulo"] for v in fontes if v.get("titulo")]


def bloquear(palavra, estado):
    from . import filtros
    palavra = " ".join((palavra or "").split()).lower()
    if len(filtros.normalizar(palavra).strip()) < 3:
        return "Mande <b>bloquear</b> + a palavra (pelo menos 3 letras). Ex.: <code>bloquear baby doll</code>"
    lista = estado.setdefault("bloqueados", [])
    if filtros.normalizar(palavra) in [filtros.normalizar(p) for p in lista]:
        return f"🚫 <b>{html.escape(palavra)}</b> já estava bloqueada."
    # Mostra o que essa palavra teria barrado, para você ver se não é ampla demais
    filtros.definir_bloqueios([palavra])
    pegos = [t for t in _titulos_recentes(estado) if (filtros.motivo_bloqueio(t) or "").startswith("bloqueado por você")]
    lista.append(palavra)
    filtros.definir_bloqueios(lista)
    resp = f"🚫 Pronto: não posto mais produtos com <b>{html.escape(palavra)}</b> no título."
    if pegos:
        resp += f"\n\nDos posts recentes, {len(pegos)} teriam sido barrados. Ex.:\n" + "\n".join(
            f"• {html.escape(t[:60])}" for t in pegos[:3])
        if len(pegos) > 15:
            resp += "\n\n⚠️ É bastante coisa. Se a palavra for ampla demais, mande <b>desbloquear " \
                    f"{html.escape(palavra)}</b>."
    return resp


def desbloquear(palavra, estado):
    from . import filtros
    alvo = filtros.normalizar(" ".join((palavra or "").split()))
    lista = estado.get("bloqueados") or []
    nova = [p for p in lista if filtros.normalizar(p) != alvo]
    if len(nova) == len(lista):
        return "Essa palavra não está na lista. Mande <b>bloqueados</b> para ver a lista."
    estado["bloqueados"] = nova
    filtros.definir_bloqueios(nova)
    return f"✅ <b>{html.escape(palavra.strip())}</b> liberada de novo."


def listar_bloqueados(estado):
    lista = estado.get("bloqueados") or []
    if not lista:
        return "Nenhuma palavra bloqueada por você. Para bloquear: <code>bloquear baby doll</code>"
    return "🚫 <b>Palavras bloqueadas por você</b>\n" + "\n".join(f"• {html.escape(p)}" for p in lista) + \
        "\n\nPara liberar: <b>desbloquear</b> + palavra."


# ---------- fila do WhatsApp ----------

def _itens_fila():
    import json
    import os
    from pathlib import Path

    pasta = os.environ.get("WA_FILA")
    if not pasta or not Path(pasta).is_dir():
        return []
    itens = []
    for arq in sorted(Path(pasta).glob("*.json")):
        try:
            itens.append((arq, json.loads(arq.read_text(encoding="utf-8"))))
        except (OSError, ValueError):
            pass
    return itens


def _apagar_item(arq, item):
    from pathlib import Path
    img = item.get("imagem")
    if img and not str(img).startswith("http"):
        Path(img).unlink(missing_ok=True)
    arq.unlink(missing_ok=True)


def _nome_do_item(item):
    """Linha do produto dentro do texto da oferta (pula a frase de abertura e os preços)."""
    linhas = [l.strip() for l in (item.get("texto") or "").splitlines() if l.strip()]
    for l in linhas[1:]:
        if "R$" not in l and "http" not in l and not l.startswith(("_", "*")):
            return l
    return linhas[0] if linhas else "(sem texto)"


def ver_fila(agora, arquivo_wa=None):
    import json
    from pathlib import Path

    arq = Path(arquivo_wa) if arquivo_wa else Path(__file__).resolve().parent.parent / "data" / "wa_estado.json"
    try:
        wa = json.loads(arq.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        wa = {}
    enviados = wa.get("enviados", 0) if wa.get("dia") == agora.date().isoformat() else 0
    limite = f" de {wa['max_dia']}" if wa.get("max_dia") else ""
    linhas = ["📬 <b>Fila do WhatsApp</b>", f"Hoje já saíram <b>{enviados}</b>{limite} posts no grupo."]
    if wa.get("intervalo_max"):
        linhas.append(f"Sai 1 a cada {wa['intervalo_min']:g} a {wa['intervalo_max']:g} min (sorteado), "
                      "com o limite espalhado das 7h às 23h.")
    elif wa.get("intervalo_min"):
        linhas.append(f"Sai 1 a cada {wa['intervalo_min']} min, das 7h às 23h.")
    from .fila_pagina import ENDERECO
    pagina = f'🗂️ O dia inteiro (o que saiu, o que espera e o que ficou de fora): <a href="{ENDERECO}">página da fila</a>'
    itens = _itens_fila()
    if not itens:
        return "\n".join(linhas + ["", "A fila está vazia agora.", "", pagina])
    linhas.append("")
    for i, (_, item) in enumerate(itens, 1):
        loja = "Shopee" if item.get("loja") == "shopee" else "ML"
        linhas.append(f"{i}. [{loja}] {html.escape(_nome_do_item(item)[:60])}")
    linhas += ["", "Para cancelar um: <b>tirar 2</b>. Para cancelar todos: <b>limpar fila</b>.",
               "<i>Oferta parada há mais de 3 h sai da fila sozinha.</i>", "", pagina]
    return "\n".join(linhas)


def tirar_da_fila(texto):
    nums = sorted({int(n) for n in re.findall(r"\d+", texto)}, reverse=True)
    itens = _itens_fila()
    if not nums:
        return "Mande <b>tirar</b> + o número do item. Veja os números com <b>fila</b>."
    tirados = []
    for n in nums:
        if 1 <= n <= len(itens):
            arq, item = itens[n - 1]
            _apagar_item(arq, item)
            tirados.append(_nome_do_item(item)[:50])
    if not tirados:
        return "Não achei esse número na fila. Mande <b>fila</b> para ver a lista atual."
    return "🗑️ Tirei da fila:\n" + "\n".join(f"• {html.escape(t)}" for t in reversed(tirados))


def limpar_fila():
    itens = _itens_fila()
    for arq, item in itens:
        _apagar_item(arq, item)
    return f"🗑️ Fila do WhatsApp limpa ({len(itens)} item(ns) cancelado(s))." if itens else "A fila já estava vazia."


# ---------- aviso de bot parado ----------

HORAS_SEM_POST = 3


def ultimo_post(estado):
    """Data e hora do último post no canal (Mercado Livre ou Shopee), ou None."""
    quando = [v.get("quando") for v in estado.get("postados", {}).values()]
    quando += list(estado.get("shopee", {}).get("postados", {}).values())
    datas = []
    for q in quando:
        try:
            datas.append(datetime.fromisoformat(q))
        except (TypeError, ValueError):
            pass
    return max(datas) if datas else None


def avisar_se_parado(tg, cfg, estado, agora, log=print):
    """Rodando, mas sem postar nada há horas (token vencido, loja fora do ar...): avisa 1x por dia."""
    hoje = agora.date().isoformat()
    if not cfg.admin_chat or estado.get("aviso_parado") == hoje:
        return False
    if not (cfg.hora_inicio + HORAS_SEM_POST <= agora.hour < cfg.hora_fim):
        return False
    ultimo = ultimo_post(estado)
    if ultimo is None:
        return False
    if ultimo.tzinfo is None:
        ultimo = ultimo.replace(tzinfo=agora.tzinfo)
    horas = (agora - ultimo).total_seconds() / 3600
    if horas < HORAS_SEM_POST:
        return False
    texto = (f"⚠️ <b>Faz {int(horas)} h que não sai nenhuma oferta no canal.</b>\n"
             f"Último post: {ultimo:%d/%m às %H:%M}. O bot está rodando, mas não achou nada para postar "
             "ou algo está falhando.")
    if estado.get("aguardando_link"):
        texto += f"\n⏳ Há {estado['aguardando_link']} ofertas boas esperando link do Linkbuilder."
    texto += "\nMe chame no Claude se quiser que eu veja o motivo."
    try:
        tg.enviar_texto(cfg.admin_chat, texto, html=True)
        estado["aviso_parado"] = hoje
        log("Aviso de bot parado enviado.")
        return True
    except TelegramErro as e:
        log(f"Aviso: não consegui mandar o aviso de bot parado: {e}")
        return False


# ---------------------------------------------------------------- recarga do chip do WhatsApp
RECARGA_AVISOS = (75, 85)  # chip pré-pago perde o número com 90 dias sem recarga


def registrar_recarga(texto, estado, agora):
    """'recarga' (hoje), 'recarga 10/11' ou 'recarga plano' (chip com plano: não precisa de lembrete)."""
    resto = _norm(texto).split(" ", 1)[1].strip() if " " in texto.strip() else ""
    if resto in ("plano", "pos", "pós", "controle", "pos-pago", "pós-pago"):
        estado["chip_recarga"] = {"plano": True}
        return "Anotado: o chip do WhatsApp tem plano. Não vou lembrar de recarga."
    if not resto:
        dia = agora.date()
    else:
        m = re.fullmatch(r"(\d{1,2})/(\d{1,2})(?:/(\d{2,4}))?", resto)
        if not m:
            return "Mande <b>recarga</b> (fiz hoje), <b>recarga 10/11</b> (fiz nesse dia) ou <b>recarga plano</b>."
        ano = int(m.group(3)) if m.group(3) else agora.year
        ano = ano + 2000 if ano < 100 else ano
        try:
            dia = agora.date().replace(year=ano, month=int(m.group(2)), day=int(m.group(1)))
        except ValueError:
            return "Essa data não existe. Ex.: <b>recarga 10/11</b>."
        if dia > agora.date():
            dia = dia.replace(year=dia.year - 1)
    estado["chip_recarga"] = {"dia": dia.isoformat(), "avisos": []}
    vence = dia + timedelta(days=90)
    return (f"Anotado: última recarga do chip em {dia:%d/%m/%Y}. O número só corre risco depois de "
            f"{vence:%d/%m/%Y}. Aviso você com {RECARGA_AVISOS[0]} e {RECARGA_AVISOS[1]} dias.")


def lembrar_recarga(tg, cfg, estado, agora, log=print):
    """Lembra a recarga do chip pré-pago antes dos 90 dias (1 aviso em cada marco)."""
    reg = estado.get("chip_recarga") or {}
    if not cfg.admin_chat or reg.get("plano") or not reg.get("dia"):
        return False
    dias = (agora.date() - datetime.fromisoformat(reg["dia"]).date()).days
    marco = max((m for m in RECARGA_AVISOS if dias >= m), default=None)
    if marco is None or marco in reg.get("avisos", []):
        return False
    falta = 90 - dias
    try:
        tg.enviar_texto(cfg.admin_chat, f"📱 <b>Recarga do chip do WhatsApp</b>: a última foi há {dias} dias. Chip pré-pago "
                        f"perde o número com 90 dias sem recarga (faltam {max(falta, 0)}). Depois de recarregar, "
                        "mande <b>recarga</b> aqui.")
    except TelegramErro as e:
        log(f"Aviso: não consegui lembrar da recarga: {e}")
        return False
    reg.setdefault("avisos", []).append(marco)
    return True


def tratar_texto(texto, tg, ml, estado, cfg, agora, session=None, rng=random):
    """Decide o que fazer com uma mensagem sua. Retorna a resposta (ou None)."""
    t = (texto or "").strip()
    n = _norm(t)
    if re.match(r"/?cupom\s+(da\s+)?shopee\b", n):
        return postar_cupom_shopee(t, tg, cfg, estado, agora)
    if n.startswith(("cupom", "/cupom")):
        return postar_cupom(t, tg, cfg, estado, agora)
    if n.startswith(("achar ", "/achar ")):
        from . import busca_publica
        return busca_publica.procurar(t.split(" ", 1)[1], estado, agora, ml, busca_publica._shopee())
    if n.startswith(("esgotou", "esgotado", "acabou", "/esgotou")):
        return esgotar_cupom(t, tg, cfg, estado)
    if n.startswith(("geral", "/geral")):
        return marcar_geral(t, estado, True)
    if n.startswith(("restrito", "/restrito")):
        return marcar_geral(t, estado, False)
    if n in ("resumo", "/resumo", "status", "/status"):
        return montar_resumo(estado, cfg, tg, agora)
    if n.startswith(("bloquear ", "/bloquear ")):
        return bloquear(t.split(" ", 1)[1], estado)
    if n.startswith(("desbloquear ", "/desbloquear ")):
        return desbloquear(t.split(" ", 1)[1], estado)
    if n in ("bloqueados", "/bloqueados", "bloquear", "/bloquear"):
        return listar_bloqueados(estado)
    if n in ("fila", "/fila"):
        return ver_fila(agora)
    if n == "recarga" or n.startswith(("recarga ", "/recarga")):
        return registrar_recarga(t.lstrip("/"), estado, agora)
    if n in ("limpar fila", "/limpar_fila"):
        return limpar_fila()
    if n.startswith(("tirar ", "/tirar ")):
        return tirar_da_fila(n)
    if n in ("pacote", "/pacote", "instagram", "/instagram"):
        from . import conteudo
        conteudo.montar_e_enviar(tg, cfg.admin_chat, estado, agora, rng=rng, session=session)
        return None
    if n == "marcar" or n.startswith(("marcar ", "/marcar")):
        return marcar(t, tg, ml, estado, cfg, agora, session, rng)
    if n.startswith(("buscar ", "/buscar ")):
        from . import busca
        return busca.buscar(t.split(" ", 1)[1], ml, estado)
    if n.startswith(("pegar", "/pegar")):
        from . import busca
        return busca.pegar(t.split(" ", 1)[1] if " " in t else "", tg, estado, cfg, agora)
    if n.startswith(("vigiar ", "/vigiar ")):
        from . import busca
        return busca.vigiar(t.split(" ", 1)[1], estado)
    if n in ("vigias", "/vigias"):
        from . import busca
        return busca.listar_vigias(estado)
    if n.startswith(("parar ", "/parar ")):
        from . import busca
        return busca.parar(t.split(" ", 1)[1], estado)
    if n in ("categorias", "/categorias"):
        return relatorio_areas(tg, ml, cfg, log=lambda m: None)
    if n in ("aprovar categorias", "/aprovar_categorias"):
        estado["areas_novas"] = True
        estado["descoberta_em"] = None  # refaz a busca na próxima rodada
        return ("✅ Categorias novas aprovadas. Na próxima rodada o bot refaz a busca já com roupas, games, "
                "livros, escola, esporte, casa e festa. Para desligar: <b>pausar categorias</b>.")
    if n in ("pausar categorias", "/pausar_categorias"):
        estado["areas_novas"] = False
        estado["descoberta_em"] = None
        return "⏸️ Categorias novas desligadas; o bot volta só para Bebês e Brinquedos."
    if n in ("temas", "/temas"):
        from . import conteudo
        return conteudo.listar_temas(estado, agora)
    partes = n.split()
    if partes and partes[0] in ("carrossel", "reel") and len(partes) >= 2:
        from . import conteudo
        return conteudo.enviar_tema(tg, cfg.admin_chat, estado, agora, partes[1], partes[0], rng, session)
    if partes and partes[0] in ("insta", "/insta"):
        achados = lote.RE_MELI.findall(t)
        if not achados:
            return "Mande <b>insta</b> + o link meli.la do produto."
        # vários links numa mensagem só: gera um post para cada
        erros = [postar_insta(l, tg, ml, estado, cfg, session, rng, agora) for l in dict.fromkeys(achados)]
        erros = [e for e in erros if e]
        return "\n".join(erros) if erros else None
    links = lote.RE_MELI.findall(t)
    if links:
        pendente = estado.get("lote")
        extra = estado.get("lote_extra")
        if (pendente and len(links) == len(pendente["ids"])) or (extra and len(links) == len(extra["ids"])):
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
        if u.get("callback_query"):
            from . import instagram_pub
            try:
                instagram_pub.tratar_toque(tg, cfg.admin_chat, estado, u["callback_query"], agora)
            except TelegramErro as e:
                log(f"Aviso: não consegui responder ao botão: {e}")
            continue
        msg = u.get("message") or {}
        if str((msg.get("chat") or {}).get("id")) != str(cfg.admin_chat):
            from . import busca_publica  # busca sob pedido para quem escreve no privado do bot (se ligada)
            busca_publica.atender(msg, tg, ml, estado, agora, log)
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
