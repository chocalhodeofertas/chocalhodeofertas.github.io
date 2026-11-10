"""Cupons postados no canal.

Um post pode ter vários cupons (blocos). Cada cupom tem um status: ativo,
esgotado ou encerrado. Quando o status muda, o bot reescreve o post,
riscando só aquele cupom.

estado["posts_cupom"][id_da_mensagem] = {"titulo", "blocos": [{"codigo", "html"}], "rodape", "criado"}
estado["cupons"][CODIGO] = {"post", "status", "validade", "criado"}
"""
import html
from datetime import datetime

from .telegram import TelegramErro

RODAPE = "Cupons têm quantidade e prazo limitados. Ative no app antes de comprar."
MARCA = {"esgotado": "❌ esgotou", "encerrado": "⏰ encerrado"}
DIAS_GUARDAR = 10


def render(estado, post):
    cupons = estado.get("cupons", {})
    partes, ativos, status_unico = [], 0, None
    for b in post["blocos"]:
        st = cupons.get(b["codigo"], {}).get("status", "ativo")
        status_unico = st
        if st == "ativo":
            ativos += 1
            partes.append(b["html"])
        else:
            partes.append(f"<s>{b['html']}</s>\n<b>{MARCA.get(st, st)}</b>")
    titulo = post["titulo"]
    if not ativos:
        if len(post["blocos"]) == 1:
            titulo = "❌ <b>CUPOM ESGOTADO</b>" if status_unico == "esgotado" else "⏰ <b>CUPOM ENCERRADO</b>"
        else:
            titulo = "⏰ <b>CUPONS ENCERRADOS</b>"
    return f"{titulo}\n\n" + "\n\n".join(partes) + f"\n\n<i>{post['rodape']}</i>"


def publicar(tg, cfg, estado, titulo, blocos, agora, rodape=RODAPE):
    """blocos: lista de (codigo ou None, html, validade ou None). Retorna o id da mensagem."""
    post = {"titulo": titulo, "blocos": [{"codigo": c or "", "html": h} for c, h, _ in blocos],
            "rodape": rodape, "criado": agora.isoformat(timespec="minutes")}
    enviada = tg.enviar_texto(cfg.canal, render(estado, post), html=True)
    mid = enviada.get("message_id") if isinstance(enviada, dict) else None
    if not mid:
        return None
    cupons = estado.setdefault("cupons", {})
    for b, (codigo, _, validade) in zip(post["blocos"], blocos):
        if not codigo:
            b["codigo"] = f"#{mid}"
        cupons[b["codigo"]] = {
            "post": mid, "status": "ativo", "criado": post["criado"],
            "validade": validade.isoformat(timespec="minutes") if validade else None,
        }
    estado.setdefault("posts_cupom", {})[str(mid)] = post
    from .estado import contar_dia

    contar_dia(estado, agora, "cupons", len(blocos))
    return mid


def _reescrever(tg, cfg, estado, mid):
    post = estado.get("posts_cupom", {}).get(str(mid))
    if not post:
        return
    try:
        tg.editar_texto(cfg.canal, mid, render(estado, post))
    except TelegramErro:
        pass  # mensagem apagada ou sem mudança


def marcar(tg, cfg, estado, codigo, status, aviso=None):
    c = estado["cupons"][codigo]
    c["status"] = status
    _reescrever(tg, cfg, estado, c["post"])
    if aviso:
        tg.enviar_texto(cfg.canal, aviso, html=True, responder_a=c["post"])


def atualizar_bloco(tg, cfg, estado, codigo, novo_html, aviso=None, validade=None):
    c = estado["cupons"][codigo]
    if validade:
        c["validade"] = validade.isoformat(timespec="minutes")
    post = estado.get("posts_cupom", {}).get(str(c["post"]))
    if post:
        for b in post["blocos"]:
            if b["codigo"] == codigo:
                b["html"] = novo_html
    _reescrever(tg, cfg, estado, c["post"])
    if aviso:
        tg.enviar_texto(cfg.canal, aviso, html=True, responder_a=c["post"])


def ativos(estado):
    return {k: c for k, c in (estado.get("cupons") or {}).items() if c.get("status") == "ativo"}


def verificar(tg, cfg, estado, agora, log=print):
    """Encerra os cupons vencidos e esquece os antigos."""
    cupons = estado.get("cupons") or {}
    for codigo, c in list(cupons.items()):
        if c.get("status") == "ativo" and c.get("validade") and datetime.fromisoformat(c["validade"]) < agora:
            try:
                marcar(tg, cfg, estado, codigo, "encerrado")
                log(f"Cupom {codigo} encerrado (venceu).")
            except TelegramErro as e:
                log(f"Aviso: não consegui marcar o cupom {codigo}: {e}")
        if c.get("criado") and (agora - datetime.fromisoformat(c["criado"])).days > DIAS_GUARDAR:
            del cupons[codigo]
    posts = estado.get("posts_cupom") or {}
    for mid, p in list(posts.items()):
        if (agora - datetime.fromisoformat(p["criado"])).days > DIAS_GUARDAR:
            del posts[mid]


def nome(codigo):
    return "" if codigo.startswith("#") else f" {html.escape(codigo)}"
