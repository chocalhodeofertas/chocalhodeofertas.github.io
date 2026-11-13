"""Publicação no Instagram com aprovação pelo Telegram.

Fluxo:
1. Quando o bot monta um carrossel ou um post de produto (pacote do dia, "carrossel <tema>",
   "insta <link>"), as imagens vão para docs/ig-tmp/<id>/ (o Instagram baixa pelo GitHub Pages)
   e chega no seu Telegram a pergunta com os botões ✅ Aprovar / ❌ Recusar.
2. Aprovado: vai ao ar no horário do roteiro (ou na hora, se não houver horário ou se ele já passou).
3. Antes de publicar, se a peça tiver mais de 2 h, confere se cada produto continua nas ofertas
   com preço igual ou menor. Se não, não publica e te avisa.
4. Pendentes de dias anteriores expiram. As imagens são apagadas 2 dias depois.

Nada vai ao ar sem o seu toque em Aprovar. Reel e stories continuam manuais.
"""
import io
import os
import re
import shutil
from datetime import datetime, timedelta
from pathlib import Path

import requests

from .telegram import TelegramErro

SITE = "https://chocalhodeofertas.github.io"
PASTA = Path(__file__).resolve().parent.parent / "docs" / "ig-tmp"
CONFERIR_PRECO_APOS = timedelta(hours=2)
GUARDAR_DIAS = 2
NOME_TIPO = {"carrossel": "carrossel", "post": "post do produto"}


def ativo():
    return bool(os.environ.get("INSTAGRAM_TOKEN") and os.environ.get("INSTAGRAM_USER_ID"))


def _hora(texto, agora):
    """'18h' / '20h30' → datetime de hoje. None se não houver horário."""
    m = re.fullmatch(r"(\d{1,2})h(\d{2})?", (texto or "").strip())
    if not m:
        return None
    return agora.replace(hour=int(m.group(1)), minute=int(m.group(2) or 0), second=0, microsecond=0)


def _jpeg(png_bytes):
    from PIL import Image
    img = Image.open(io.BytesIO(png_bytes)).convert("RGB")
    out = io.BytesIO()
    img.save(out, "JPEG", quality=88, optimize=True)
    return out.getvalue()


def _quando_txt(item):
    return f"às {item['hora_txt']}" if item.get("hora_txt") else "assim que você aprovar"


def oferecer(tg, chat, estado, agora, tipo, imagens_png, legenda, ofertas, hora_txt=None, pasta=PASTA):
    """Guarda a peça e pergunta no Telegram se pode publicar. Devolve o id (ou None se o Instagram não está ligado)."""
    if not ativo() or not chat:
        return None
    fila = estado.setdefault("ig_fila", {})
    pid = f"{agora:%Y%m%d-%H%M%S}-{len(fila) % 100:02d}"
    destino = pasta / pid
    destino.mkdir(parents=True, exist_ok=True)
    nomes = []
    for k, png in enumerate(imagens_png, 1):
        nome = f"{k:02d}.jpg"
        (destino / nome).write_bytes(_jpeg(png))
        nomes.append(nome)
    hora = _hora(hora_txt, agora)
    item = {
        "tipo": tipo, "criado_em": agora.isoformat(timespec="minutes"),
        "hora": hora.isoformat(timespec="minutes") if hora else None, "hora_txt": hora_txt if hora else None,
        "status": "pendente", "legenda": legenda, "imagens": nomes,
        "produtos": [{"id": o.id, "titulo": (o.titulo or "")[:60], "preco": o.preco} for o in ofertas],
    }
    fila[pid] = item
    texto = f"📲 Publicar este {NOME_TIPO[tipo]} no Instagram {_quando_txt(item)}?"
    try:
        msg = tg.enviar_texto(chat, texto, acoes=[("✅ Aprovar", f"ig:ok:{pid}"), ("❌ Recusar", f"ig:nao:{pid}")])
        item["msg"] = msg.get("message_id")
    except TelegramErro:
        item["status"] = "erro"
        item["motivo"] = "não consegui mandar a pergunta no Telegram"
    return pid


def _editar(tg, chat, item, texto):
    if item.get("msg"):
        try:
            tg.editar_texto(chat, item["msg"], texto, html=False)
        except TelegramErro:
            pass


def tratar_toque(tg, chat, estado, cq, agora):
    """Trata o toque em ✅/❌. Devolve True se o toque era deste módulo."""
    dados = cq.get("data") or ""
    if not dados.startswith("ig:"):
        return False
    _, acao, pid = (dados.split(":", 2) + ["", ""])[:3]
    item = (estado.get("ig_fila") or {}).get(pid)
    msg_chat = ((cq.get("message") or {}).get("chat") or {}).get("id")
    if str(msg_chat) != str(chat):
        return True  # toque de outra conversa: ignora
    if not item:
        tg.responder_toque(cq["id"], "Essa peça não está mais na fila.")
        return True
    if item["status"] != "pendente":
        tg.responder_toque(cq["id"], f"Já estava: {item['status']}.")
        return True
    nome = NOME_TIPO[item["tipo"]]
    if acao == "ok":
        item["status"] = "aprovado"
        item["aprovado_em"] = agora.isoformat(timespec="minutes")
        tg.responder_toque(cq["id"], "Aprovado!")
        _editar(tg, chat, item, f"✅ Aprovado: o {nome} vai ao ar no Instagram {_quando_txt(item)}"
                                + (" (confiro o preço antes)." if item.get("hora_txt") else "."))
    else:
        item["status"] = "recusado"
        tg.responder_toque(cq["id"], "Recusado.")
        _editar(tg, chat, item, f"❌ Recusado: não vou publicar este {nome}. Se quiser, poste à mão.")
    return True


def _conferir_precos(item, estado):
    """Devolve o motivo para NÃO publicar, ou None se está tudo certo."""
    atuais = {i["id"]: i for i in (estado.get("vitrine") or {}).get("itens", [])}
    for p in item["produtos"]:
        agora_i = atuais.get(p["id"])
        if not agora_i:
            return f"“{p['titulo']}” saiu das ofertas"
        if agora_i["preco"] > p["preco"] + 0.005:
            from .mensagens import brl
            return f"o preço de “{p['titulo']}” subiu ({brl(p['preco'])} → {brl(agora_i['preco'])})"
    return None


def _no_ar(urls, session):
    try:
        return all(session.head(u, timeout=20, allow_redirects=True).status_code == 200 for u in urls)
    except requests.RequestException:
        return False


def publicar_pendentes(tg, chat, estado, agora, ig=None, session=None, pasta=PASTA, log=print):
    """Publica o que foi aprovado e já chegou no horário; expira e limpa o resto."""
    fila = estado.get("ig_fila") or {}
    if not fila:
        return
    hoje = agora.date().isoformat()
    session = session or requests.Session()
    for pid, item in list(fila.items()):
        criado = datetime.fromisoformat(item["criado_em"])
        nome = NOME_TIPO[item["tipo"]]
        if item["status"] in ("pendente", "aprovado") and criado.date().isoformat() < hoje:
            item["status"] = "expirado"
            _editar(tg, chat, item, f"⌛ Expirou: o {nome} de {criado:%d/%m} não foi publicado.")
            continue
        if item["status"] != "aprovado":
            continue
        if item.get("hora") and agora < datetime.fromisoformat(item["hora"]):
            continue
        if agora - criado > CONFERIR_PRECO_APOS:
            motivo = _conferir_precos(item, estado)
            if motivo:
                item["status"] = "barrado"
                item["motivo"] = motivo
                aviso = f"⚠️ Não publiquei o {nome} {_quando_txt(item)}: {motivo}."
                _editar(tg, chat, item, aviso)
                try:
                    tg.enviar_texto(chat, aviso + " Se quiser, peça outro (ex.: carrossel brinquedos).")
                except TelegramErro:
                    pass
                continue
        urls = [f"{SITE}/ig-tmp/{pid}/{n}" for n in item["imagens"]]
        if not _no_ar(urls, session):
            log(f"Instagram: imagens de {pid} ainda não estão no ar; tento na próxima rodada.")
            continue
        from .instagram import Instagram, InstagramErro
        try:
            ig = ig or Instagram(os.environ["INSTAGRAM_TOKEN"], os.environ["INSTAGRAM_USER_ID"])
            if item["tipo"] == "carrossel":
                mid, link = ig.publicar_carrossel(urls, item["legenda"])
            else:
                mid, link = ig.publicar_imagem(urls[0], item["legenda"])
        except (InstagramErro, KeyError) as e:
            item["tentativas"] = item.get("tentativas", 0) + 1
            log(f"Instagram: falha ao publicar {pid}: {e}")
            if item["tentativas"] >= 3:
                item["status"] = "erro"
                item["motivo"] = str(e)[:200]
                try:
                    tg.enviar_texto(chat, f"⚠️ Não consegui publicar o {nome} no Instagram depois de 3 tentativas: {e}")
                except TelegramErro:
                    pass
            continue
        item.update(status="publicado", publicado_em=agora.isoformat(timespec="minutes"), ig_id=mid, link=link)
        _editar(tg, chat, item, f"📸 Publicado no Instagram: {link}")
        log(f"Instagram: {nome} publicado ({link}).")
    _limpar(estado, agora, pasta)


def _limpar(estado, agora, pasta=PASTA):
    """Apaga imagens de peças já resolvidas há mais de 2 dias (e os registros com mais de 30 dias)."""
    fila = estado.get("ig_fila") or {}
    for pid, item in list(fila.items()):
        criado = datetime.fromisoformat(item["criado_em"])
        if item["status"] in ("pendente", "aprovado"):
            continue
        if agora - criado > timedelta(days=GUARDAR_DIAS):
            shutil.rmtree(pasta / pid, ignore_errors=True)
        if agora - criado > timedelta(days=30):
            del fila[pid]
